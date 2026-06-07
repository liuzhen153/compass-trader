#!/usr/bin/env python3
"""
Compass Trader · 本地 HTML 可视化仪表盘
启动后浏览器打开 http://localhost:8765

用法：
  python3 scripts/dashboard.py              # 启动服务 (端口 8765)
  python3 scripts/dashboard.py --port 9999   # 自定义端口
"""

import sys
import json
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

PORT = 8765

# ── 数据读取 ──────────────────────────────────────────────

def read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def api_account():
    return read_json("account.json") or {}

def api_positions():
    data = read_json("positions.json") or {"positions": []}
    return data

def api_trades():
    data = read_json("trades.json") or {"trades": []}
    return data

def api_tracker():
    return read_json("tracker.json") or {"daily_snapshots": []}

def api_summary():
    account = read_json("account.json") or {"initial_capital": 1e6, "cash": 1e6}
    pos_data = read_json("positions.json") or {"positions": []}
    positions = pos_data.get("positions", [])
    trades_data = read_json("trades.json") or {"trades": []}
    trades = trades_data.get("trades", [])
    tracker = read_json("tracker.json") or {"daily_snapshots": []}

    market_value = sum(p["shares"] * p["current_price"] for p in positions)
    total_cost = sum(p["shares"] * p["avg_cost"] for p in positions)
    total_asset = account["cash"] + market_value
    total_pnl = market_value - total_cost
    cumulative_return = (total_asset / account["initial_capital"] - 1) * 100 if account["initial_capital"] > 0 else 0

    # 行业暴露
    industries = {}
    for p in positions:
        ind = p.get("industry") or "未分类"
        if ind not in industries:
            industries[ind] = {"mv": 0, "pnl": 0, "tickers": []}
        mv = p["shares"] * p["current_price"]
        cost = p["shares"] * p["avg_cost"]
        industries[ind]["mv"] += mv
        industries[ind]["pnl"] += (mv - cost)
        industries[ind]["tickers"].append(p["name"])

    # 盈亏统计
    wins = sum(1 for p in positions if p["current_price"] > p["avg_cost"])
    losses = sum(1 for p in positions if p["current_price"] <= p["avg_cost"])

    # 交易统计
    buy_trades = [t for t in trades if t["action"] == "BUY"]

    return {
        "account": {
            "initial_capital": account["initial_capital"],
            "total_asset": round(total_asset, 2),
            "cash": round(account["cash"], 2),
            "market_value": round(market_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "cumulative_return_pct": round(cumulative_return, 2),
            "cash_ratio": round(account["cash"] / total_asset * 100, 1) if total_asset > 0 else 100,
        },
        "positions": [{
            "ticker": p["ticker"],
            "name": p["name"],
            "shares": p["shares"],
            "avg_cost": p["avg_cost"],
            "current_price": p["current_price"],
            "market_value": round(p["shares"] * p["current_price"], 2),
            "pnl": round(p["shares"] * (p["current_price"] - p["avg_cost"]), 2),
            "pnl_pct": round((p["current_price"] - p["avg_cost"]) / p["avg_cost"] * 100, 2),
            "industry": p.get("industry", ""),
            "entry_date": p.get("entry_date", ""),
            "stop_loss": p.get("stop_loss"),
            "take_profit": p.get("take_profit"),
        } for p in positions],
        "industries": [{
            "name": ind,
            "market_value": round(data["mv"], 2),
            "pnl": round(data["pnl"], 2),
            "weight": round(data["mv"] / total_asset * 100, 1) if total_asset > 0 else 0,
            "tickers": data["tickers"],
        } for ind, data in industries.items()],
        "trades": trades,
        "snapshots": tracker.get("daily_snapshots", []),
        "stats": {
            "position_count": len(positions),
            "win_count": wins,
            "loss_count": losses,
            "trade_count": len(buy_trades),
        },
    }


def api_refresh_prices():
    """刷新所有持仓现价"""
    try:
        from market_data import batch_quotes
        positions = (read_json("positions.json") or {}).get("positions", [])
        if not positions:
            return {"success": True, "message": "无持仓", "updated": []}
        tickers = [p["ticker"] for p in positions]
        quotes = batch_quotes(tickers)
        updated = []
        for q in quotes:
            if "error" in q:
                continue
            ticker = q["ticker"]
            price = q.get("price")
            if price:
                for p in positions:
                    if p["ticker"] == ticker:
                        p["current_price"] = price
                        updated.append({"ticker": ticker, "name": q.get("name"), "price": price})
        # 保存
        with open(os.path.join(DATA_DIR, "positions.json"), "w") as f:
            json.dump({"positions": positions, "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}, f, ensure_ascii=False, indent=2)
        return {"success": True, "updated": updated}
    except Exception as e:
        return {"error": str(e)}


# ── Dashboard HTML ────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Compass Trader · 模拟盘仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e1e4e8; min-height: 100vh; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid #21262d; margin-bottom: 24px; }
.header h1 { font-size: 24px; font-weight: 700; color: #58a6ff; }
.header .actions { display: flex; gap: 12px; }
.header .actions button { padding: 8px 16px; border: 1px solid #30363d; border-radius: 6px; background: #21262d; color: #c9d1d9; cursor: pointer; font-size: 13px; }
.header .actions button:hover { background: #30363d; }
.header .actions button.primary { background: #238636; border-color: #2ea043; color: #fff; }
.header .actions button.primary:hover { background: #2ea043; }
.header .status { font-size: 12px; color: #8b949e; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; }
.card .label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.card .value { font-size: 28px; font-weight: 700; }
.card .sub { font-size: 13px; color: #8b949e; margin-top: 4px; }
.value.up { color: #3fb950; }
.value.down { color: #f85149; }
.value.neutral { color: #e1e4e8; }
.charts { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px; }
.chart-box { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; }
.chart-box.full { grid-column: 1 / -1; }
.chart-box h3 { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: #c9d1d9; }
.chart-box canvas { max-height: 350px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #21262d; font-size: 13px; }
th { color: #8b949e; font-weight: 500; }
td { color: #c9d1d9; }
tr:hover td { background: #1c2128; }
.ticker-link { color: #58a6ff; text-decoration: none; }
.pnl-up { color: #3fb950; }
.pnl-down { color: #f85149; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.badge-buy { background: #1b3a1b; color: #3fb950; }
.badge-sell { background: #3a1b1b; color: #f85149; }
.empty-state { text-align: center; padding: 60px 20px; color: #484f58; }
.empty-state .icon { font-size: 48px; margin-bottom: 16px; }
.refresh-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #3fb950; margin-right: 6px; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
@media (max-width: 768px) { .charts { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">
<div class="header">
  <div>
    <h1>🧭 Compass Trader</h1>
    <div class="status"><span class="refresh-indicator"></span>数据更新于 <span id="updateTime">--</span></div>
  </div>
  <div class="actions">
    <button onclick="refreshData()">🔄 刷新数据</button>
    <button class="primary" onclick="refreshPrices()">📡 更新行情</button>
  </div>
</div>

<div class="cards" id="cards"></div>

<div class="charts">
  <div class="chart-box">
    <h3>📈 资产曲线</h3>
    <canvas id="assetChart"></canvas>
  </div>
  <div class="chart-box">
    <h3>🥧 行业分布</h3>
    <canvas id="industryChart"></canvas>
  </div>
</div>

<div class="chart-box full" id="positionsSection">
  <h3>📋 当前持仓</h3>
  <div id="positionsTable"></div>
</div>

<div class="chart-box full" id="tradesSection" style="margin-top:16px;">
  <h3>📜 交易记录</h3>
  <div id="tradesTable"></div>
</div>
</div>

<script>
let assetChart = null, industryChart = null;

async function fetchAPI(path) {
  const res = await fetch('/api/' + path);
  return res.json();
}

function formatMoney(v) { return '¥' + (v || 0).toLocaleString('zh-CN', {minimumFractionDigits: 0, maximumFractionDigits: 0}); }
function formatPct(v) { return (v >= 0 ? '+' : '') + (v || 0).toFixed(2) + '%'; }
function pctClass(v) { return v > 0 ? 'pnl-up' : v < 0 ? 'pnl-down' : ''; }

async function refreshData() {
  const summary = await fetchAPI('summary');
  renderCards(summary);
  renderAssetChart(summary.snapshots || []);
  renderIndustryChart(summary.industries || []);
  renderPositions(summary.positions || []);
  renderTrades(summary.trades || []);
  document.getElementById('updateTime').textContent = new Date().toLocaleTimeString('zh-CN');
}

function renderCards(s) {
  const a = s.account;
  const st = s.stats;
  const cards = [
    { label: '总资产', value: formatMoney(a.total_asset), cls: 'neutral', sub: `初始 ${formatMoney(a.initial_capital)}` },
    { label: '累计收益', value: formatPct(a.cumulative_return_pct), cls: a.cumulative_return_pct >= 0 ? 'up' : 'down', sub: `浮动盈亏 ${formatPct(a.total_pnl_pct)}` },
    { label: '现金余额', value: formatMoney(a.cash), cls: 'neutral', sub: `占比 ${a.cash_ratio}%` },
    { label: '持仓市值', value: formatMoney(a.market_value), cls: 'neutral', sub: `${st.position_count} 只标的` },
    { label: '交易统计', value: st.trade_count, cls: 'neutral', sub: `盈利 ${st.win_count} / 亏损 ${st.loss_count}` },
  ];
  document.getElementById('cards').innerHTML = cards.map(c =>
    `<div class="card"><div class="label">${c.label}</div><div class="value ${c.cls}">${c.value}</div><div class="sub">${c.sub}</div></div>`
  ).join('');
}

function renderAssetChart(snapshots) {
  const ctx = document.getElementById('assetChart').getContext('2d');
  if (assetChart) assetChart.destroy();
  const labels = snapshots.map(s => s.date);
  const values = snapshots.map(s => s.total_asset);
  assetChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '总资产',
        data: values,
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88,166,255,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8b949e' } } },
      scales: {
        x: { ticks: { color: '#484f58', maxTicksLimit: 12 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#484f58', callback: v => formatMoney(v) }, grid: { color: '#21262d' } }
      }
    }
  });
}

function renderIndustryChart(industries) {
  const ctx = document.getElementById('industryChart').getContext('2d');
  if (industryChart) industryChart.destroy();
  if (!industries.length) {
    document.getElementById('industryChart').parentElement.innerHTML = '<h3>🥧 行业分布</h3><div class="empty-state"><div class="icon">📭</div>暂无持仓</div>';
    return;
  }
  const colors = ['#58a6ff','#3fb950','#f0883e','#f85149','#bc8cff','#ffa198','#79c0ff','#d2a8ff','#56d364','#e3b341'];
  industryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: industries.map(i => i.name),
      datasets: [{
        data: industries.map(i => i.market_value),
        backgroundColor: colors,
        borderColor: '#161b22',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#c9d1d9', padding: 16, usePointStyle: true } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${formatMoney(ctx.raw)} (${industries[ctx.dataIndex].weight}%)` } }
      }
    }
  });
}

function renderPositions(positions) {
  if (!positions.length) {
    document.getElementById('positionsTable').innerHTML = '<div class="empty-state"><div class="icon">📭</div>暂无持仓</div>';
    return;
  }
  const rows = positions.map(p => `
    <tr>
      <td><span class="ticker-link">${p.name}</span><br><small style="color:#8b949e">${p.ticker}</small></td>
      <td>${p.shares} 股</td>
      <td>${p.avg_cost.toFixed(2)}</td>
      <td>${p.current_price.toFixed(2)}</td>
      <td>${formatMoney(p.market_value)}</td>
      <td class="${pctClass(p.pnl)}">${formatPct(p.pnl_pct)}</td>
      <td class="${pctClass(p.pnl)}">${formatMoney(p.pnl)}</td>
      <td><span style="color:#8b949e">${p.industry || '-'}</span></td>
    </tr>
  `).join('');
  document.getElementById('positionsTable').innerHTML = `
    <table><thead><tr><th>标的</th><th>持仓</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏%</th><th>盈亏</th><th>行业</th></tr></thead><tbody>${rows}</tbody></table>
  `;
}

function renderTrades(trades) {
  if (!trades.length) {
    document.getElementById('tradesTable').innerHTML = '<div class="empty-state"><div class="icon">📜</div>暂无交易记录</div>';
    return;
  }
  const rows = trades.slice().reverse().slice(0, 20).map(t => `
    <tr>
      <td>${t.timestamp ? t.timestamp.slice(0,16) : '-'}</td>
      <td><span class="badge ${t.action === 'BUY' ? 'badge-buy' : 'badge-sell'}">${t.action}</span></td>
      <td>${t.name || ''} (${t.ticker})</td>
      <td>${t.shares} 股</td>
      <td>¥${t.price}</td>
      <td>${t.confidence || '-'}</td>
      <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.reason || '-'}</td>
      <td><span class="badge ${t.status === 'open' ? 'badge-buy' : 'badge-sell'}">${t.status}</span></td>
    </tr>
  `).join('');
  document.getElementById('tradesTable').innerHTML = `
    <table><thead><tr><th>时间</th><th>操作</th><th>标的</th><th>数量</th><th>价格</th><th>置信度</th><th>理由</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>
  `;
}

async function refreshPrices() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ 更新中...';
  try {
    const res = await fetch('/api/refresh-prices');
    const data = await res.json();
    if (data.updated) {
      alert(`已更新 ${data.updated.length} 只标的行情`);
      await refreshData();
    } else {
      alert('无持仓需要更新');
    }
  } catch(e) { alert('更新失败: ' + e.message); }
  btn.disabled = false;
  btn.textContent = '📡 更新行情';
}

// 初始化
refreshData();
// 自动刷新 (30s)
setInterval(refreshData, 30000);
</script>
</body>
</html>"""

# ── HTTP Server ──────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._html_response(DASHBOARD_HTML)

        elif path == "/api/summary":
            self._json_response(api_summary())

        elif path == "/api/account":
            self._json_response(api_account())

        elif path == "/api/positions":
            self._json_response(api_positions())

        elif path == "/api/trades":
            self._json_response(api_trades())

        elif path == "/api/tracker":
            self._json_response(api_tracker())

        elif path == "/api/refresh-prices":
            self._json_response(api_refresh_prices())

        else:
            self._json_response({"error": "Not found"}, 404)


def main():
    global PORT
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        PORT = int(sys.argv[idx + 1])

    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"🧭 Compass Trader 仪表盘")
    print(f"   → 打开浏览器访问: http://localhost:{PORT}")
    print(f"   → 按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 仪表盘已关闭")
        server.shutdown()


if __name__ == "__main__":
    main()
