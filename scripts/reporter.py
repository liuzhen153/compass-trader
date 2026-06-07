#!/usr/bin/env python3
"""
Compass Trader · 绩效报告生成器
从 data/ 目录读取数据，自动生成周报/月报 .md 文件。

用法：
  python3 scripts/reporter.py weekly [输出目录]     # 生成本周周报
  python3 scripts/reporter.py monthly [输出目录]    # 生成本月月报
  python3 scripts/reporter.py trade <trade_id> [输出目录]  # 生成单笔交易记录
  python3 scripts/reporter.py summary                  # 仅打印，不写文件
"""

import sys
import json
import os
from datetime import datetime, timedelta, date

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"


# ── 数据加载 ──────────────────────────────────────────────

def _read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _load_all():
    """加载所有数据"""
    account = _read_json("account.json") or {"initial_capital": 1000000, "cash": 1000000, "created_at": "2026-01-01"}
    positions_data = _read_json("positions.json") or {"positions": []}
    trades_data = _read_json("trades.json") or {"trades": []}
    tracker = _read_json("tracker.json") or {"daily_snapshots": []}
    return account, positions_data.get("positions", []), trades_data.get("trades", []), tracker


def _get_benchmark_return(start_date: str, end_date: str = None) -> dict:
    """获取同期沪深300收益作为基准"""
    try:
        from market_data import get_index_history
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        hist = get_index_history("000300", start_date, end_date)
        if isinstance(hist, dict) and "error" in hist:
            return {"error": hist["error"], "return_pct": None}
        if not hist or len(hist) < 2:
            return {"error": "数据不足", "return_pct": None}
        start_val = hist[0]["close"]
        end_val = hist[-1]["close"]
        ret = (end_val - start_val) / start_val * 100
        return {"return_pct": round(ret, 2), "start_val": start_val, "end_val": end_val}
    except Exception as e:
        return {"error": str(e), "return_pct": None}


# ── 绩效计算 ──────────────────────────────────────────────

def _calc_performance(trades: list, start_date: str = None, end_date: str = None) -> dict:
    """从交易列表计算绩效指标"""
    if not trades:
        return {
            "trade_count": 0, "win_count": 0, "loss_count": 0,
            "win_rate": 0, "avg_win_pct": 0, "avg_loss_pct": 0,
            "profit_loss_ratio": 0, "best_trade": None, "worst_trade": None,
        }

    # 过滤时间段内的交易
    if start_date or end_date:
        filtered = []
        for t in trades:
            ts = t.get("timestamp", "")[:10]
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date:
                continue
            # 只统计已完成的交易
            if t.get("status") == "closed" or t.get("exit_price") is not None:
                filtered.append(t)
    else:
        filtered = [t for t in trades if t.get("status") == "closed" or t.get("exit_price") is not None]

    if not filtered:
        return {"trade_count": 0, "win_count": 0, "loss_count": 0, "win_rate": 0,
                "avg_win_pct": 0, "avg_loss_pct": 0, "profit_loss_ratio": 0,
                "best_trade": None, "worst_trade": None}

    # 计算每笔盈亏
    pnls = []
    for t in filtered:
        if t["action"] == "BUY" and t.get("exit_price"):
            entry = t["price"]
            exit_p = t["exit_price"]
            pnl_pct = (exit_p - entry) / entry * 100
            pnls.append({
                "ticker": t["ticker"],
                "name": t.get("name", ""),
                "pnl_pct": round(pnl_pct, 2),
                "entry_date": t.get("timestamp", "")[:10],
            })
        elif t["action"] == "SELL":
            # SELL 记录需要匹配对应的 BUY
            pass

    # 简化：只从有 exit_price 的 BUY 记录统计
    if not pnls:
        # fallback: 计算所有交易
        pass

    wins = [p for p in pnls if p["pnl_pct"] > 0]
    losses = [p for p in pnls if p["pnl_pct"] <= 0]

    win_count = len(wins)
    loss_count = len(losses)
    total = win_count + loss_count
    win_rate = win_count / total * 100 if total > 0 else 0

    avg_win = sum(p["pnl_pct"] for p in wins) / win_count if win_count > 0 else 0
    avg_loss = abs(sum(p["pnl_pct"] for p in losses) / loss_count) if loss_count > 0 else 0
    pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    best = max(pnls, key=lambda x: x["pnl_pct"]) if pnls else None
    worst = min(pnls, key=lambda x: x["pnl_pct"]) if pnls else None

    return {
        "trade_count": total,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_loss_ratio": round(pl_ratio, 2),
        "best_trade": best,
        "worst_trade": worst,
    }


