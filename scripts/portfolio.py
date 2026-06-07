#!/usr/bin/env python3
"""
Compass Trader · 持仓管理与交易执行模块
模拟交易执行引擎，基于本地 JSON 文件管理持仓和交易记录。

用法：
  python3 scripts/portfolio.py buy <ticker> <name> <shares> <price> <reason> [confidence] [stop_loss] [take_profit]
  python3 scripts/portfolio.py sell <ticker> <price> <reason>
  python3 scripts/portfolio.py summary                          # 账户概览
  python3 scripts/portfolio.py positions                       # 持仓明细
  python3 scripts/portfolio.py trades                           # 交易历史
  python3 scripts/portfolio.py snapshot                         # 记录当日快照
  python3 scripts/portfolio.py update-price <ticker> <price>    # 更新现价
  python3 scripts/portfolio.py update-all-prices                # 批量更新持仓现价
  python3 scripts/portfolio.py industry                         # 行业暴露分析
  python3 scripts/portfolio.py init [初始资金]                  # 初始化/重置账户
"""

import sys
import json
import os
from datetime import datetime, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")

# 添加 scripts 目录到 path 以便导入 market_data
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))


# ── 数据读写 ──────────────────────────────────────────────

def _read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_account() -> dict:
    """加载账户数据"""
    return _read_json("account.json") or {
        "initial_capital": 1000000, "cash": 1000000,
        "created_at": datetime.now().strftime("%Y-%m-%d"), "currency": "CNY"
    }


def load_positions() -> list:
    """加载当前持仓列表"""
    data = _read_json("positions.json")
    return data.get("positions", []) if data else []


def load_trades() -> list:
    """加载交易历史"""
    data = _read_json("trades.json")
    return data.get("trades", []) if data else []


