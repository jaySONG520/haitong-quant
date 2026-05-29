# Quant Candidate Research Report

- Generated at: 2026-05-29T17:38:39
- Config: configs/generated_stock_screen.json
- News input: data/generated_stock_news_scores.csv
- Assumed order value: 10000.00
- Minimum score: 40.00

> Research output only. This is a rules-based screen, not a return guarantee or personalized buy/sell instruction.

## Ranked Candidates

### 1. 600036

- Close: 38.01
- Total score: 45.87
- Short-term bias: rule_neutral
- Medium-term bias: rule_weak
- News score: -0.125
- News summary: 招商证券：董事长变更 (-0.33); 油价巨震风控升级 多家银行将原油基金调至R5最高风险等级 (-0.33); 银行收紧零售信贷风控？不同银行体感有温差 (-0.33)
- News URL: http://finance.eastmoney.com/a/202605273751293316.html

Advantages:
- 5-day momentum is positive
- latest close is above MA20
- RSI is in a constructive, not extreme, zone

Risks:
- 20-day momentum is negative
- reviewed recent-news score is negative

Key metrics:
- 5-day return: 2.67%
- 20-day return: -4.02%
- MA5 / MA20 / MA60: 37.214 / 37.606 / 38.8438
- RSI14: 50.95
- ATR14 pct: 1.03%
- Volume ratio 5/20: 0.981
- 20-day drawdown: -1.27%

Fee-aware rules:
- Entry trigger: 1.00%
- Stop loss: 4.00%
- Take profit: 7.20%
- Trailing stop: 3.00%
- Round-trip fee drag: 0.15%
- Minimum order value for about 30 bps fee drag: 3333.33
- Rule text: 研究规则: 只在候选评分仍达标且价格较信号收盘价上破 1.00% 后考虑入场; 从成交价回撤 4.00% 触发止损; 浮盈达到 7.20% 后分批止盈或启用 3.00% 跟踪止损; 单笔金额低于最低手续费友好金额时不交易。

### 2. 300750

- Close: 424.0
- Total score: 44.06
- Short-term bias: rule_weak
- Medium-term bias: rule_weak
- News score: 0.042
- News summary: 北京科锐澄清：与特斯拉上海签下合作协议，总装机容量仅为“初略预估量” (+0.33); 9只个股大宗交易超5000万元 (+0.00); 2026年一季报净利润为207.38亿元、宁德时代300750.SZ)较去年同期上涨48.52% (+0.00)
- News URL: http://finance.eastmoney.com/a/202605293753980822.html

Advantages:
- 5-day momentum is positive
- medium trend is not below long trend
- recent volume is above 20-day average
- reviewed recent-news score is positive

Risks:
- 20-day momentum is negative
- latest close is below MA20

Key metrics:
- 5-day return: 3.12%
- 20-day return: -0.86%
- MA5 / MA20 / MA60: 411.972 / 426.21 / 407.9608
- RSI14: 34.67
- ATR14 pct: 3.30%
- Volume ratio 5/20: 1.1819
- 20-day drawdown: -7.83%

Fee-aware rules:
- Entry trigger: 1.80%
- Stop loss: 6.74%
- Take profit: 12.13%
- Trailing stop: 4.94%
- Round-trip fee drag: 0.15%
- Minimum order value for about 30 bps fee drag: 3333.33
- Rule text: 研究规则: 只在候选评分仍达标且价格较信号收盘价上破 1.80% 后考虑入场; 从成交价回撤 6.74% 触发止损; 浮盈达到 12.13% 后分批止盈或启用 4.94% 跟踪止损; 单笔金额低于最低手续费友好金额时不交易。