# ── 周报生成 ──────────────────────────────────────────────

def generate_weekly_report(output_dir: str = None) -> dict:
    """生成本周周报 .md"""
    if output_dir is None:
        output_dir = os.getcwd()

    account, positions, trades, tracker = _load_all()

    today = datetime.now()
    # 本周一
    monday = today - timedelta(days=today.weekday())
    # 上周日
    last_sunday = monday - timedelta(days=1)
    # 本周一的上周一（用于计算基准）
    week_start = monday.strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")

    # 计算账户概况
    market_value = sum(p["shares"] * p["current_price"] for p in positions)
    total_asset = account["cash"] + market_value
    initial = account["initial_capital"]
    cumulative_return = (total_asset / initial - 1) * 100 if initial > 0 else 0

    # 找上周快照计算本周收益
    snapshots = tracker.get("daily_snapshots", [])
    week_snapshot = None
    for snap in reversed(snapshots):
        if snap["date"] < week_start and not week_snapshot:
            week_snapshot = snap
            break
    if week_snapshot:
        begin_asset = week_snapshot["total_asset"]
        week_return = (total_asset - begin_asset) / begin_asset * 100 if begin_asset > 0 else 0
    else:
        begin_asset = total_asset
        week_return = 0

    # 本周收益 = 当前资产 vs 上周五收盘资产
    # (日快照记录了每日总资产)

    # 基准对比
    benchmark = _get_benchmark_return(monday.strftime("%Y-%m-%d"), week_end)

    # 本周交易
    week_trades = []
    for t in trades:
        ts = t.get("timestamp", "")[:10]
        if week_start <= ts <= week_end:
            week_trades.append(t)

    # 绩效计算
    perf = _calc_performance(trades)

    # 行业暴露
    industries = {}
    for p in positions:
        ind = p.get("industry") or "未分类"
        if ind not in industries:
            industries[ind] = {"mv": 0, "pnl": 0}
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        industries[ind]["mv"] += mv
        industries[ind]["pnl"] += (mv - cost)

    # ── 周报编号 ──
    iso = today.isocalendar()
    week_label = f"{iso[0]}-W{iso[1]:02d}"

    # ── 构建 Markdown ──
    lines = []
    lines.append("---")
    lines.append(f"date: {today.strftime('%Y-%m-%d')}")
    lines.append("type: weekly-report")
    lines.append(f"name: 模拟盘周报 ({week_label})")
    lines.append("code: N/A")
    lines.append("engine: compass-trader v1.0.0")
    lines.append("---")
    lines.append("")
    lines.append(f"## 模拟盘周报 ({week_label})")
    lines.append("")
    lines.append("**账户概况**：")
    lines.append(f"- 期初资产：¥{begin_asset:,.0f} | 期末资产：¥{total_asset:,.0f}")
    lines.append(f"- 本周收益：{week_return:+.2f}% | 累计收益：{cumulative_return:+.2f}%")
    lines.append(f"- 持仓数量：{len(positions)} 只 | 现金比例：{account['cash']/total_asset*100:.1f}%" if total_asset > 0 else "- 现金比例：100%")
    lines.append("")

    if benchmark.get("return_pct") is not None:
        excess = week_return - benchmark["return_pct"]
        lines.append(f"**vs 基准**：")
        lines.append(f"- 沪深300同期：{benchmark['return_pct']:+.2f}% → 超额收益：{excess:+.2f}%")
        lines.append("")

    lines.append("**胜率分析**：")
    lines.append(f"- 本周交易：{len(week_trades)} 笔 | 累计交易：{perf['trade_count']} 笔")
    lines.append(f"- 盈利次数：{perf['win_count']} | 胜率：{perf['win_rate']}%")
    lines.append(f"- 平均盈利：{perf['avg_win_pct']:+.2f}% | 平均亏损：{perf['avg_loss_pct']:+.2f}%")
    lines.append(f"- 盈亏比：{perf['profit_loss_ratio']}")
    lines.append("")

    lines.append("**当前持仓**：")
    if positions:
        lines.append("| 标的 | 成本价 | 现价 | 浮动盈亏 | 占比 | 持有天数 |")
        lines.append("|------|--------|------|---------|------|---------|")
        for p in positions:
            mv = p["shares"] * p["current_price"]
            pnl = (p["current_price"] - p["avg_cost"]) / p["avg_cost"] * 100
            weight = mv / total_asset * 100 if total_asset > 0 else 0
            days = (today - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days if p.get("entry_date") else "?"
            lines.append(f"| {p['name']}({p['ticker']}) | ¥{p['avg_cost']:.2f} | ¥{p['current_price']:.2f} | {pnl:+.2f}% | {weight:.1f}% | {days}天 |")
    else:
        lines.append("（空仓）")
    lines.append("")

    lines.append("**本周操作**：")
    if week_trades:
        lines.append("| 日期 | 操作 | 标的 | 价格 | 数量 | 理由 |")
        lines.append("|------|------|------|------|------|------|")
        for t in week_trades:
            lines.append(f"| {t['timestamp'][:10]} | {t['action']} | {t.get('name','')}({t['ticker']}) | ¥{t['price']} | {t['shares']}股 | {t.get('reason','')} |")
    else:
        lines.append("（本周无操作）")
    lines.append("")

    lines.append("**行业暴露**：")
    if industries:
        lines.append("| 行业 | 市值 | 占比 | 浮动盈亏 |")
        lines.append("|------|------|------|---------|")
        for ind, data in industries.items():
            weight = data["mv"] / total_asset * 100 if total_asset > 0 else 0
            lines.append(f"| {ind} | ¥{data['mv']:,.0f} | {weight:.1f}% | ¥{data['pnl']:+,.0f} |")
    else:
        lines.append("（空仓）")
    lines.append("")

    lines.append("**AI反思**：")
    lines.append("<!-- TODO: AI review — 请 Claude 根据以上数据撰写反思 -->")
    lines.append("- 做得好的：[具体案例]")
    lines.append("- 需要改进的：[具体案例]")
    lines.append("- 下周关注：[具体标的/事件]")
    lines.append("")
    lines.append("---")
    lines.append("*本报告由 Compass Trader 自动生成。模拟盘数据，不构成投资建议。*")

    # ── 写入文件 ──
    filename = f"周报-{week_label}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "success": True,
        "file": filepath,
        "filename": filename,
        "week": week_label,
        "summary": {
            "total_asset": round(total_asset, 2),
            "week_return_pct": round(week_return, 2),
            "cumulative_return_pct": round(cumulative_return, 2),
            "position_count": len(positions),
        }
    }


