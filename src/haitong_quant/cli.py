from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import json

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path

from haitong_quant.analysis import (
    AKShareStockNewsSource,
    AKShareUniverseSource,
    KeywordNewsScorer,
    KlineNewsScreener,
    NewsCSVSource,
    RawNewsCSVSource,
    TradeJournal,
    UniverseFilter,
    UniverseSelector,
    build_trade_plan,
    generate_daily_report,
    get_or_calculate_correlation_matrix,
    load_industry_map,
    render_research_report,
    write_config_with_universe,
    write_daily_report,
    write_news_scores,
    write_research_report,
    write_trade_plan_csv,
    write_trade_plan_json,
    write_universe_csv,
)
from haitong_quant.backtest import (
    BacktestEngine,
    WalkForwardEngine,
    run_parameter_grid,
    write_optimization_csv,
    write_optimization_heatmap_csv,
)
from haitong_quant.broker import MockBroker, PaperTradingEngine
from haitong_quant.config import QuantConfig, load_config
from haitong_quant.data import AKShareDataSource, CSVDataSource, DataCache
from haitong_quant.logging_config import setup_logging
from haitong_quant.models import Side
from haitong_quant.ops import (
    build_notifier,
    build_order_intents,
    latest_close_prices,
    make_risk_engine,
    monitor_loop,
    render_static_dashboard,
    render_windows_task_xml,
    serve_dashboard,
    write_static_dashboard,
    write_windows_task_xml,
)
from haitong_quant.strategy import build_strategy


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(prog="haitong-quant")
    sub = parser.add_subparsers(dest="command", required=True)

    _add_backtest(sub)
    _add_signal(sub)
    _add_dry_run(sub)
    _add_screen(sub)
    _add_score_news(sub)
    _add_report(sub)
    _add_trade_plan(sub)
    _add_universe(sub)
    _add_daily_report(sub)
    _add_walk_forward(sub)
    _add_paper(sub)
    _add_pipeline(sub)
    _add_monitor(sub)
    _add_notify_test(sub)
    _add_schedule(sub)
    _add_optimize(sub)
    _add_dashboard(sub)

    args = parser.parse_args()
    if args.command == "universe":
        _cmd_universe(args)
        return
    if args.command == "schedule":
        _cmd_schedule(args)
        return

    config = load_config(args.config)
    strategy = build_strategy(config.strategy)

    if args.command == "backtest":
        bars_by_symbol = _load_bars(config, args.prices)
        engine = BacktestEngine(
            strategy=strategy,
            starting_cash=config.backtest.starting_cash,
            commission_bps=config.backtest.commission_bps,
            slippage_bps=config.backtest.slippage_bps,
            rebalance_days=config.strategy.rebalance_days,
            lot_size=config.execution.lot_size,
        )
        result = engine.run(bars_by_symbol)
        print(_to_json({"metrics": result.metrics, "orders": len(result.orders)}))
    elif args.command == "signal":
        bars_by_symbol = _load_bars(config, args.prices)
        signals = strategy.generate_signals(bars_by_symbol)
        print(_to_json([asdict(signal) for signal in signals]))
    elif args.command == "dry-run":
        print(_to_json(_run_dry_run(config, args.prices)))
    elif args.command == "screen":
        candidates = _screen_candidates(
            config,
            prices_override=args.prices,
            news_path=args.news,
            raw_news_path=args.raw_news,
            top_n=args.top_n,
            order_value=args.order_value,
            min_score=args.min_score,
        )
        print(_to_json([asdict(result) for result in candidates]))
    elif args.command == "score-news":
        print(_to_json(_cmd_score_news(config, args)))
    elif args.command == "report":
        candidates = _screen_candidates(
            config,
            prices_override=args.prices,
            news_path=args.news,
            raw_news_path=args.raw_news,
            top_n=args.top_n,
            order_value=args.order_value,
            min_score=args.min_score,
        )
        content = render_research_report(
            candidates,
            config_path=args.config,
            news_path=args.news or args.raw_news or "",
            order_value=args.order_value,
            min_score=args.min_score,
        )
        write_research_report(args.output, content)
        print(_to_json({"output": args.output, "candidates": [item.symbol for item in candidates]}))
    elif args.command == "trade-plan":
        print(_to_json(_cmd_trade_plan(config, args)))
    elif args.command == "daily-report":
        print(_to_json(_cmd_daily_report(config, args)))
    elif args.command == "walk-forward":
        bars_by_symbol = _load_bars(config, args.prices)
        engine = WalkForwardEngine(
            strategy=strategy,
            train_days=args.train_days,
            test_days=args.test_days,
            step_days=args.step_days,
            starting_cash=config.backtest.starting_cash,
            commission_bps=config.backtest.commission_bps,
            slippage_bps=config.backtest.slippage_bps,
            rebalance_days=config.strategy.rebalance_days,
            lot_size=config.execution.lot_size,
        )
        result = engine.run(bars_by_symbol)
        print(_to_json({"windows": [asdict(w) for w in result.windows], "aggregate": result.aggregate_metrics}))
    elif args.command == "paper":
        print(_to_json(_run_paper(config, args.prices, args.max_slippage_pct)))
    elif args.command == "pipeline":
        print(_to_json(_cmd_pipeline(config, args)))
    elif args.command == "monitor":
        print(_to_json(_cmd_monitor(config, args)))
    elif args.command == "notify-test":
        print(_to_json(_cmd_notify_test(config, args)))
    elif args.command == "optimize":
        print(_to_json(_cmd_optimize(config, args)))
    elif args.command == "dashboard":
        print(_to_json(_cmd_dashboard(config, args)))


