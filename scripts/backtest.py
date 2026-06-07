#!/usr/bin/env python3
"""
Compass Trader · 回测引擎
基于 Backtrader + 新浪财经数据，运行历史策略回测。

内置策略:
  - sma_cross: 均线交叉 (MA20/MA60)
  - momentum: 动量突破 (N日新高)
  - mean_reversion: 均值回归 (布林带)

用法：
  python3 scripts/backtest.py run <ticker> sma_cross 2025-01-01 2026-06-07 [初始资金]
  python3 scripts/backtest.py list                              # 列出可用策略
  python3 scripts/backtest.py run <ticker> momentum 2025-01-01 2026-06-07 [资金] [period]
  python3 scripts/backtest.py run <ticker> mean_reversion 2025-01-01 2026-06-07 [资金] [period]
"""

import sys
import json
import os
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

import backtrader as bt
import pandas as pd

# 绕过代理
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"


# ── 内置策略 ──────────────────────────────────────────────

class SMACross(bt.Strategy):
    """均线交叉策略：MA20上穿MA60买入，下穿卖出"""
    params = dict(fast=20, slow=60)

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:  # 金叉
                size = self._calc_size()
                if size >= 100:
                    self.order = self.buy(size=size)
        else:
            if self.crossover < 0:  # 死叉
                self.order = self.close()

    def _calc_size(self):
        """计算买入股数，按100股取整"""
        size = int(self.broker.get_cash() * 0.95 / self.data.close[0])
        return max(0, (size // 100) * 100)

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class Momentum(bt.Strategy):
    """动量突破策略：价格突破N日最高价买入，跌破N日最低价卖出"""
    params = dict(period=20)

    def __init__(self):
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.period)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.data.close[0] > self.highest[-1]:  # 突破N日高
                size = self._calc_size()
                if size >= 100:
                    self.order = self.buy(size=size)
        else:
            if self.data.close[0] < self.lowest[-1]:  # 跌破N日低
                self.order = self.close()

    def _calc_size(self):
        size = int(self.broker.get_cash() * 0.95 / self.data.close[0])
        return max(0, (size // 100) * 100)

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class MeanReversion(bt.Strategy):
    """均值回归策略：触及布林下轨买入，回归中轨或触及上轨卖出"""
    params = dict(period=20, devfactor=2.0)

    def __init__(self):
        self.bollinger = bt.indicators.BollingerBands(
            self.data.close, period=self.p.period, devfactor=self.p.devfactor)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.data.close[0] <= self.bollinger.lines.bot[0]:
                size = self._calc_size()
                if size >= 100:
                    self.order = self.buy(size=size)
        else:
            # 回归中轨卖出
            if self.data.close[0] >= self.bollinger.lines.mid[0]:
                self.order = self.close()

    def _calc_size(self):
        size = int(self.broker.get_cash() * 0.95 / self.data.close[0])
        return max(0, (size // 100) * 100)

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


# ── 策略注册表 ────────────────────────────────────────────

STRATEGIES = {
    "sma_cross": {"class": SMACross, "params": {"fast": 20, "slow": 60}},
    "momentum": {"class": Momentum, "params": {"period": 20}},
    "mean_reversion": {"class": MeanReversion, "params": {"period": 20, "devfactor": 2.0}},
}


def list_strategies() -> list:
    """列出可用策略"""
    return [
        {
            "name": name,
            "class": s["class"].__name__,
            "description": s["class"].__doc__.strip().split("\n")[0] if s["class"].__doc__ else "",
            "default_params": s["params"],
        }
        for name, s in STRATEGIES.items()
    ]


# ── 回测运行 ──────────────────────────────────────────────

def run_backtest(ticker: str, strategy_name: str,
                 start_date: str, end_date: str = None,
                 initial_cash: float = 1000000,
                 strategy_params: dict = None) -> dict:
    """
    运行回测。
    返回: {ticker, strategy, total_return, annual_return, max_drawdown,
           sharpe, win_rate, profit_loss_ratio, trade_count, trades[],
           start_date, end_date, initial_cash, final_value}
    """
    if strategy_name not in STRATEGIES:
        return {"error": f"未知策略: {strategy_name}，可用: {list(STRATEGIES.keys())}"}

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # 获取历史数据
    try:
        from market_data import get_history
        data = get_history(ticker, start_date, end_date)
        if isinstance(data, dict) and "error" in data:
            return {"error": f"获取行情数据失败: {data['error']}"}
    except Exception as e:
        return {"error": f"获取行情数据失败: {str(e)}"}

    if not data or len(data) < 60:
        return {"error": f"数据不足（{len(data) if data else 0} 条），至少需要 60 条"}

    # 转换为 DataFrame
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df["volume"] = df["volume"].fillna(0).astype(float)

    # 初始化 Cerebro
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.00025)  # 万2.5 佣金

    # 添加数据
    data_feed = bt.feeds.PandasData(dataname=df, open="open", high="high",
                                     low="low", close="close", volume="volume")
    cerebro.adddata(data_feed)

    # 添加策略
    strat_cls = STRATEGIES[strategy_name]["class"]
    params = {**STRATEGIES[strategy_name]["params"]}
    if strategy_params:
        params.update(strategy_params)
    cerebro.addstrategy(strat_cls, **params)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                         riskfreerate=0.025, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")  # Variability-Weighted Return

    # 运行
    start_value = cerebro.broker.getvalue()
    results = cerebro.run()
    end_value = cerebro.broker.getvalue()

    if not results:
        return {"error": "回测运行失败，未产生结果"}

    strat = results[0]

    # 汇总指标
    total_return = (end_value - start_value) / start_value

    # 年化收益
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    annual_return = (1 + total_return) ** (365.0 / max(days, 1)) - 1 if days > 0 else 0

    # 最大回撤
    dd = strat.analyzers.drawdown.get_analysis()
    max_drawdown = dd.get("max", {}).get("drawdown", 0) / 100 if dd.get("max") else 0

    # 夏普
    sharpe = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get("sharperatio", 0) or 0

    # 交易分析
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    won = trade_analysis.get("won", {}).get("total", 0)
    lost = trade_analysis.get("lost", {}).get("total", 0)
    win_rate = won / total_trades if total_trades > 0 else 0

    # 盈亏比
    avg_win = trade_analysis.get("won", {}).get("pnl", {}).get("average", 0)
    avg_loss = abs(trade_analysis.get("lost", {}).get("pnl", {}).get("average", 0))
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    # 提取交易记录
    trades_list = []
    # TradeAnalyzer 提供聚合统计，不提供逐笔明细
    # 如有需要可以通过自定义 analyzer 扩展

    return {
        "ticker": ticker,
        "strategy": strategy_name,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "initial_cash": initial_cash,
        "final_value": round(end_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "annual_return_pct": round(annual_return * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2) if max_drawdown else 0,
        "sharpe_ratio": round(sharpe_ratio, 3) if sharpe_ratio else 0,
        "trade_count": total_trades,
        "win_count": won,
        "loss_count": lost,
        "win_rate_pct": round(win_rate * 100, 1),
        "profit_loss_ratio": round(profit_loss_ratio, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "trades": trades_list,
    }


# ── CLI 入口 ──────────────────────────────────────────────

def _cli():
    if len(sys.argv) < 2:
        print("Compass Trader · 回测引擎")
        print("用法:")
        print("  python3 scripts/backtest.py list")
        print("  python3 scripts/backtest.py run <ticker> <strategy> <start> [end] [cash] [params...]")
        print("")
        print("示例:")
        print("  python3 scripts/backtest.py run 600519 sma_cross 2023-01-01 2026-06-07 1000000")
        print("  python3 scripts/backtest.py run 600519 momentum 2023-01-01 2026-06-07 1000000 fast=10")
        return

    cmd = sys.argv[1]
    result = None

    if cmd == "list":
        result = list_strategies()

    elif cmd == "run" and len(sys.argv) >= 5:
        ticker = sys.argv[2]
        strategy = sys.argv[3]
        start = sys.argv[4]
        end = sys.argv[5] if len(sys.argv) >= 6 else None
        cash = float(sys.argv[6]) if len(sys.argv) >= 7 else 1000000

        # 解析额外参数 (key=value)
        extra_params = {}
        for arg in sys.argv[7:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                extra_params[k] = float(v) if v.replace(".", "").isdigit() else v

        result = run_backtest(ticker, strategy, start, end, cash, extra_params)
    else:
        result = {"error": f"未知命令或参数不足: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
