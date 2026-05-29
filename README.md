# 海通/国泰海通 ETF 低频轮动量化项目

这是一个本地量化交易工程骨架，覆盖数据、策略、回测、风控、执行适配和运维复盘。默认只支持研究、回测、模拟和影子盘；真实下单默认关闭。

## 安全边界

- 不提供投资建议，不保证收益。
- `enable_live_orders` 默认是 `false`。
- v1 不通过普通客户端 GUI 自动化提交真实订单。
- 真实程序化交易前，需要完成券商程序化交易权限确认、报告/合规流程、模拟联调和小额验收。
- 没有填写 `live_allowed_symbols` 时，即使打开实盘开关，风控也会拒绝真实下单。

## 快速开始

```powershell
$env:PYTHONPATH="src"
python -m haitong_quant.cli backtest --config configs/default.json --prices data/sample_prices.csv
python -m haitong_quant.cli signal --config configs/default.json --prices data/sample_prices.csv
python -m haitong_quant.cli screen --config configs/default.json --prices data/sample_prices.csv --news data/sample_news_scores.csv
python -m haitong_quant.cli report --config configs/default.json --prices data/sample_prices.csv --news data/sample_news_scores.csv --output reports/research_report.md
python -m haitong_quant.cli trade-plan --config configs/default.json --prices data/sample_prices.csv --news data/sample_news_scores.csv --output reports/trade_plan.json --csv-output reports/trade_plan.csv
python -m haitong_quant.cli score-news --source csv --input data/sample_raw_news.csv --output data/news_scores.generated.csv
python -m haitong_quant.cli universe --source csv --input data/sample_universe_rows.csv --output data/universe.generated.csv --config-output configs/generated_stock_screen.json --top-n 5
python -m unittest discover -s tests
```

安装研究依赖后可以接 AKShare/Backtrader，并用真实 ETF 历史数据替代样例 CSV：

```powershell
python -m pip install -e ".[research,dev]"
python -m haitong_quant.cli signal --config configs/akshare.json
python -m haitong_quant.cli backtest --config configs/akshare.json
python -m haitong_quant.cli screen --config configs/stock_screen.json --top-n 5
python -m haitong_quant.cli score-news --config configs/stock_screen.json --source akshare --output data/news_scores.generated.csv
```

## 股票/ETF 筛选

`screen` 命令会把 K 线因子和可选新闻分数合成一个研究候选列表：

- K 线因子：5 日/20 日动量、MA5/MA20/MA60、RSI14、ATR 波动率、成交量比、20 日回撤。
- 新闻输入：CSV 字段为 `symbol,score,summary,url,as_of`，分数范围是 `-1` 到 `+1`。
- 输出：候选评分、短期/中期规则倾向、优势、风险、新闻摘要、入场/止损/止盈/跟踪止损规则。
- 费用：默认把单边最低 5 元交易费、股票卖出税费估计纳入规则，输出往返费用占比和最低手续费友好金额。

示例：

```powershell
$env:PYTHONPATH="src"
python -m haitong_quant.cli screen --config configs/default.json --prices data/sample_prices.csv --news data/sample_news_scores.csv --top-n 3 --min-score 45 --order-value 10000
```

输出里的 `rule_constructive`、`rule_watchlist` 只是规则倾向，不是收益承诺。若要纳入“最近新闻”，有两条路径：

```powershell
# 1. 从原始新闻标题/摘要 CSV 自动打分，再筛选
python -m haitong_quant.cli score-news --source csv --input data/sample_raw_news.csv --output data/news_scores.generated.csv
python -m haitong_quant.cli screen --config configs/default.json --prices data/sample_prices.csv --news data/news_scores.generated.csv

# 2. 安装 AKShare 后，从东方财富个股新闻接口拉最近新闻并打分
python -m haitong_quant.cli score-news --config configs/stock_screen.json --source akshare --output data/news_scores.generated.csv
python -m haitong_quant.cli screen --config configs/stock_screen.json --news data/news_scores.generated.csv
python -m haitong_quant.cli report --config configs/stock_screen.json --news data/news_scores.generated.csv --output reports/stock_screen_report.md
python -m haitong_quant.cli trade-plan --config configs/stock_screen.json --news data/news_scores.generated.csv --output reports/stock_trade_plan.json
python -m haitong_quant.cli universe --asset-type stock --source akshare --output data/universe.generated.csv --config-output configs/generated_stock_screen.json --top-n 30 --min-amount 50000000
```

## 自动候选池

`universe` 命令会从全 A 实时行情或 ETF 实时行情里生成研究股票池：

- 默认过滤 ST/退市风险、北交所代码、低成交额、过低/过高价格、涨跌停附近标的、低换手标的。
- 输出 `data/universe.generated.csv` 供人工检查。
- 可同时输出 `configs/generated_stock_screen.json`，后续直接用于新闻抓取和报告。