def _add_common_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--prices", default=None)


def _add_backtest(sub) -> None:
    parser = sub.add_parser("backtest", help="Run ETF rotation backtest")
    _add_common_config(parser)


def _add_signal(sub) -> None:
    parser = sub.add_parser("signal", help="Generate latest target-weight signals")
    _add_common_config(parser)


def _add_dry_run(sub) -> None:
    parser = sub.add_parser("dry-run", help="Generate and risk-check orders against mock account")
    _add_common_config(parser)


def _add_screen(sub) -> None:
    parser = sub.add_parser("screen", help="Rank candidates with K-line and news scores")
    _add_common_config(parser)
    _add_screening_args(parser)


def _add_score_news(sub) -> None:
    parser = sub.add_parser("score-news", help="Convert raw recent news into news-score CSV")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--source", choices=["csv", "akshare"], default="csv")
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-items", type=int, default=20)


def _add_report(sub) -> None:
    parser = sub.add_parser("report", help="Write a Markdown candidate research report")
    _add_common_config(parser)
    _add_screening_args(parser)
    parser.add_argument("--output", default="reports/research_report.md")


def _add_trade_plan(sub) -> None:
    parser = sub.add_parser("trade-plan", help="Write machine-readable entry/exit rules")
    _add_common_config(parser)
    _add_screening_args(parser)
    parser.add_argument("--output", default="reports/trade_plan.json")
    parser.add_argument("--csv-output", default=None)


def _add_universe(sub) -> None:
    parser = sub.add_parser("universe", help="Generate a research universe")
    parser.add_argument("--asset-type", choices=["stock", "etf"], default="stock")
    parser.add_argument("--source", choices=["akshare", "csv"], default="akshare")
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default="data/universe.generated.csv")
    parser.add_argument("--config-output", default=None)
    parser.add_argument("--base-config", default="configs/stock_screen.json")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--min-amount", type=float, default=50_000_000.0)
    parser.add_argument("--min-price", type=float, default=2.0)
    parser.add_argument("--max-price", type=float, default=500.0)
    parser.add_argument("--max-abs-pct-change", type=float, default=9.5)
    parser.add_argument("--min-turnover", type=float, default=0.2)
    parser.add_argument("--include-st", action="store_true")
    parser.add_argument("--include-bj", action="store_true")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    parser.add_argument("--cache-db", default="data/cache.db")
    parser.add_argument("--cache-max-age-days", type=int, default=1)
    parser.add_argument("--no-cache", action="store_true")


