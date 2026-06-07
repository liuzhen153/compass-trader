# Compass Trader · 指南针交易者

> Financial Compass 的执行搭档 — 模拟盘交易执行与绩效追踪引擎。

## 定位

```
Compass Scout          Financial Compass      Compass Trader
（指南针侦察兵）        （金融指南针）           （指南针交易者）
      │                      │                      │
  发现热门赛道         深度分析标的           执行模拟交易
  识别爆发前夜         估值+风险+对比         绩效追踪+反思
      │                      │                      │
  WHAT to buy           SHOULD I buy           WHEN & HOW
      │                      │                      │
      └── 赛道委托 ──→ 赛道扫描+选股            ↑
                              │                  │
                              └── 交易参数 ──→ 执行+追踪
                                                 │
                                        绩效反馈 ──┘
```

Compass Trader 不做基本面分析，不做产业链研究。它只负责**交易执行和绩效追踪**。

## 核心能力

| 模块 | 功能 |
|------|------|
| **模拟交易执行** | 接收 FC 交易参数 → 风控验证 → 执行买卖 → 持仓管理 |
| **实时行情** | A 股实时报价、历史 K 线、指数行情、股票搜索（新浪财经 API） |
| **风控计算** | 凯利公式仓位计算、ATR/硬止损、止盈目标、时间止损、行业仓位上限 |
| **策略回测** | Backtrader 引擎，内置均线交叉/动量突破/均值回归三种策略 |
| **绩效追踪** | 周报/月报自动生成，含胜率、盈亏比、超额收益、AI 反思 |
| **可视化仪表盘** | 本地 HTML 仪表盘（端口 8765），资产曲线、持仓明细、行业分布饼图 |
| **反馈闭环** | 绩效数据反馈给 Financial Compass，帮助修正估值判断 |

## Python 脚本引擎

内置 6 个 Python 脚本，Claude 优先调用脚本获取数据而非依赖 WebSearch：

| 脚本 | 用途 | 示例 |
|------|------|------|
| `market_data.py` | A 股实时行情/历史K线/指数/搜索 | `python3 scripts/market_data.py quote 600519` |
| `risk.py` | 凯利公式/仓位计算/止损止盈 | `python3 scripts/risk.py kelly 0.55 2.0` |
| `portfolio.py` | 模拟交易执行/持仓管理/快照 | `python3 scripts/portfolio.py init 1000000` |
| `backtest.py` | 历史策略回测（Backtrader） | `python3 scripts/backtest.py run 600519 sma_cross 2024-01-01 2026-06-07 1000000` |
| `reporter.py` | 生成周报/月报/交易记录 .md | `python3 scripts/reporter.py weekly` |
| `dashboard.py` | 启动本地 HTML 仪表盘 | `python3 scripts/dashboard.py` |

### 仪表盘

浏览器打开 `http://localhost:8765`，实时展示：
- 📊 资产曲线（总资产 vs 快照历史）
- 💰 账户概况卡片
- 📋 持仓明细表格
- 🥧 行业分布饼图
- 📜 交易记录时间线
- 🔄 一键刷新行情 + 每 30 秒自动刷新

**数据完全来自 `data/*.json`，与命令行共享同一份数据。**

## 快速开始

在 Claude Code 中：

```
# 交易执行
接收 FC 交易参数 / 执行 FC 推荐     # 读取 FC 参数 → 风控验证 → 执行买入
买入 [标的]                          # 模拟盘买入
卖出 [标的]                          # 模拟盘卖出

# 行情查询
[标的] 行情 / [标的] 多少钱          # 实时报价
搜索 [关键词]                        # 搜索股票代码

# 风控计算
计算仓位 [标的]                      # 凯利公式仓位建议

# 绩效报告
本周绩效 / 本周报告                  # 生成周报 .md
本月绩效 / 本月报告                  # 生成月报 .md
当前持仓 / 帮我看看持仓               # 持仓汇总 + 行业暴露

# 回测
回测 [标的] [策略]                   # 历史策略回测
回测有哪些策略                       # 列出内置策略

# 可视化
打开仪表盘                           # 启动 HTML 仪表盘
```

## 交易指令格式

每个交易操作生成结构化 JSON：

```json
{
  "timestamp": "2026-06-06T09:30:00",
  "action": "BUY",
  "ticker": "600519.SH",
  "ticker_name": "贵州茅台",
  "quantity": 100,
  "price_type": "LIMIT",
  "limit_price": 1680.00,
  "reason": "估值分位处于历史10%以下/资金面回暖",
  "confidence": "medium",
  "stop_loss": 1512.00,
  "take_profit": 2016.00,
  "time_horizon": "6-12 months",
  "risk_note": "消费复苏不及预期将触发止损"
}
```

## 输出格式

```
模拟盘周报：周报-[YYYY-WXX].md
模拟盘月报：月报-[YYYYMM].md
交易记录：交易-[标的]-[YYYYMMDD-HHMMSS].md
```

## 数据目录

所有账户和交易数据存储在 `data/` 下的 JSON 文件中：

| 文件 | 内容 |
|------|------|
| `data/account.json` | 账户资金（初始资金/现金余额） |
| `data/positions.json` | 当前持仓（标的/成本价/现价/行业） |
| `data/trades.json` | 交易历史（含止损止盈/置信度/理由） |
| `data/tracker.json` | 每日快照（用于周报/月报计算） |

## 前置依赖

| 依赖 | 说明 |
|------|------|
| [Financial Compass](https://github.com/liuzhen153/financial-compass) | 提供估值判断和交易参数（必需，否则缺少决策依据） |
| [Compass Scout](https://github.com/liuzhen153/compass-scout) | 上游赛道发现（可选，Scout→FC→Trader 形成完整闭环） |
| Claude Code | 运行环境 |

## 安装

```bash
git clone https://github.com/liuzhen153/compass-trader.git ~/.claude/skills/compass-trader
pip install -r requirements.txt
```

## 三者分工

| 职责 | Compass Scout | Financial Compass | Compass Trader |
|------|:---:|:---:|:---:|
| 赛道发现+方向判断 | ✅ | — | — |
| 三大映射/五维验证 | ✅ | — | — |
| 产业链 L0-L6 + 卡点判据 | — | ✅ | — |
| 贝叶斯估值+三情景 | — | ✅ | — |
| 基金穿透+赛道扫描 | — | ✅ | — |
| 交易参数输出 | — | ✅ | — |
| 模拟盘执行+风控 | — | — | ✅ |
| 策略回测 | — | — | ✅ |
| 绩效追踪+AI反思 | — | — | ✅ |

## 免责声明

本工具是模拟交易工具，不构成投资建议。模拟盘结果不保证实盘表现。所有交易决策的最终责任在用户手中。投资有风险，入市需谨慎。

## License

MIT