# ── 月报生成 ──────────────────────────────────────────────

def generate_monthly_report(output_dir: str = None) -> dict:
    """生成本月月报 .md"""
    if output_dir is None:
        output_dir = os.getcwd()

    account, positions, trades, tracker = _load_all()

    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    month_end = today.strftime("%Y-%m-%d")
    month_label = today.strftime("%Y%m")

    market_value = sum(p["shares"] * p["current_price"] for p in positions)
    total_asset = account["cash"] + market_value
    initial = account["initial_capital"]
    cumulative_return = (total_asset / initial - 1) * 100 if initial > 0 else 0

    # 月初资产（从快照中找）
    snapshots = tracker.get("daily_snapshots", [])
    month_first_snap = None
    for snap in snapshots:
        if snap["date"] >= month_start and not month_first_snap:
            month_first_snap = snap
            break
    if month_first_snap:
        begin_asset = month_first_snap["total_asset"]
        month_return = (total_asset - begin_asset) / begin_asset * 100 if begin_asset > 0 else 0
    else:
        begin_asset = total_asset
        month_return = 0

    benchmark = _get_benchmark_return(month_start, month_end)
    perf = _calc_performance(trades)

    # 本月交易
    month_trades = [t for t in trades if t.get("timestamp", "")[:7] == today.strftime("%Y-%m")]

    # 行业暴露
    industries = {}
    for p in positions:
        ind = p.get("industry") or "未分类"
        if ind not in industries:
            industries[ind] = {"mv": 0, "pnl": 0}
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        industries[ind]["mv"] += mv
        industries[ind]["pnl"] += (mv - cost)

    # ── 构建 Markdown ──
    lines = []
    lines.append("---")
    lines.append(f"date: {today.strftime('%Y-%m-%d')}")
    lines.append("type: monthly-report")
    lines.append(f"name: 模拟盘月报 ({month_label})")
    lines.append("code: N/A")
    lines.append("engine: compass-trader v1.0.0")
    lines.append("---")
    lines.append("")
    lines.append(f"## 模拟盘月报 ({month_label})")
    lines.append("")
    lines.append("**账户概况**：")
    lines.append(f"- 月初资产：¥{begin_asset:,.0f} | 月末资产：¥{total_asset:,.0f}")
    lines.append(f"- 本月收益：{month_return:+.2f}% | 累计收益：{cumulative_return:+.2f}%")
    lines.append(f"- 持仓数量：{len(positions)} 只 | 现金比例：{account['cash']/total_asset*100:.1f}%" if total_asset > 0 else "- 现金比例：100%")
    lines.append("")

    if benchmark.get("return_pct") is not None:
        excess = month_return - benchmark["return_pct"]
        lines.append(f"**vs 基准**：")
        lines.append(f"- 沪深300同期：{benchmark['return_pct']:+.2f}% → 超额收益：{excess:+.2f}%")
        lines.append("")

    lines.append("**月度操作汇总**：")
    lines.append(f"- 本月交易：{len(month_trades)} 笔 | 累计交易：{perf['trade_count']} 笔")
    lines.append(f"- 盈利次数：{perf['win_count']} | 胜率：{perf['win_rate']}%")
    lines.append(f"- 盈亏比：{perf['profit_loss_ratio']}")
    if perf["best_trade"]:
        lines.append(f"- 最佳操作：{perf['best_trade']['name']} {perf['best_trade']['pnl_pct']:+.2f}%")
    if perf["worst_trade"]:
        lines.append(f"- 最差操作：{perf['worst_trade']['name']} {perf['worst_trade']['pnl_pct']:+.2f}%")
    lines.append("")

    lines.append("**行业暴露**：")
    if industries:
        lines.append("| 行业 | 市值 | 占比 | 浮动盈亏 |")
        lines.append("|------|------|------|---------|")
        for ind, data in industries.items():
            weight = data["mv"] / total_asset * 100 if total_asset > 0 else 0
            lines.append(f"| {ind} | ¥{data['mv']:,.0f} | {weight:.1f}% | ¥{data['pnl']:+,.0f} |")
    else:
        lines.append("（空仓）")
    lines.append("")

    lines.append("**月度反思**：")
    lines.append("<!-- TODO: AI review — 请 Claude 根据以上数据撰写月度反思 -->")
    lines.append("- 策略执行一致性：[自评]")
    lines.append("- 情绪干扰：[有无冲动交易]")
    lines.append("- 下月计划：[调整方向]")
    lines.append("")
    lines.append("---")
    lines.append("*本报告由 Compass Trader 自动生成。模拟盘数据，不构成投资建议。*")

    # ── 写入文件 ──
    filename = f"月报-{month_label}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "success": True,
        "file": filepath,
        "filename": filename,
        "month": month_label,
        "summary": {
            "total_asset": round(total_asset, 2),
            "month_return_pct": round(month_return, 2),
            "cumulative_return_pct": round(cumulative_return, 2),
            "position_count": len(positions),
        }
    }