def _add_daily_report(sub) -> None:
    parser = sub.add_parser("daily-report", help="Generate post-close research daily report")
    _add_common_config(parser)
    _add_screening_args(parser)
    parser.add_argument("--output", default="reports/daily_report.md")
    parser.add_argument("--journal-db", default="data/journal.db")


def _add_walk_forward(sub) -> None:
    parser = sub.add_parser("walk-forward", help="Run walk-forward backtest")
    _add_common_config(parser)
    parser.add_argument("--train-days", type=int, default=252)
    parser.add_argument("--test-days", type=int, default=63)
    parser.add_argument("--step-days", type=int, default=63)


def _add_paper(sub) -> None:
    parser = sub.add_parser("paper", help="Validate current signals through paper matching")
    _add_common_config(parser)
    parser.add_argument("--max-slippage-pct", type=float, default=0.02)


def _add_pipeline(sub) -> None:
    parser = sub.add_parser("pipeline", help="Run daily data -> plan -> paper -> report workflow")
    _add_common_config(parser)
    _add_screening_args(parser)
    parser.add_argument("--mode", choices=["research", "paper", "live"], default="paper")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--journal-db", default="data/journal.db")
    parser.add_argument("--max-slippage-pct", type=float, default=0.02)


def _add_monitor(sub) -> None:
    parser = sub.add_parser("monitor", help="Monitor trade-plan stop/take-profit alerts")
    _add_common_config(parser)
    parser.add_argument("--trade-plan", default="reports/trade_plan.json")
    parser.add_argument("--alerts", default=None)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--notifier", choices=["console", "webhook", "wechat", "wecom", "smtp", "serverchan"], default=None)


def _add_notify_test(sub) -> None:
    parser = sub.add_parser("notify-test", help="Send a safe notifier test message")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--notifier", choices=["console", "webhook", "wechat", "wecom", "smtp", "serverchan"], default=None)
    parser.add_argument("--title", default="海通量化提醒测试")
    parser.add_argument("--body", default="这是一条通知通道测试消息，不涉及交易。")


def _add_schedule(sub) -> None:
    parser = sub.add_parser("schedule", help="Generate Windows Task Scheduler XML")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--time", default="15:15")
    parser.add_argument("--mode", choices=["research", "paper"], default="paper")
    parser.add_argument("--output", default="reports/haitong_quant_pipeline.xml")


def _add_optimize(sub) -> None:
    parser = sub.add_parser("optimize", help="Run parameter grid walk-forward optimization")
    _add_common_config(parser)
    parser.add_argument("--grid", default="")
    parser.add_argument("--lookback-days", default="10,20,40")
    parser.add_argument("--top-n", default="1,2,3")
    parser.add_argument("--min-momentum", default="-0.02,0,0.02")
    parser.add_argument("--train-days", type=int, default=252)
    parser.add_argument("--test-days", type=int, default=63)
    parser.add_argument("--step-days", type=int, default=63)
    parser.add_argument("--output", default="reports/optimization.csv")
    parser.add_argument("--heatmap-output", default="reports/optimization_heatmap.csv")
    parser.add_argument("--heatmap-metric", default="avg_test_sharpe")


def _add_dashboard(sub) -> None:
    parser = sub.add_parser("dashboard", help="Write a read-only static dashboard")
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--trade-plan", default="reports/trade_plan.json")
    parser.add_argument("--daily-report", default="reports/daily_report.md")
    parser.add_argument("--output", default=None)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)


def _add_screening_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--news", default=None)
    parser.add_argument("--raw-news", default=None)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--order-value", type=float, default=10000.0)
    parser.add_argument("--min-score", type=float, default=55.0)


