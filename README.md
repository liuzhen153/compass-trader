# Compass Trader · 指南针交易者

> Financial Compass 的执行搭档——模拟盘交易与绩效追踪引擎。

## 定位

Compass Trader 不做基本面分析，不做产业链研究（那是 [Financial Compass](https://github.com/liuzhen153/financial-compass) 的职责）。它只负责**交易执行和绩效追踪**。

## 能力

| 模块 | 功能 |
|------|------|
| **回测模式** | Backtrader / QMT 历史策略回测 |
| **模拟盘模式** | 国金 miniQMT / BigQuant 模拟盘执行 |
| **持仓跟踪** | 浮动盈亏、行业暴露、风险指标 |
| **交易指令生成** | 结构化 JSON（含止损止盈、置信度） |
| **绩效追踪** | 周报/月报，胜率、盈亏比、超额收益、AI 反思 |

## 与 Financial Compass 的分工

```
Financial Compass          Compass Trader
     ↓                         ↓
  产业链分析     ──────→    交易指令生成
  贝叶斯估值     ──────→    模拟盘执行
  基金穿透       ──────→    绩效追踪
  赛道扫描       ──────→    回测验证
```

## 输出

- 周报/月报：`.md` 文件，含 YAML 元信息
- 交易记录：结构化 JSON + `.md` 文件

## 免责声明

模拟交易工具，不构成投资建议。模拟盘结果不保证实盘表现。

## License

MIT