# ── 交易记录 ──────────────────────────────────────────────

def generate_trade_record(trade_id: str, output_dir: str = None) -> dict:
    """生成单笔交易记录 .md"""
    if output_dir is None:
        output_dir = os.getcwd()

    trades = _read_json("trades.json")
    if not trades:
        return {"error": "无交易记录"}

    trade = None
    for t in trades.get("trades", []):
        if t["id"] == trade_id:
            trade = t
            break

    if not trade:
        return {"error": f"未找到交易 {trade_id}"}

    today = datetime.now()
    filename = f"交易-{trade['name']}-{today.strftime('%Y%m%d-%H%M%S')}.md"
    filepath = os.path.join(output_dir, filename)

    lines = []
    lines.append("---")
    lines.append(f"date: {today.strftime('%Y-%m-%d')}")
    lines.append("type: trade-record")
    lines.append(f"name: 交易记录-{trade['name']}-{trade['id']}")
    lines.append(f"code: {trade['ticker']}")
    lines.append("engine: compass-trader v1.0.0")
    lines.append("---")
    lines.append("")
    lines.append(f"## 交易记录：{trade['action']} {trade['name']}({trade['ticker']})")
    lines.append("")
    lines.append(f"- **交易ID**：{trade['id']}")
    lines.append(f"- **时间**：{trade['timestamp']}")
    lines.append(f"- **操作**：{trade['action']}")
    lines.append(f"- **标的**：{trade['name']} ({trade['ticker']})")
    lines.append(f"- **数量**：{trade['shares']} 股")
    lines.append(f"- **价格**：¥{trade['price']:.2f}")
    lines.append(f"- **金额**：¥{trade.get('amount', trade['shares'] * trade['price']):,.2f}")
    lines.append(f"- **置信度**：{trade.get('confidence', 'N/A')}")
    if trade.get("stop_loss"):
        lines.append(f"- **止损价**：¥{trade['stop_loss']:.2f}")
    if trade.get("take_profit"):
        lines.append(f"- **止盈价**：¥{trade['take_profit']:.2f}")
    lines.append(f"- **理由**：{trade.get('reason', 'N/A')}")
    lines.append(f"- **状态**：{trade.get('status', 'N/A')}")
    lines.append("")
    lines.append("**AI复盘**：")
    lines.append("<!-- TODO: AI review -->")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"success": True, "file": filepath, "filename": filename}


