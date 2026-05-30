from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import patch

from haitong_quant.analysis.correlation import calculate_correlation_matrix
from haitong_quant.backtest.optimizer import OptimizationResult, write_optimization_heatmap_csv
from haitong_quant.cli import _cmd_notify_test, _cmd_pipeline
from haitong_quant.config import load_config
from haitong_quant.data import AKShareDataSource, DataCache
from haitong_quant.logging_config import setup_logging
from haitong_quant.models import AccountSnapshot, Bar, OrderIntent, Side
from haitong_quant.ops.monitor import evaluate_trade_plan, monitor_loop
from haitong_quant.ops.notifiers import ConsoleNotifier, WebhookNotifier, _resolve_ca_bundle, build_notifier
from haitong_quant.ops.scheduler import render_windows_task_xml
from haitong_quant.risk import PortfolioRiskChecker, PortfolioRiskConfig, RiskEngine, RuntimeRiskConfig
from haitong_quant.strategy import build_strategy


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class V11FeatureTests(unittest.TestCase):
    def test_cache_keys_include_source_asset_type_and_adjust(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DataCache(Path(tmp) / "cache.db")
            etf_bars = [Bar(date(2026, 1, 2), "510300", 1, 1, 1, 1, 10)]
            stock_bars = [Bar(date(2026, 1, 2), "510300", 2, 2, 2, 2, 20)]

            cache.put_bars("510300", etf_bars, source="akshare", asset_type="etf", adjust="qfq")
            cache.put_bars("510300", stock_bars, source="akshare", asset_type="stock", adjust="hfq")

            loaded_etf = cache.get_bars("510300", source="akshare", asset_type="etf", adjust="qfq")
            loaded_stock = cache.get_bars("510300", source="akshare", asset_type="stock", adjust="hfq")

            self.assertEqual(loaded_etf[0].close, 1)
            self.assertEqual(loaded_stock[0].close, 2)
            cache.close()

    def test_universe_cache_uses_chinese_code_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DataCache(Path(tmp) / "cache.db")
            cache.put_universe("stock", [{"代码": "600036", "名称": "招商银行"}], source="akshare")
            loaded = cache.get_universe("stock", source="akshare")

            self.assertEqual(loaded[0]["代码"], "600036")
            rows = cache._get_conn().execute("SELECT symbol FROM universe").fetchall()
            self.assertEqual(rows[0][0], "600036")
            cache.close()

    def test_akshare_data_source_uses_fresh_cache(self):
        calls = {"count": 0}

        def fund_etf_hist_em(**kwargs):
            calls["count"] += 1
            return FakeFrame(
                [
                    {
                        "日期": "2026-01-02",
                        "开盘": 4.0,
                        "最高": 4.2,
                        "最低": 3.9,
                        "收盘": 4.1,
                        "成交量": 1000,
                    }
                ]
            )

        fake_akshare = types.SimpleNamespace(fund_etf_hist_em=fund_etf_hist_em)
        old_module = sys.modules.get("akshare")
        sys.modules["akshare"] = fake_akshare
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cache = DataCache(Path(tmp) / "cache.db")
                source = AKShareDataSource(cache=cache, cache_max_age_days=30)
                first = source.load_bars(["510300"])
                second = source.load_bars(["510300"])
                self.assertEqual(first["510300"][0].close, 4.1)
                self.assertEqual(second["510300"][0].close, 4.1)
                self.assertEqual(calls["count"], 1)
                cache.close()
        finally:
            if old_module is None:
                sys.modules.pop("akshare", None)
            else:
                sys.modules["akshare"] = old_module

    def test_risk_engine_calls_portfolio_checker_and_records_entries(self):
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_daily_entries=1))
        engine = RiskEngine(
            RuntimeRiskConfig(
                allowed_symbols={"510300", "510500"},
                max_single_order_value=100000,
                max_daily_trade_value=200000,
                max_symbol_weight=1.0,
                trading_start=time(9, 30),
                trading_end=time(14, 55),
                portfolio_checker=checker,
                max_intraday_drawdown_pct=0,
                max_total_drawdown_pct=0,
            )
        )
        account = AccountSnapshot(cash=100000, positions={}, as_of=datetime(2026, 1, 2, 10))
        prices = {"510300": 4.0, "510500": 5.0}
        now = datetime(2026, 1, 2, 10)

        first = engine.validate(OrderIntent("510300", Side.BUY.value, 100, 4.0, "test"), account, prices, now)
        second = engine.validate(OrderIntent("510500", Side.BUY.value, 100, 5.0, "test"), account, prices, now)

        self.assertTrue(first.approved)
        self.assertFalse(second.approved)
        self.assertTrue(second.reason.startswith("portfolio_risk:"))

    def test_drawdown_breaker_writes_kill_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            kill = Path(tmp) / "KILL_SWITCH"
            engine = RiskEngine(
                RuntimeRiskConfig(
                    allowed_symbols={"510300", "510500"},
                    max_single_order_value=100000,
                    max_daily_trade_value=200000,
                    max_symbol_weight=1.0,
                    trading_start=time(9, 30),
                    trading_end=time(14, 55),
                    manual_kill_switch_path=kill,
                    max_intraday_drawdown_pct=0,
                    max_total_drawdown_pct=0.05,
                )
            )
            high = AccountSnapshot(cash=100000, positions={}, as_of=datetime(2026, 1, 2, 10))
            low = AccountSnapshot(cash=94000, positions={}, as_of=datetime(2026, 1, 2, 10, 1))
            prices = {"510300": 4.0, "510500": 5.0}

            self.assertTrue(
                engine.validate(
                    OrderIntent("510300", Side.BUY.value, 100, 4.0, "test"),
                    high,
                    prices,
                    datetime(2026, 1, 2, 10),
                ).approved
            )
            decision = engine.validate(
                OrderIntent("510500", Side.BUY.value, 100, 5.0, "test"),
                low,
                prices,
                datetime(2026, 1, 2, 10, 1),
            )

            self.assertFalse(decision.approved)
            self.assertEqual(decision.reason, "total_drawdown_breaker_active")
            self.assertTrue(kill.exists())

    def test_correlation_monitor_scheduler_and_strategy_factory(self):
        bars = {
            "510300": [
                Bar(date(2026, 1, 1), "510300", 1, 1, 1, 1),
                Bar(date(2026, 1, 2), "510300", 2, 2, 2, 2),
                Bar(date(2026, 1, 3), "510300", 3, 3, 3, 3),
            ],
            "510500": [
                Bar(date(2026, 1, 1), "510500", 1, 1, 1, 2),
                Bar(date(2026, 1, 2), "510500", 2, 2, 2, 4),
                Bar(date(2026, 1, 3), "510500", 3, 3, 3, 6),
            ],
        }
        matrix = calculate_correlation_matrix(bars, window=3, min_overlap=2)
        self.assertAlmostEqual(matrix[("510300", "510500")], 1.0)

        config = load_config("configs/default.json")
        self.assertEqual(build_strategy(config.strategy).strategy_id, config.strategy.id)

        xml = render_windows_task_xml(
            command="python",
            arguments="-m haitong_quant.cli pipeline",
            working_directory=".",
            start_time="2026-05-29T15:15:00",
        )
        self.assertIn("CalendarTrigger", xml)
        self.assertIsInstance(build_notifier("serverchan"), ConsoleNotifier)

        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "symbol": "510300",
                                "status": "entry_candidate",
                                "entry_price": 4.1,
                                "pre_entry_invalidation_price": 3.8,
                                "stop_loss_price_if_entry_fills": 3.7,
                                "take_profit_price_if_entry_fills": 4.5,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            alerts = evaluate_trade_plan(plan, {"510300": 4.6})
            self.assertEqual(alerts[0].alert_type, "entry_triggered")
            self.assertEqual(alerts[1].alert_type, "take_profit_triggered")

    def test_wechat_notifier_alias_and_payload(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(build_notifier("wechat"), ConsoleNotifier)

        webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-token"
        with patch.dict(os.environ, {"HAITONG_QUANT_WECHAT_WEBHOOK_URL": webhook_url}, clear=True):
            self.assertIsInstance(build_notifier("wecom"), WebhookNotifier)

        sent_payloads = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"errcode":0}'

        def fake_urlopen(req, **kwargs):
            sent_payloads.append({"payload": json.loads(req.data.decode("utf-8")), "kwargs": kwargs})
            return FakeResponse()

        with patch("haitong_quant.ops.notifiers.request.urlopen", fake_urlopen):
            WebhookNotifier(webhook_url).send("测试标题", "测试正文")

        self.assertEqual(sent_payloads[0]["payload"]["msgtype"], "text")
        self.assertIn("测试标题", sent_payloads[0]["payload"]["text"]["content"])
        self.assertIn("timeout", sent_payloads[0]["kwargs"])
        self.assertNotIn("secret-token", json.dumps(sent_payloads[0]["payload"], ensure_ascii=False))

    def test_ca_bundle_can_be_overridden_for_enterprise_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            ca_path = Path(tmp) / "ca.pem"
            ca_path.write_text("placeholder", encoding="utf-8")

            with patch.dict(os.environ, {"HAITONG_QUANT_CA_BUNDLE": str(ca_path)}, clear=True):
                self.assertEqual(_resolve_ca_bundle(), str(ca_path))

    def test_monitor_loop_deduplicates_repeated_alerts(self):
        class CollectingNotifier:
            def __init__(self):
                self.messages = []

            def send(self, title, body):
                self.messages.append((title, body))

        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            alerts_path = Path(tmp) / "alerts.jsonl"
            plan.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "symbol": "510300",
                                "status": "entry_candidate",
                                "entry_price": 4.1,
                                "pre_entry_invalidation_price": 3.8,
                                "stop_loss_price_if_entry_fills": 3.7,
                                "take_profit_price_if_entry_fills": 4.5,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            notifier = CollectingNotifier()

            first = monitor_loop(
                trade_plan_path=plan,
                price_loader=lambda: {"510300": 4.6},
                alerts_path=alerts_path,
                notifier=notifier,
                once=True,
            )
            second = monitor_loop(
                trade_plan_path=plan,
                price_loader=lambda: {"510300": 4.6},
                alerts_path=alerts_path,
                notifier=notifier,
                once=True,
            )

            self.assertEqual([alert.alert_type for alert in first], ["entry_triggered", "take_profit_triggered"])
            self.assertEqual(second, [])
            self.assertEqual(len(notifier.messages), 2)
            self.assertIn("入场触发", notifier.messages[0][0])

    def test_notify_test_command_uses_safe_message(self):
        config = load_config("configs/default.json")
        args = Namespace(notifier="console", title="测试通知", body="不涉及交易")

        result = _cmd_notify_test(config, args)

        self.assertEqual(result, {"notifier": "console", "sent": True})

    def test_notify_test_command_reports_send_failure(self):
        config = load_config("configs/default.json")
        args = Namespace(notifier="wechat", title="测试通知", body="不涉及交易")

        with patch("haitong_quant.cli.build_notifier") as build:
            notifier = types.SimpleNamespace(send=lambda title, body: (_ for _ in ()).throw(RuntimeError("network timeout")))
            build.return_value = notifier
            result = _cmd_notify_test(config, args)

        self.assertEqual(result["notifier"], "wechat")
        self.assertFalse(result["sent"])
        self.assertIn("network timeout", result["error"])

    def test_pipeline_writes_manifest_in_output_dir(self):
        config = load_config("configs/default.json")
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                mode="paper",
                output_dir=tmp,
                prices=None,
                news=None,
                raw_news=None,
                top_n=2,
                order_value=10000.0,
                min_score=45.0,
                config="configs/default.json",
                journal_db=str(Path(tmp) / "journal.db"),
                max_slippage_pct=0.02,
            )

            manifest = _cmd_pipeline(config, args)

            self.assertTrue(Path(manifest["trade_plan"]).exists())
            self.assertTrue((Path(tmp) / "manifest.json").exists())
            self.assertIn("paper", manifest)

    def test_optimization_heatmap_csv_writes_metric_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "heatmap.csv"
            write_optimization_heatmap_csv(
                output,
                [
                    OptimizationResult(
                        lookback_days=20,
                        top_n=2,
                        min_momentum=0.0,
                        avg_train_return=0.1,
                        avg_test_return=0.05,
                        avg_test_drawdown=-0.02,
                        avg_train_sharpe=1.5,
                        avg_test_sharpe=0.9,
                        overfit_ratio=1.6,
                        parameter_stability=0.8,
                        window_count=3,
                    )
                ],
            )

            content = output.read_text(encoding="utf-8")
            self.assertIn("avg_test_sharpe", content)
            self.assertIn("0.9", content)

    def test_logging_writes_decision_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                setup_logging(
                    log_path=Path(tmp) / "haitong.log",
                    decisions_path=Path(tmp) / "decisions.jsonl",
                    console=False,
                )
                engine = RiskEngine(
                    RuntimeRiskConfig(
                        allowed_symbols={"510300"},
                        max_single_order_value=100000,
                        max_daily_trade_value=100000,
                        max_symbol_weight=1.0,
                        trading_start=time(9, 30),
                        trading_end=time(14, 55),
                        max_intraday_drawdown_pct=0,
                        max_total_drawdown_pct=0,
                    )
                )
                account = AccountSnapshot(cash=100000, positions={}, as_of=datetime(2026, 1, 2, 10))
                engine.validate(
                    OrderIntent("510300", Side.BUY.value, 100, 4.0, "test"),
                    account,
                    {"510300": 4.0},
                    datetime(2026, 1, 2, 10),
                )

                decision_path = Path(tmp) / "decisions.jsonl"
                self.assertTrue(decision_path.exists())
                self.assertIn("510300", decision_path.read_text(encoding="utf-8"))
            finally:
                root = logging.getLogger()
                for handler in list(root.handlers):
                    root.removeHandler(handler)
                    handler.close()
                setattr(root, "_haitong_logging_configured", False)
