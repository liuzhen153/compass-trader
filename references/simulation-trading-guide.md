# 模拟盘操作指南

## 快速开始（以国金miniQMT为例）

### 1. 环境准备
```bash
# 安装依赖
pip install akshare tushare backtrader xtquant pandas numpy matplotlib

# 下载国金证券QMT客户端
# https://www.gjzq.com.cn/ （搜索"QMT"下载）
```

### 2. 注册模拟盘账号
1. 下载并安装QMT客户端
2. 选择"模拟交易"模式
3. 初始模拟资金：100万（默认）
4. 记录模拟账户ID

### 3. Python连接模拟盘
```python
from xtquant import xtdata, xttrader, xtconstant

# 下载历史数据
xtdata.download_history_data('600519.SH', '1d', '20240101', '')

# 获取行情
data = xtdata.get_market_data_ex(
    stock_list=['600519.SH'],
    period='1d',
    start_time='20260101'
)

# 下单示例（需先登录QMT客户端）
# seq = xttrader.order_stock(
#     account_id='YOUR_ACCOUNT',
#     stock_code='600519.SH',
#     order_type=xtconstant.STOCK_BUY,
#     order_volume=100,
#     price_type=xtconstant.FIX_PRICE,
#     price=1680.00,
#     strategy_name='AI_Strategy',
#     order_remark='AI signal: H3 probability > 50%'
# )
```

### 4. 策略回测（Backtrader）
```python
import backtrader as bt
import akshare as ak

class AIStrategy(bt.Strategy):
    def __init__(self):
        self.sma20 = bt.indicators.SMA(self.data.close, period=20)
        self.sma60 = bt.indicators.SMA(self.data.close, period=60)

    def next(self):
        # AI分析信号在此整合
        if self.sma20[0] > self.sma60[0] and self.sma20[-1] <= self.sma60[-1]:
            self.buy(size=100)  # 金叉买入

        if self.sma20[0] < self.sma60[0] and self.sma20[-1] >= self.sma60[-1]:
            self.sell(size=100)  # 死叉卖出

# 获取数据
df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20240101", adjust="qfq")

# 运行回测
cerebro = bt.Cerebro()
data = bt.feeds.PandasData(dataname=df)
cerebro.adddata(data)
cerebro.addstrategy(AIStrategy)
cerebro.broker.setcash(100000.0)
cerebro.run()
cerebro.plot()
```

## 模拟盘纪律

### 仓位管理
- 单只股票/基金不超过总仓位的20%
- 行业暴露不超过总仓位的40%
- 现金比例不低于10%（用于加仓机会）
- 使用凯利公式指导仓位大小：`f = (bp - q) / b`

### 止损规则
- 硬止损：单笔亏损达到入场价的-8%
- 时间止损：持仓30天无利润，减半
- 逻辑止损：买入理由消失（不论盈亏）

### 记录要求
每笔交易记录：
- 入场日期、价格、数量
- 买入理由（AI分析的什么信号触发的）
- 出场日期、价格
- 盈亏金额、百分比
- 复盘：买入理由是否正确？卖出时机是否最优？

## AI模拟盘评估周期

```
第一轮（2周）：手动模拟
  - AI给出分析，人工判断后手动在模拟盘下单
  - 目的：验证AI分析质量

第二轮（4周）：半自动模拟
  - AI给出分析+交易建议，人工确认后执行
  - 目的：磨合AI信号到执行的转换

第三轮（8周+）：全自动模拟
  - AI分析→AI生成指令→自动执行模拟盘
  - 目的：测试全自动策略的稳定性

评估标准：
  - 绝对收益率 > 基准指数（沪深300）
  - 夏普比率 > 1.0
  - 最大回撤 < 25%
  - 月度胜率 > 55%
  - 连续3个月达标才能考虑转实盘
```
