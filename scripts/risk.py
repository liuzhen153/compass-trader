#!/usr/bin/env python3
"""
Compass Trader · 仓位与风险管理模块
凯利公式、仓位计算、止损止盈建议。

用法：
  python3 scripts/risk.py kelly <胜率> <盈亏比>              # 凯利公式仓位
  python3 scripts/risk.py size <总资产> <股价> <风险%> <止损%> # 建议股数
  python3 scripts/risk.py stop <入场价> [ATR] [方法]          # 止损价
  python3 scripts/risk.py profit <入场价> <止损价> [盈亏比]    # 止盈价
  python3 scripts/risk.py check <ticker> <行业>              # 检查仓位上限
"""

import sys
import json
import os

# 数据目录（相对于 skill 根目录）
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")


# ── 默认风控参数 ──────────────────────────────────────────

DEFAULT_MAX_SINGLE = 0.20      # 单只股票上限 20%
DEFAULT_MAX_INDUSTRY = 0.40    # 单行业上限 40%
DEFAULT_MIN_CASH = 0.10        # 最低现金 10%
DEFAULT_HARD_STOP = -0.08      # 硬止损 -8%
DEFAULT_TIME_STOP_DAYS = 30    # 时间止损 30 天
DEFAULT_RR_RATIO = 2.0         # 默认盈亏比 2:1


# ── 凯利公式 ──────────────────────────────────────────────

def kelly_position(win_prob: float, win_loss_ratio: float,
                   fractional: float = 0.5) -> dict:
    """
    凯利公式：f = (b*p - q) / b
    - win_prob: 胜率 p (0~1)
    - win_loss_ratio: 盈亏比 b (盈利/亏损)
    - fractional: 分数凯利系数（默认 0.5 = 半凯利，降低波动）

    返回: {full_kelly, fractional_kelly, half_kelly, suggestion}
    """
    if win_prob <= 0 or win_prob > 1:
        return {"error": "胜率应在 (0, 1] 之间"}
    if win_loss_ratio <= 0:
        return {"error": "盈亏比应 > 0"}

    q = 1 - win_prob
    f_full = max(0, (win_loss_ratio * win_prob - q) / win_loss_ratio)
    f_half = f_full * 0.5
    f_frac = f_full * fractional

    # 建议措辞
    if f_full <= 0:
        suggestion = "凯利值为负，不建议参与"
    elif f_full < 0.05:
        suggestion = f"凯利值偏低 ({f_full:.1%})，建议小仓位试探"
    elif f_full < 0.15:
        suggestion = f"凯利值适中 ({f_full:.1%})，建议 {f_frac:.1%} (分数凯利)"
    elif f_full < 0.25:
        suggestion = f"凯利值较高 ({f_full:.1%})，建议 {f_frac:.1%} (分数凯利)，注意上限"
    else:
        suggestion = f"凯利值很高 ({f_full:.1%})，但建议不超过单只上限 {DEFAULT_MAX_SINGLE:.0%}"

    return {
        "full_kelly": round(f_full, 4),
        "half_kelly": round(f_half, 4),
        "fractional_kelly": round(f_frac, 4),
        "fractional_coeff": fractional,
        "suggestion": suggestion,
    }


# ── 仓位计算 ──────────────────────────────────────────────