def _save_positions(positions):
    data = {
        "positions": positions,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _write_json("positions.json", data)


def _save_trades(trades):
    _write_json("trades.json", {"trades": trades})


def _save_account(account):
    account["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _write_json("account.json", account)


# ── 账户初始化 ────────────────────────────────────────────

def init_account(initial_capital: float = 1000000):
    """初始化/重置模拟账户"""
    account = {
        "initial_capital": initial_capital,
        "cash": initial_capital,
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "currency": "CNY",
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_account(account)
    _save_positions([])
    _save_trades([])

    # 重置 tracker
    _write_json("tracker.json", {"weekly": [], "monthly": [], "daily_snapshots": []})

    return {"success": True, "message": f"账户已初始化，初始资金: ¥{initial_capital:,.0f}"}


# ── 交易执行 ──────────────────────────────────────────────

def execute_trade(action: str, ticker: str, name: str, shares: int,
                  price: float, reason: str = "", confidence: str = "medium",
                  stop_loss: float = None, take_profit: float = None,
                  industry: str = "") -> dict:
    """
    执行模拟交易。
    action: BUY / SELL
    返回交易记录
    """
    action = action.upper()
    if action not in ("BUY", "SELL"):
        return {"error": f"不支持的操作: {action}，仅支持 BUY / SELL"}

    account = load_account()
    positions = load_positions()
    trades = load_trades()

    total_amount = shares * price
    trade_id = f"TRD-{datetime.now().strftime('%Y%m%d')}-{len(trades)+1:03d}"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    if action == "BUY":
        # 检查现金
        if total_amount > account["cash"]:
            return {
                "error": f"现金不足！需要 ¥{total_amount:,.2f}，可用 ¥{account['cash']:,.2f}",
                "shortfall": round(total_amount - account["cash"], 2),
            }

        # 扣减现金
        account["cash"] -= total_amount
        _save_account(account)

        # 更新或新增持仓
        existing = next((p for p in positions if p["ticker"] == ticker), None)
        if existing:
            old_cost = existing["avg_cost"] * existing["shares"]
            new_cost = old_cost + total_amount
            existing["shares"] += shares
            existing["avg_cost"] = round(new_cost / existing["shares"], 2)
        else:
            positions.append({
                "ticker": ticker,
                "name": name,
                "shares": shares,
                "avg_cost": price,
                "current_price": price,
                "industry": industry,
                "entry_date": datetime.now().strftime("%Y-%m-%d"),
                "stop_loss": stop_loss or round(price * 0.92, 2),
                "take_profit": take_profit or round(price * 1.16, 2),
            })
        _save_positions(positions)

    elif action == "SELL":
        # 检查持仓
        existing = next((p for p in positions if p["ticker"] == ticker), None)
        if not existing:
            return {"error": f"未持有 {ticker}，无法卖出"}
        if shares > existing["shares"]:
            return {"error": f"持仓不足！持有 {existing['shares']} 股，尝试卖出 {shares} 股"}

        # 增加现金
        account["cash"] += total_amount
        _save_account(account)

        # 更新或删除持仓
        if shares == existing["shares"]:
            positions.remove(existing)
        else:
            existing["shares"] -= shares
        _save_positions(positions)

        # 更新对应的开仓交易状态
        # (简化逻辑：卖出时把最早的 open 交易标记为 closed)
        for t in trades:
            if t["ticker"] == ticker and t["status"] == "open":
                t["status"] = "closed"
                t["exit_date"] = datetime.now().strftime("%Y-%m-%d")
                t["exit_price"] = price
                break

    # 记录交易
    trade_record = {
        "id": trade_id,
        "timestamp": now,
        "action": action,
        "ticker": ticker,
        "name": name,
        "shares": shares,
        "price": price,
        "amount": round(total_amount, 2),
        "reason": reason,
        "confidence": confidence,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "status": "open" if action == "BUY" else "closed",
    }
    trades.append(trade_record)
    _save_trades(trades)

    return {
        "success": True,
        "trade": trade_record,
        "account_snapshot": get_portfolio_summary(),
    }


def close_position(ticker: str, price: float, reason: str = "") -> dict:
    """平仓某只股票的全部持仓"""
    positions = load_positions()
    existing = next((p for p in positions if p["ticker"] == ticker), None)
    if not existing:
        return {"error": f"未持有 {ticker}"}

    return execute_trade("SELL", ticker, existing["name"], existing["shares"],
                         price, reason, "medium", None, None, existing.get("industry", ""))


# ── 更新价格 ──────────────────────────────────────────────

def update_position_price(ticker: str, price: float) -> dict:
    """手动更新单只持仓的现价"""
    positions = load_positions()
    for p in positions:
        if p["ticker"] == ticker:
            p["current_price"] = price
            _save_positions(positions)
            return {"success": True, "ticker": ticker, "price": price}
    return {"error": f"未持有 {ticker}"}


def update_all_prices() -> dict:
    """从新浪 API 批量更新所有持仓现价"""
    try:
        from market_data import batch_quotes
    except ImportError:
        return {"error": "无法导入 market_data 模块"}

    positions = load_positions()
    if not positions:
        return {"message": "当前无持仓，无需更新"}

    tickers = [p["ticker"] for p in positions]
    quotes = batch_quotes(tickers)

    updated = []
    failed = []
    for q in quotes:
        if "error" in q:
            failed.append(q)
            continue
        ticker = q["ticker"]
        price = q.get("price")
        if price:
            for p in positions:
                if p["ticker"] == ticker:
                    p["current_price"] = price
                    updated.append({"ticker": ticker, "name": q.get("name"), "price": price})

    _save_positions(positions)
    return {
        "success": True,
        "updated": updated,
        "failed": failed,
        "total": len(tickers),
    }


# ── 汇总分析 ──────────────────────────────────────────────

def get_portfolio_summary() -> dict:
    """获取账户概况"""
    account = load_account()
    positions = load_positions()

    market_value = sum(p["shares"] * p["current_price"] for p in positions)
    total_cost = sum(p["shares"] * p["avg_cost"] for p in positions)
    total_asset = account["cash"] + market_value
    total_pnl = market_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    cumulative_return = (total_asset / account["initial_capital"] - 1) * 100

    return {
        "initial_capital": account["initial_capital"],
        "total_asset": round(total_asset, 2),
        "cash": round(account["cash"], 2),
        "market_value": round(market_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "cumulative_return_pct": round(cumulative_return, 2),
        "position_count": len(positions),
        "cash_ratio": round(account["cash"] / total_asset, 4) if total_asset > 0 else 1,
        "currency": account["currency"],
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def get_positions_detail() -> dict:
    """获取持仓明细（含浮动盈亏）"""
    positions = load_positions()
    details = []
    for p in positions:
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        pnl = mv - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        details.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "shares": p["shares"],
            "avg_cost": p["avg_cost"],
            "current_price": p["current_price"],
            "market_value": round(mv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "industry": p.get("industry", ""),
            "entry_date": p.get("entry_date", ""),
            "stop_loss": p.get("stop_loss"),
            "take_profit": p.get("take_profit"),
            "days_held": (datetime.now() - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days if p.get("entry_date") else None,
        })

    total_mv = sum(d["market_value"] for d in details)
    return {
        "positions": details,
        "count": len(details),
        "total_market_value": round(total_mv, 2),
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def get_industry_exposure() -> dict:
    """获取行业暴露分析"""
    positions = load_positions()
    total = load_account()["initial_capital"]

    industries = {}
    for p in positions:
        ind = p.get("industry") or "未分类"
        if ind not in industries:
            industries[ind] = {"market_value": 0, "pnl": 0, "tickers": []}
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        industries[ind]["market_value"] += mv
        industries[ind]["pnl"] += (mv - cost)
        industries[ind]["tickers"].append(p["ticker"])

    result = []
    for ind, data in industries.items():
        result.append({
            "industry": ind,
            "market_value": round(data["market_value"], 2),
            "weight": round(data["market_value"] / total, 4),
            "pnl": round(data["pnl"], 2),
            "tickers": data["tickers"],
        })

    return {"exposure": result, "total": total}


# ── 快照 ──────────────────────────────────────────────────

def snapshot_daily() -> dict:
    """记录当日账户快照到 tracker.json"""
    summary = get_portfolio_summary()
    tracker = _read_json("tracker.json") or {"weekly": [], "monthly": [], "daily_snapshots": []}

    today = datetime.now().strftime("%Y-%m-%d")

    # 避免同一天重复记录
    if tracker["daily_snapshots"] and tracker["daily_snapshots"][-1]["date"] == today:
        tracker["daily_snapshots"][-1] = {
            "date": today,
            "total_asset": summary["total_asset"],
            "cash": summary["cash"],
            "market_value": summary["market_value"],
            "cumulative_return_pct": summary["cumulative_return_pct"],
        }
    else:
        tracker["daily_snapshots"].append({
            "date": today,
            "total_asset": summary["total_asset"],
            "cash": summary["cash"],
            "market_value": summary["market_value"],
            "cumulative_return_pct": summary["cumulative_return_pct"],
        })

    _write_json("tracker.json", tracker)
    return {"success": True, "date": today, "snapshot": tracker["daily_snapshots"][-1]}


# ── CLI 入口 ──────────────────────────────────────────────

def _cli():
    if len(sys.argv) < 2:
        print("Compass Trader · 持仓管理与交易执行")
        print("用法:")
        print("  python3 scripts/portfolio.py init [资金]")
        print("  python3 scripts/portfolio.py buy <ticker> <name> <shares> <price> [reason] [confidence] [stop] [profit] [industry]")
        print("  python3 scripts/portfolio.py sell <ticker> <price> [reason]")
        print("  python3 scripts/portfolio.py close <ticker> <price> [reason]")
        print("  python3 scripts/portfolio.py summary")
        print("  python3 scripts/portfolio.py positions")
        print("  python3 scripts/portfolio.py trades")
        print("  python3 scripts/portfolio.py industry")
        print("  python3 scripts/portfolio.py snapshot")
        print("  python3 scripts/portfolio.py update-price <ticker> <price>")
        print("  python3 scripts/portfolio.py update-all-prices")
        return

    cmd = sys.argv[1]
    result = None

    if cmd == "init":
        capital = float(sys.argv[2]) if len(sys.argv) >= 3 else 1000000
        result = init_account(capital)

    elif cmd == "buy" and len(sys.argv) >= 6:
        ticker = sys.argv[2]
        name = sys.argv[3]
        shares = int(sys.argv[4])
        price = float(sys.argv[5])
        reason = sys.argv[6] if len(sys.argv) >= 7 else ""
        confidence = sys.argv[7] if len(sys.argv) >= 8 else "medium"
        stop_loss = float(sys.argv[8]) if len(sys.argv) >= 9 else None
        take_profit = float(sys.argv[9]) if len(sys.argv) >= 10 else None
        industry = sys.argv[10] if len(sys.argv) >= 11 else ""
        result = execute_trade("BUY", ticker, name, shares, price,
                               reason, confidence, stop_loss, take_profit, industry)

    elif cmd == "sell" and len(sys.argv) >= 4:
        ticker = sys.argv[2]
        price = float(sys.argv[3])
        reason = sys.argv[4] if len(sys.argv) >= 5 else ""
        result = close_position(ticker, price, reason)

    elif cmd == "close" and len(sys.argv) >= 4:
        ticker = sys.argv[2]
        price = float(sys.argv[3])
        reason = sys.argv[4] if len(sys.argv) >= 5 else ""
        result = close_position(ticker, price, reason)

    elif cmd == "summary":
        result = get_portfolio_summary()

    elif cmd == "positions":
        result = get_positions_detail()

    elif cmd == "trades":
        result = {"trades": load_trades()}

    elif cmd == "industry":
        result = get_industry_exposure()

    elif cmd == "snapshot":
        result = snapshot_daily()

    elif cmd == "update-price" and len(sys.argv) >= 4:
        result = update_position_price(sys.argv[2], float(sys.argv[3]))

    elif cmd == "update-all-prices":
        result = update_all_prices()

    else:
        result = {"error": f"未知命令或参数不足: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