示例：

```powershell
$env:PYTHONPATH="src"
python -m haitong_quant.cli universe --asset-type stock --source akshare --output data/universe.generated.csv --config-output configs/generated_stock_screen.json --top-n 30 --min-amount 50000000
python -m haitong_quant.cli score-news --config configs/generated_stock_screen.json --source akshare --output data/news_scores.generated.csv
python -m haitong_quant.cli report --config configs/generated_stock_screen.json --news data/news_scores.generated.csv --output reports/generated_stock_report.md --min-score 50
python -m haitong_quant.cli trade-plan --config configs/generated_stock_screen.json --news data/news_scores.generated.csv --output reports/generated_trade_plan.json --csv-output reports/generated_trade_plan.csv --min-score 50
```

## 自动化交接文件

`trade-plan` 命令会输出机器可读 JSON/CSV，供你的自动化程序读取：

- `entry_price`: 价格上破该值后，才进入候选入场条件。
- `pre_entry_invalidation_price`: 未成交前跌破该值，本轮信号失效。
- `stop_loss_price_if_entry_fills`: 若按 `entry_price` 成交后的止损参考价。
- `take_profit_price_if_entry_fills`: 若按 `entry_price` 成交后的止盈参考价。
- `trailing_stop_pct`: 浮盈后的跟踪止损比例。
- `estimated_round_trip_fee`: 按单笔金额和 5 元最低手续费估算的往返费用。
- `status`: `entry_candidate` 表示规则强候选，`watch_only` 表示观察，不应自动转成市价买入。

示例：

```powershell
python -m haitong_quant.cli trade-plan --config configs/default.json --prices data/sample_prices.csv --news data/sample_news_scores.csv --output reports/trade_plan.json --csv-output reports/trade_plan.csv --min-score 45
```

如果免费行情端点临时断开或超时，可以降低重试等待，或用最近保存的 `data/universe.generated.csv` / 本地 CSV 继续筛选：

```powershell
python -m haitong_quant.cli universe --asset-type stock --source akshare --retries 0 --retry-seconds 0 --output data/universe.generated.csv
python -m haitong_quant.cli universe --source csv --input data/universe.generated.csv --config-output configs/generated_stock_screen.json
```

## v1.1 daily workflow

New production-support commands:

```powershell
$env:PYTHONPATH="src"
python -m haitong_quant.cli pipeline --config configs/default.json --mode paper
python -m haitong_quant.cli monitor --config configs/default.json --trade-plan reports/trade_plan.json --once
python -m haitong_quant.cli schedule --config configs/default.json --time 15:15 --output reports/haitong_quant_pipeline.xml
python -m haitong_quant.cli optimize --config configs/default.json --train-days 15 --test-days 8 --step-days 5 --lookback-days 5,10 --top-n 1,2 --min-momentum -0.02
python -m haitong_quant.cli dashboard --config configs/default.json --trade-plan reports/trade_plan.json
```

The system now has SQLite cache integration for AKShare bars/universe/news,
portfolio-level risk checks, Pearson correlation checks, drawdown breakers,
rotating logs, decision JSONL logs, notifier hooks, a strategy factory, and a
static read-only dashboard. Live orders remain disabled unless the official
broker adapter and live allowlists are explicitly configured.

## 项目结构

- `src/haitong_quant/data`: CSV 与 AKShare 数据源
- `src/haitong_quant/strategy`: ETF 低频轮动信号
- `src/haitong_quant/backtest`: 内置回测引擎与 Backtrader 可选入口
- `src/haitong_quant/risk`: 白名单、限额、交易时段、急停、重复单等风控
- `src/haitong_quant/broker`: Mock、QMT proxy、GUI 只读占位适配器
- `src/haitong_quant/ops`: 信号到订单、影子盘和运行编排
- `configs/default.json`: 默认安全配置

## 接入官方交易接口

优先路径是向海通/国泰海通确认 e海方舟、QMT/miniQMT、PTrade 或其他正式程序化接口。若获得 QMT/miniQMT，可以用 `QmtProxyBroker` 对接本机 `quant-qmt-proxy` 风格 REST 服务；适配器仍会在 `allow_orders=false` 时拒绝下单。

普通 `e海通财/海通通财` GUI 自动化只适合作为控件调研或只读辅助，不纳入 v1 实盘提交链路。

## 第一版策略

ETF 低频轮动按日频数据计算动量：

1. 只看 ETF 白名单。
2. 每次再平衡只使用再平衡日前一交易日及更早数据。
3. 选出 `top_n` 个动量最高且超过 `min_momentum` 的 ETF。
4. 目标权重等分，未入选标的目标权重为 0。

内置回测在下一交易日收盘价成交，包含手续费和滑点参数，避免使用当天未来价格生成当天成交。