def position_size(account_total: float, price: float,
                  risk_pct: float = 0.02,
                  stop_loss_pct: float = 0.08) -> dict:
    """
    风险百分比法计算建议股数。
    公式：shares = (account * risk_pct) / (price * stop_loss_pct)

    - account_total: 账户总资产
    - price: 当前股价
    - risk_pct: 单笔交易愿意承担的最大亏损比例（默认 2%）
    - stop_loss_pct: 止损距离（默认 8%，即买入价的 92%）

    返回: {shares, amount, risk_amount, max_shares_by_single_limit}
    """
    if account_total <= 0 or price <= 0:
        return {"error": "资产和股价必须 > 0"}

    risk_amount = account_total * risk_pct           # 单笔最大亏损金额
    per_share_risk = price * stop_loss_pct            # 每股风险
    shares = int(risk_amount / per_share_risk)         # 向下取整
    # 按 100 股（1手）取整
    shares = (shares // 100) * 100

    # 单只上限约束
    max_shares_by_single = int(account_total * DEFAULT_MAX_SINGLE / price)
    max_shares_by_single = (max_shares_by_single // 100) * 100

    if shares > max_shares_by_single:
        capped = True
        final_shares = max_shares_by_single
    else:
        capped = False
        final_shares = shares

    amount = final_shares * price
    position_pct = amount / account_total

    return {
        "shares": final_shares,
        "amount": round(amount, 2),
        "position_pct": round(position_pct, 4),
        "risk_amount": round(risk_amount, 2),
        "per_share_risk": round(per_share_risk, 2),
        "capped_by_single_limit": capped,
        "note": f"{'⚠️ 触达单只上限 ' + str(DEFAULT_MAX_SINGLE*100) + '%，已截断' if capped else '✅ 仓位在限制内'}",
    }


# ── 止损计算 ──────────────────────────────────────────────

def calculate_stop_loss(entry_price: float, atr: float = None,
                         method: str = "hard") -> dict:
    """
    计算止损价。
    - method='hard': 固定比例止损 (DEFAULT_HARD_STOP = -8%)
    - method='atr': ATR 倍数止损 (2倍 ATR)
    """
    if entry_price <= 0:
        return {"error": "入场价必须 > 0"}

    if method == "hard":
        stop_loss = round(entry_price * (1 + DEFAULT_HARD_STOP), 2)
        note = f"硬止损：入场价 {entry_price} × (1 {DEFAULT_HARD_STOP:.0%})"
    elif method == "atr" and atr and atr > 0:
        stop_loss = round(entry_price - 2 * atr, 2)
        note = f"ATR止损：入场价 {entry_price} - 2×ATR({atr})"
    elif method == "atr":
        stop_loss = round(entry_price * (1 + DEFAULT_HARD_STOP), 2)
        note = f"ATR 未知，回退到硬止损: {stop_loss}"
    else:
        stop_loss = round(entry_price * (1 + DEFAULT_HARD_STOP), 2)
        note = f"未知方法 '{method}'，使用硬止损"

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "stop_loss_pct": round((stop_loss - entry_price) / entry_price * 100, 2),
        "method": method,
        "note": note,
    }


# ── 止盈计算 ──────────────────────────────────────────────

def calculate_take_profit(entry_price: float, stop_loss: float = None,
                           rr_ratio: float = DEFAULT_RR_RATIO) -> dict:
    """
    基于盈亏比计算止盈价。
    公式：止盈价 = 入场价 + (入场价 - 止损价) × 盈亏比
    """
    if entry_price <= 0:
        return {"error": "入场价必须 > 0"}

    if stop_loss is None:
        stop_loss = round(entry_price * (1 + DEFAULT_HARD_STOP), 2)

    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0:
        return {"error": f"止损价 ({stop_loss}) 必须低于入场价 ({entry_price})"}

    take_profit = round(entry_price + risk_per_share * rr_ratio, 2)
    gain_pct = round((take_profit - entry_price) / entry_price * 100, 2)

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "take_profit_pct": gain_pct,
        "rr_ratio": rr_ratio,
        "risk_per_share": round(risk_per_share, 2),
        "reward_per_share": round(take_profit - entry_price, 2),
    }


# ── 仓位上限检查 ──────────────────────────────────────────