# ── 摘要（不写文件）─ ─────────────────────────────────────

def generate_summary() -> dict:
    """生成账户摘要（不写文件，仅输出到终端）"""
    account, positions, trades, tracker = _load_all()

    market_value = sum(p["shares"] * p["current_price"] for p in positions)
    total_asset = account["cash"] + market_value
    initial = account["initial_capital"]
    cumulative_return = (total_asset / initial - 1) * 100 if initial > 0 else 0

    # 持仓明细
    pos_details = []
    for p in positions:
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        pnl = mv - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        pos_details.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "shares": p["shares"],
            "avg_cost": p["avg_cost"],
            "current_price": p["current_price"],
            "market_value": round(mv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_pct": round(mv / total_asset * 100, 2) if total_asset > 0 else 0,
        })

    return {
        "account": {
            "initial_capital": initial,
            "total_asset": round(total_asset, 2),
            "cash": round(account["cash"], 2),
            "market_value": round(market_value, 2),
            "cumulative_return_pct": round(cumulative_return, 2),
        },
        "positions": pos_details,
        "position_count": len(positions),
        "trade_count": len(trades),
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── CLI 入口 ──────────────────────────────────────────────

def _cli():
    if len(sys.argv) < 2:
        print("Compass Trader · 绩效报告生成器")
        print("用法:")
        print("  python3 scripts/reporter.py weekly [输出目录]")
        print("  python3 scripts/reporter.py monthly [输出目录]")
        print("  python3 scripts/reporter.py trade <trade_id> [输出目录]")
        print("  python3 scripts/reporter.py summary")
        return

    cmd = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else os.getcwd()
    result = None

    if cmd == "weekly":
        result = generate_weekly_report(output_dir)
    elif cmd == "monthly":
        result = generate_monthly_report(output_dir)
    elif cmd == "trade" and len(sys.argv) >= 3:
        result = generate_trade_record(sys.argv[2], output_dir)
    elif cmd == "summary":
        result = generate_summary()
    else:
        result = {"error": f"未知命令或参数不足: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