def _cmd_universe(args) -> None:
    universe_filter = UniverseFilter(
        asset_type=args.asset_type,
        top_n=args.top_n,
        min_amount=args.min_amount,
        min_price=args.min_price,
        max_price=args.max_price,
        max_abs_pct_change=args.max_abs_pct_change,
        min_turnover=args.min_turnover,
        exclude_st=not args.include_st,
        include_bj=args.include_bj,
    )
    if args.source == "csv":
        if not args.input:
            raise SystemExit("--input is required when --source csv")
        from haitong_quant.analysis import CSVUniverseSource

        rows = CSVUniverseSource(args.input).fetch_rows()
    else:
        cache = None if args.no_cache else DataCache(args.cache_db)
        rows = AKShareUniverseSource(
            retries=args.retries,
            retry_seconds=args.retry_seconds,
            cache=cache,
            cache_max_age_days=args.cache_max_age_days,
        ).fetch_rows(args.asset_type)
    members = UniverseSelector(universe_filter).select(rows)
    write_universe_csv(args.output, members)
    payload = {"output": args.output, "symbols": [member.symbol for member in members]}
    if args.config_output:
        write_config_with_universe(
            base_config_path=args.base_config,
            output_path=args.config_output,
            members=members,
            asset_type=args.asset_type,
        )
        payload["config_output"] = args.config_output
    print(_to_json(payload))


def _cmd_score_news(config: QuantConfig, args) -> dict:
    cache = _make_cache(config)
    if args.source == "akshare":
        try:
            raw_items = AKShareStockNewsSource(max_items_per_symbol=args.max_items).load(
                config.strategy.symbols
            )
            scores = KeywordNewsScorer().score_items(raw_items)
        except Exception:
            cached = cache.get_news_scores() if cache is not None else None
            if not cached:
                raise
            scores = {
                symbol: _news_score_from_dict(data)
                for symbol, data in cached.items()
            }
    else:
        if not args.input:
            raise SystemExit("--input is required when --source csv")
        raw_items = RawNewsCSVSource(args.input).load()
        scores = KeywordNewsScorer().score_items(raw_items)
    write_news_scores(args.output, scores)
    if cache is not None:
        cache.put_news_scores({symbol: asdict(score) for symbol, score in scores.items()})
    return {"output": args.output, "symbols": sorted(scores)}


def _cmd_trade_plan(config: QuantConfig, args) -> dict:
    candidates = _screen_candidates(
        config,
        prices_override=args.prices,
        news_path=args.news,
        raw_news_path=args.raw_news,
        top_n=args.top_n,
        order_value=args.order_value,
        min_score=args.min_score,
    )
    items = build_trade_plan(candidates, order_value=args.order_value)
    write_trade_plan_json(
        args.output,
        items,
        config_path=args.config,
        news_path=args.news or args.raw_news or "",
        min_score=args.min_score,
    )
    if args.csv_output:
        write_trade_plan_csv(args.csv_output, items)
    return {"output": args.output, "csv_output": args.csv_output, "symbols": [item.symbol for item in items]}


def _cmd_daily_report(config: QuantConfig, args) -> dict:
    candidates = _screen_candidates(
        config,
        prices_override=args.prices,
        news_path=args.news,
        raw_news_path=args.raw_news,
        top_n=args.top_n,
        order_value=args.order_value,
        min_score=args.min_score,
    )
    plan = build_trade_plan(candidates, order_value=args.order_value)
    journal_summary = _load_journal_summary(args.journal_db)
    content = generate_daily_report(
        candidates=candidates,
        trade_plan=plan,
        journal_summary=journal_summary,
        config_path=args.config,
        order_value=args.order_value,
    )
    write_daily_report(args.output, content)
    return {"output": args.output, "candidates": len(candidates)}