def _load_positions():
    """加载当前持仓"""
    pos_path = os.path.join(DATA_DIR, "positions.json")
    try:
        with open(pos_path, "r") as f:
            data = json.load(f)
            return data.get("positions", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _load_account():
    """加载账户"""
    acct_path = os.path.join(DATA_DIR, "account.json")
    try:
        with open(acct_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"initial_capital": 1000000, "cash": 1000000}


def max_position_check(ticker: str, industry: str = None,
                       max_single: float = DEFAULT_MAX_SINGLE,
                       max_industry: float = DEFAULT_MAX_INDUSTRY) -> dict:
    """
    检查新开仓是否超过单只/单行业上限。
    返回: {passed, checks: [{rule, current, limit, ok}], warnings}
    """
    positions = _load_positions()
    account = _load_account()
    total = account["initial_capital"]

    checks = []
    warnings = []

    # 1. 单只上限检查
    current_single = 0
    for p in positions:
        if p["ticker"] == ticker:
            current_single += p["shares"] * p["current_price"]
    single_pct = current_single / total
    single_ok = single_pct < max_single
    checks.append({
        "rule": f"单只上限 ≤ {max_single:.0%}",
        "current": round(single_pct, 4),
        "limit": max_single,
        "ok": single_ok,
    })
    if not single_ok:
        warnings.append(f"⚠️ {ticker} 已占 {single_pct:.1%}，超 {max_single:.0%} 上限")

    # 2. 行业上限检查
    if industry:
        current_industry = 0
        for p in positions:
            if p.get("industry") == industry:
                current_industry += p["shares"] * p["current_price"]
        industry_pct = current_industry / total
        industry_ok = industry_pct < max_industry
        checks.append({
            "rule": f"行业上限 ≤ {max_industry:.0%} (当前行业: {industry})",
            "current": round(industry_pct, 4),
            "limit": max_industry,
            "ok": industry_ok,
        })
        if not industry_ok:
            warnings.append(f"⚠️ {industry} 行业已占 {industry_pct:.1%}%，超 {max_industry:.0%} 上限")

    # 3. 现金下限检查
    cash_pct = account["cash"] / total
    min_cash_ok = cash_pct >= DEFAULT_MIN_CASH
    checks.append({
        "rule": f"现金下限 ≥ {DEFAULT_MIN_CASH:.0%}",
        "current": round(cash_pct, 4),
        "limit": DEFAULT_MIN_CASH,
        "ok": min_cash_ok,
    })
    if not min_cash_ok:
        warnings.append(f"⚠️ 现金仅剩 {cash_pct:.1%}%，低于 {DEFAULT_MIN_CASH:.0%} 下限")

    return {
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "warnings": warnings,
    }


# ── 时间止损检查 ──────────────────────────────────────────

def check_time_stop(trades: list = None) -> list:
    """
    检查是否有持仓超过时间止损（30天）。
    返回: [{ticker, name, entry_date, days_held, should_reduce}]
    """
    from datetime import datetime

    if trades is None:
        trades_path = os.path.join(DATA_DIR, "trades.json")
        try:
            with open(trades_path, "r") as f:
                trades = json.load(f).get("trades", [])
        except (FileNotFoundError, json.JSONDecodeError):
            trades = []

    today = datetime.now()
    alerts = []
    for t in trades:
        if t.get("status") != "open":
            continue
        entry_date = datetime.strptime(t["entry_date"], "%Y-%m-%d") if t.get("entry_date") else None
        if not entry_date:
            continue
        days_held = (today - entry_date).days
        if days_held >= DEFAULT_TIME_STOP_DAYS:
            # 检查是否有盈利（从positions获取current_price）
            alerts.append({
                "ticker": t["ticker"],
                "name": t.get("name", ""),
                "entry_date": t["entry_date"],
                "days_held": days_held,
                "should_reduce": True,
                "reason": f"持仓 {days_held} 天超过 {DEFAULT_TIME_STOP_DAYS} 天时间止损线",
            })
    return alerts


# ── CLI 入口 ──────────────────────────────────────────────

def _cli():
    if len(sys.argv) < 2:
        print("Compass Trader · 仓位与风险管理")
        print("用法:")
        print("  python3 scripts/risk.py kelly <胜率> <盈亏比>")
        print("  python3 scripts/risk.py size <总资产> <股价> [风险%] [止损%]")
        print("  python3 scripts/risk.py stop <入场价> [ATR] [方法]")
        print("  python3 scripts/risk.py profit <入场价> <止损价> [盈亏比]")
        print("  python3 scripts/risk.py check <ticker> [行业]")
        print("  python3 scripts/risk.py time-stop")
        return

    cmd = sys.argv[1]
    result = None

    if cmd == "kelly" and len(sys.argv) >= 4:
        result = kelly_position(float(sys.argv[2]), float(sys.argv[3]))
    elif cmd == "size" and len(sys.argv) >= 4:
        risk_pct = float(sys.argv[4]) if len(sys.argv) >= 5 else 0.02
        stop_pct = float(sys.argv[5]) if len(sys.argv) >= 6 else 0.08
        result = position_size(float(sys.argv[2]), float(sys.argv[3]), risk_pct, stop_pct)
    elif cmd == "stop" and len(sys.argv) >= 3:
        entry = float(sys.argv[2])
        atr = float(sys.argv[3]) if len(sys.argv) >= 4 else None
        method = sys.argv[4] if len(sys.argv) >= 5 else "hard"
        result = calculate_stop_loss(entry, atr, method)
    elif cmd == "profit" and len(sys.argv) >= 4:
        entry = float(sys.argv[2])
        stop = float(sys.argv[3])
        rr = float(sys.argv[4]) if len(sys.argv) >= 5 else DEFAULT_RR_RATIO
        result = calculate_take_profit(entry, stop, rr)
    elif cmd == "check" and len(sys.argv) >= 3:
        industry = sys.argv[3] if len(sys.argv) >= 4 else None
        result = max_position_check(sys.argv[2], industry)
    elif cmd == "time-stop":
        result = check_time_stop()
    else:
        result = {"error": f"未知命令或参数不足: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
