#!/bin/bash
# Compass Trader · 全模块验证脚本
# 验证所有 Python 脚本可正常导入、关键函数可调用
set -e

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SKILL_DIR"

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if python3 -c "$@" 2>/dev/null; then
        echo "✅ $label"
        PASS=$((PASS + 1))
    else
        echo "❌ $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Compass Trader · 模块验证 ==="
echo ""

echo "--- market_data.py ---"
check "import market_data" \
    "import sys; sys.path.insert(0, 'scripts'); from market_data import get_realtime_quote, get_history, get_index_data, search_ticker, batch_quotes; print('OK')"

check "quote 600519" \
    "import sys, json; sys.path.insert(0, 'scripts'); from market_data import get_realtime_quote; r = get_realtime_quote('600519'); assert 'error' not in r, r.get('error'); print(f\"{r['name']} ¥{r['price']}\")"

check "history 600519" \
    "import sys; sys.path.insert(0, 'scripts'); from market_data import get_history; r = get_history('600519', '2026-05-01', '2026-06-07'); assert isinstance(r, list) and len(r) > 0, 'no data'; print(f'{len(r)} rows')"

check "index 000300" \
    "import sys; sys.path.insert(0, 'scripts'); from market_data import get_index_data; r = get_index_data('000300'); assert 'error' not in r, r.get('error'); print(f\"沪深300: {r['price']}\")"

check "search 茅台" \
    "import sys; sys.path.insert(0, 'scripts'); from market_data import search_ticker; r = search_ticker('茅台'); assert isinstance(r, list) and len(r) > 0, 'no results'; print(f\"Found: {r[0]['ticker']} {r[0]['name']}\")"

echo ""
echo "--- risk.py ---"
check "import risk" \
    "import sys; sys.path.insert(0, 'scripts'); from risk import kelly_position, position_size, calculate_stop_loss, calculate_take_profit, max_position_check; print('OK')"

check "kelly" \
    "import sys; sys.path.insert(0, 'scripts'); from risk import kelly_position; r = kelly_position(0.55, 2.0); assert r['full_kelly'] > 0, 'kelly <= 0'; print(f\"Kelly: {r['full_kelly']:.2%}\")"

check "position_size" \
    "import sys; sys.path.insert(0, 'scripts'); from risk import position_size; r = position_size(1000000, 1680, 0.02, 0.08); assert r['shares'] >= 0, 'shares < 0'; print(f\"{r['shares']} shares ({r['position_pct']:.1%})\")"

check "stop_loss" \
    "import sys; sys.path.insert(0, 'scripts'); from risk import calculate_stop_loss; r = calculate_stop_loss(1680); assert r['stop_loss'] < 1680, 'stop >= entry'; print(f\"Stop: {r['stop_loss']}\")"

check "take_profit" \
    "import sys; sys.path.insert(0, 'scripts'); from risk import calculate_take_profit; r = calculate_take_profit(1680, 1545.6, 2.0); assert r['take_profit'] > 1680, 'tp <= entry'; print(f\"TP: {r['take_profit']}\")"

echo ""
echo "--- portfolio.py ---"
check "import portfolio" \
    "import sys; sys.path.insert(0, 'scripts'); from portfolio import load_account, load_positions, get_portfolio_summary; print('OK')"

check "load_account" \
    "import sys; sys.path.insert(0, 'scripts'); from portfolio import load_account; a = load_account(); assert a['initial_capital'] > 0; print(f\"Capital: ¥{a['initial_capital']:,.0f}\")"

check "summary" \
    "import sys; sys.path.insert(0, 'scripts'); from portfolio import get_portfolio_summary; s = get_portfolio_summary(); assert s['total_asset'] > 0; print(f\"Asset: ¥{s['total_asset']:,.0f}\")"

echo ""
echo "--- backtest.py ---"
check "import backtest" \
    "import sys; sys.path.insert(0, 'scripts'); from backtest import run_backtest, list_strategies; print('OK')"

check "list strategies" \
    "import sys; sys.path.insert(0, 'scripts'); from backtest import list_strategies; s = list_strategies(); assert len(s) == 3; print(f'{len(s)} strategies: {[x[\"name\"] for x in s]}')"

echo ""
echo "--- reporter.py ---"
check "import reporter" \
    "import sys; sys.path.insert(0, 'scripts'); from reporter import generate_weekly_report, generate_monthly_report, generate_summary; print('OK')"

check "generate summary" \
    "import sys, json; sys.path.insert(0, 'scripts'); from reporter import generate_summary; r = generate_summary(); assert 'account' in r; print(f\"Asset: ¥{r['account']['total_asset']:,.0f}\")"

check "generate weekly report" \
    "import sys; sys.path.insert(0, 'scripts'); from reporter import generate_weekly_report; r = generate_weekly_report('/tmp'); assert r['success']; print(f\"{r['filename']}\")"

echo ""
echo "--- 数据目录 ---"
check "account.json exists" \
    "import json; d = json.load(open('data/account.json')); assert d['currency'] == 'CNY'; print(f\"{d['currency']} ¥{d['initial_capital']:,.0f}\")"

check "positions.json exists" \
    "import json; d = json.load(open('data/positions.json')); assert 'positions' in d; print(f\"{len(d['positions'])} positions\")"

check "trades.json exists" \
    "import json; d = json.load(open('data/trades.json')); assert 'trades' in d; print(f\"{len(d['trades'])} trades\")"

check "tracker.json exists" \
    "import json; d = json.load(open('data/tracker.json')); assert 'daily_snapshots' in d; print(f\"{len(d['daily_snapshots'])} snapshots\")"

echo ""
echo "=== 结果: $PASS 通过 / $((PASS + FAIL)) 总计 ==="

if [ "$FAIL" -gt 0 ]; then
    echo "❌ $FAIL 项失败"
    exit 1
else
    echo "✅ 全部通过！"
fi