def _cmd_pipeline(config: QuantConfig, args) -> dict:
    if args.mode == "live":
        if not config.execution.enable_live_orders or config.broker.kind == "mock":
            raise SystemExit("live mode requires enable_live_orders=true and a non-mock broker")

    output_dir = Path(args.output_dir or _default_run_dir(config))
    output_dir.mkdir(parents=True, exist_ok=True)
    bars_by_symbol = _load_bars(config, args.prices)
    news = _load_news(args.news, args.raw_news)
    candidates = _screen_loaded(
        config,
        bars_by_symbol,
        news,
        top_n=args.top_n,
        order_value=args.order_value,
        min_score=args.min_score,
    )
    plan = build_trade_plan(candidates, order_value=args.order_value)
    plan_path = output_dir / "trade_plan.json"
    write_trade_plan_json(
        plan_path,
        plan,
        config_path=args.config,
        news_path=args.news or args.raw_news or "",
        min_score=args.min_score,
    )
    paper_payload = None
    if args.mode in {"paper", "live"}:
        paper_payload = _run_paper_loaded(config, bars_by_symbol, args.max_slippage_pct)
        (output_dir / "paper_report.json").write_text(
            _to_json(paper_payload) + "\n", encoding="utf-8"
        )
    journal_records = _record_plan_to_journal(args.journal_db, plan)
    daily_path = output_dir / "daily_report.md"
    content = generate_daily_report(
        candidates=candidates,
        trade_plan=plan,
        journal_summary=_load_journal_summary(args.journal_db),
        config_path=args.config,
        order_value=args.order_value,
    )
    write_daily_report(daily_path, content)
    dashboard_path = output_dir / "dashboard.html"
    write_static_dashboard(
        dashboard_path,
        render_static_dashboard(
            trade_plan_path=plan_path,
            daily_report_path=daily_path,
            config_path=args.config,
            paper_report=paper_payload,
            dashboard_poll_interval_seconds=config.ops.dashboard_poll_interval_seconds,
            dashboard_min_poll_interval_seconds=config.ops.dashboard_min_poll_interval_seconds,
        ),
    )
    manifest = {
        "mode": args.mode,
        "output_dir": str(output_dir),
        "trade_plan": str(plan_path),
        "daily_report": str(daily_path),
        "dashboard": str(dashboard_path),
        "journal_records": journal_records,
        "candidates": [item.symbol for item in candidates],
        "paper": paper_payload,
    }
    (output_dir / "manifest.json").write_text(_to_json(manifest) + "\n", encoding="utf-8")
    return manifest


def _cmd_monitor(config: QuantConfig, args) -> dict:
    alerts_path = args.alerts or config.ops.alerts_path
    notifier_kind = args.notifier or config.ops.notifier.type
    notifier = build_notifier(notifier_kind)

    def load_prices() -> dict[str, float]:
        return latest_close_prices(_load_bars(config, args.prices))

    alerts = monitor_loop(
        trade_plan_path=args.trade_plan,
        price_loader=load_prices,
        alerts_path=alerts_path,
        notifier=notifier,
        interval_seconds=args.interval_seconds,
        once=args.once,
    )
    return {
        "alerts": [asdict(alert) for alert in alerts],
        "alerts_path": alerts_path,
        "notifier": notifier_kind,
    }


def _cmd_notify_test(config: QuantConfig, args) -> dict:
    notifier_kind = args.notifier or config.ops.notifier.type
    notifier = build_notifier(notifier_kind)
    try:
        notifier.send(args.title, args.body)
    except Exception as exc:
        return {"notifier": notifier_kind, "sent": False, "error": str(exc)}
    return {"notifier": notifier_kind, "sent": True}


def _cmd_schedule(args) -> None:
    hour, minute = _parse_hhmm(args.time)
    start = datetime.combine(date.today(), datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    xml = render_windows_task_xml(
        command=sys.executable,
        arguments=f"-m haitong_quant.cli pipeline --config {args.config} --mode {args.mode}",
        working_directory=str(Path.cwd()),
        start_time=start.isoformat(timespec="seconds"),
    )
    write_windows_task_xml(args.output, xml)
    print(_to_json({"output": args.output, "start_time": start.isoformat(timespec="seconds")}))


def _cmd_optimize(config: QuantConfig, args) -> dict:
    grid = _parse_grid(args)
    bars_by_symbol = _load_bars(config, args.prices)
    results = run_parameter_grid(
        config,
        bars_by_symbol,
        lookback_days=grid["lookback_days"],
        top_n=grid["top_n"],
        min_momentum=grid["min_momentum"],
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
    )
    write_optimization_csv(args.output, results)
    write_optimization_heatmap_csv(
        args.heatmap_output,
        results,
        metric=args.heatmap_metric,
    )
    return {
        "output": args.output,
        "heatmap_output": args.heatmap_output,
        "best": asdict(results[0]) if results else None,
        "count": len(results),
    }


def _cmd_dashboard(config: QuantConfig, args) -> dict:
    if args.serve:
        serve_dashboard(
            trade_plan_path=args.trade_plan,
            daily_report_path=args.daily_report,
            config_path=args.config,
            host=args.host,
            port=args.port,
            dashboard_poll_interval_seconds=config.ops.dashboard_poll_interval_seconds,
            dashboard_min_poll_interval_seconds=config.ops.dashboard_min_poll_interval_seconds,
        )
        return {"served": True, "url": f"http://{args.host}:{args.port}"}
    output = args.output or config.ops.dashboard_path
    content = render_static_dashboard(
        trade_plan_path=args.trade_plan,
        daily_report_path=args.daily_report,
        config_path=args.config,
        dashboard_poll_interval_seconds=config.ops.dashboard_poll_interval_seconds,
        dashboard_min_poll_interval_seconds=config.ops.dashboard_min_poll_interval_seconds,
    )
    write_static_dashboard(output, content)
    return {"output": output}


def _run_dry_run(config: QuantConfig, prices_override: str | None) -> dict:
    bars_by_symbol = _load_bars(config, prices_override)
    strategy = build_strategy(config.strategy)
    broker = MockBroker(starting_cash=config.broker.starting_cash)
    broker.connect()
    prices = latest_close_prices(bars_by_symbol)
    signals = strategy.generate_signals(bars_by_symbol)
    intents = build_order_intents(
        signals,
        broker.get_account_snapshot(),
        prices,
        strategy_id=config.strategy.id,
        lot_size=config.execution.lot_size,
        slippage_bps=config.execution.default_limit_slippage_bps,
    )
    risk = _make_risk_engine_with_context(config, bars_by_symbol)
    decisions = []
    for intent in intents:
        decision = risk.validate(
            intent,
            broker.get_account_snapshot(),
            prices,
            now=datetime.now().replace(hour=10, minute=0, second=0, microsecond=0),
        )
        decisions.append({"order": asdict(intent), "decision": asdict(decision)})
        if decision.approved and decision.adjusted_order:
            broker.submit_order(decision.adjusted_order)
    return {"decisions": decisions, "cash": broker.get_cash(), "positions": broker.get_positions()}


def _run_paper(config: QuantConfig, prices_override: str | None, max_slippage_pct: float) -> dict:
    bars_by_symbol = _load_bars(config, prices_override)
    return _run_paper_loaded(config, bars_by_symbol, max_slippage_pct)


def _run_paper_loaded(
    config: QuantConfig,
    bars_by_symbol: dict,
    max_slippage_pct: float,
) -> dict:
    broker = MockBroker(starting_cash=config.broker.starting_cash)
    broker.connect()
    prices = latest_close_prices(bars_by_symbol)
    signals = build_strategy(config.strategy).generate_signals(bars_by_symbol)
    intents = build_order_intents(
        signals,
        broker.get_account_snapshot(),
        prices,
        strategy_id=config.strategy.id,
        lot_size=config.execution.lot_size,
        slippage_bps=config.execution.default_limit_slippage_bps,
    )
    paper = PaperTradingEngine(
        starting_cash=config.broker.starting_cash,
        max_slippage_pct=max_slippage_pct,
    )
    report = paper.validate(intents, prices)
    return {
        "all_passed": report.all_passed,
        "summary": report.summary,
        "results": [
            {"symbol": r.order.symbol, "passed": r.passed, "reason": r.reason}
            for r in report.results
        ],
    }


def _screen_candidates(
    config: QuantConfig,
    *,
    prices_override: str | None,
    news_path: str | None,
    raw_news_path: str | None,
    top_n: int,
    order_value: float,
    min_score: float,
):
    bars_by_symbol = _load_bars(config, prices_override)
    news = _load_news(news_path, raw_news_path)
    return _screen_loaded(config, bars_by_symbol, news, top_n=top_n, order_value=order_value, min_score=min_score)


def _screen_loaded(
    config: QuantConfig,
    bars_by_symbol: dict,
    news,
    *,
    top_n: int,
    order_value: float,
    min_score: float,
):
    screener = KlineNewsScreener(
        min_trade_fee=config.execution.min_trade_fee,
        stock_sell_tax_bps=config.execution.stock_sell_tax_bps,
        default_order_value=order_value,
        min_score=min_score,
    )
    return screener.screen(bars_by_symbol, news_by_symbol=news, top_n=top_n)


def _load_news(news_path: str | None, raw_news_path: str | None):
    if raw_news_path:
        return KeywordNewsScorer().score_items(RawNewsCSVSource(raw_news_path).load())
    if news_path:
        return NewsCSVSource(news_path).load()
    return {}


def _load_bars(config: QuantConfig, prices_override: str | None):
    if config.data.source == "akshare" and not prices_override:
        cache = _make_cache(config)
        return AKShareDataSource(
            adjust=config.data.adjust,
            asset_type=config.data.asset_type,
            cache=cache,
            cache_max_age_days=config.cache.max_age_days if config.cache.enabled else None,
        ).load_bars(config.strategy.symbols)
    csv_path = prices_override or config.data.csv_path
    return CSVDataSource(Path(csv_path)).load_bars(config.strategy.symbols)


def _make_cache(config: QuantConfig) -> DataCache | None:
    return DataCache(config.cache.db_path) if config.cache.enabled else None


def _make_risk_engine_with_context(config: QuantConfig, bars_by_symbol: dict):
    cache = _make_cache(config)
    industry_map = load_industry_map(
        config.risk.portfolio.industry_map_path,
        list(config.strategy.symbols),
        use_akshare=False,
    )
    correlation_matrix = get_or_calculate_correlation_matrix(
        bars_by_symbol,
        cache=cache,
        window=config.risk.portfolio.correlation_window,
        source=config.data.source,
        asset_type=config.data.asset_type,
        adjust=config.data.adjust,
    )
    return make_risk_engine(
        config,
        industry_map=industry_map,
        correlation_matrix=correlation_matrix,
    )


def _load_journal_summary(journal_db: str):
    journal_path = Path(journal_db)
    if not journal_path.exists():
        return None
    journal = TradeJournal(journal_path)
    try:
        return journal.summary()
    finally:
        journal.close()


def _record_plan_to_journal(journal_db: str, plan) -> int:
    if not plan:
        return 0
    journal = TradeJournal(journal_db)
    count = 0
    try:
        today = date.today().isoformat()
        for item in plan:
            signal_id = f"{today}:{item.symbol}:{item.entry_price:.4f}"
            journal.record_signal(
                signal_id=signal_id,
                signal_date=today,
                symbol=item.symbol,
                direction=Side.BUY.value,
                entry_price=item.entry_price,
                stop_loss_price=item.stop_loss_price_if_entry_fills,
                take_profit_price=item.take_profit_price_if_entry_fills,
                score=item.total_score,
                notes=item.status,
            )
            count += 1
    finally:
        journal.close()
    return count


def _news_score_from_dict(data: dict):
    from haitong_quant.analysis.news import NewsScore

    return NewsScore(
        symbol=str(data.get("symbol", "")),
        score=float(data.get("score", 0.0)),
        summary=str(data.get("summary", "")),
        url=str(data.get("url", "")),
        as_of=str(data.get("as_of", "")),
        event_type=str(data.get("event_type", "other")),
        confidence=float(data.get("confidence", 0.0)),
        source_name=str(data.get("source_name", "")),
    )


def _default_run_dir(config: QuantConfig) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return str(Path(config.ops.pipeline_output_dir) / stamp)


def _parse_hhmm(value: str) -> tuple[int, int]:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour, parsed.minute


def _parse_grid(args) -> dict[str, list]:
    values = {
        "lookback_days": _int_list(args.lookback_days),
        "top_n": _int_list(args.top_n),
        "min_momentum": _float_list(args.min_momentum),
    }
    if args.grid:
        for chunk in args.grid.split(";"):
            if not chunk.strip():
                continue
            key, raw = chunk.split("=", 1)
            key = key.strip()
            if key in {"lookback_days", "top_n"}:
                values[key] = _int_list(raw)
            elif key == "min_momentum":
                values[key] = _float_list(raw)
            else:
                raise ValueError(f"Unsupported grid key: {key}")
    return values


def _int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


if __name__ == "__main__":
    main()
