from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haitong_quant.ops.dashboard import build_dashboard_summary, render_static_dashboard


class DashboardTests(unittest.TestCase):
    def test_static_dashboard_renders_chinese_interactive_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            trade_plan = Path(tmp) / "trade_plan.json"
            daily_report = Path(tmp) / "daily_report.md"
            trade_plan.write_text(
                json.dumps(
                    {
                        "research_only": True,
                        "generated_at": "2026-05-30T15:15:00",
                        "items": [
                            {
                                "symbol": "510300",
                                "status": "entry_candidate",
                                "signal_close": 4.0,
                                "total_score": 78.5,
                                "short_term_bias": "rule_constructive",
                                "medium_term_bias": "rule_constructive",
                                "entry_price": 4.04,
                                "pre_entry_invalidation_price": 3.8,
                                "stop_loss_price_if_entry_fills": 3.86,
                                "take_profit_price_if_entry_fills": 4.36,
                                "trailing_stop_pct": 0.03,
                                "assumed_order_value": 10000,
                                "estimated_round_trip_fee": 15,
                                "advantages": ["5-day momentum is positive"],
                                "risks": ["RSI is high; chasing risk is elevated"],
                                "news_score": 0.1,
                                "news_summary": "Sample positive broad sector liquidity note",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            daily_report.write_text(
                "# 研究日报\n\n| 代码 | 状态 |\n| --- | --- |\n| 510300 | entry_candidate |\n\nRSI is high; chasing risk is elevated",
                encoding="utf-8",
            )

            html = render_static_dashboard(
                trade_plan_path=trade_plan,
                daily_report_path=daily_report,
            )

            self.assertIn("海通量化运营看板", html)
            self.assertIn("候选看板", html)
            self.assertIn("触发价格", html)
            self.assertIn("风险复盘", html)
            self.assertIn("日报原文", html)
            self.assertIn("搜索代码或名称", html)
            self.assertIn("刷新", html)
            self.assertIn("自动刷新", html)
            self.assertIn("轮询间隔", html)
            self.assertIn("最后刷新", html)
            self.assertIn("下次刷新", html)
            self.assertIn("行情来源", html)
            self.assertIn("价格趋势", html)
            self.assertIn("计划触发价", html)
            self.assertIn("价格执行计划", html)
            self.assertIn("计划买入价", html)
            self.assertIn("止盈卖出价", html)
            self.assertIn("止损离场价", html)
            self.assertIn("可入场候选", html)
            self.assertIn("RSI偏高，追价风险抬升", html)
            self.assertNotIn("Haitong Quant Dashboard", html)
            self.assertNotIn("Trade Plan", html)
            self.assertNotIn("RSI is high; chasing risk is elevated", html)

    def test_summary_handles_missing_files_with_chinese_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = build_dashboard_summary(
                trade_plan_path=Path(tmp) / "missing_plan.json",
                daily_report_path=Path(tmp) / "missing_report.md",
                dashboard_poll_interval_seconds=12,
                dashboard_min_poll_interval_seconds=5,
            )

            self.assertEqual(summary["metrics"]["candidate_count"], 0)
            self.assertEqual(summary["daily_report"]["content"], "")
            self.assertEqual(summary["polling"]["default_interval_seconds"], 12)
            self.assertEqual(summary["polling"]["min_interval_seconds"], 5)
            self.assertIn("refreshed_at", summary)
            self.assertIn("未找到交易计划文件", " ".join(summary["warnings"]))
            self.assertIn("未找到研究日报文件", " ".join(summary["warnings"]))

    def test_dashboard_summary_api_returns_normalized_payload(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask is not installed")

        from haitong_quant.ops.web_dashboard import create_flask_app

        with tempfile.TemporaryDirectory() as tmp:
            trade_plan = Path(tmp) / "trade_plan.json"
            daily_report = Path(tmp) / "daily_report.md"
            trade_plan.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-05-30T15:15:00",
                        "items": [
                            {
                                "symbol": "510500",
                                "status": "watch_only",
                                "total_score": 62.0,
                                "entry_price": 7.1,
                                "stop_loss_price_if_entry_fills": 6.8,
                                "take_profit_price_if_entry_fills": 7.6,
                                "advantages": [],
                                "risks": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            daily_report.write_text("# 研究日报\n\n暂无复盘数据。", encoding="utf-8")
            app = create_flask_app(
                trade_plan_path=trade_plan,
                daily_report_path=daily_report,
                dashboard_poll_interval_seconds=18,
                dashboard_min_poll_interval_seconds=6,
            )

            client = app.test_client()
            response = client.get("/api/dashboard-summary")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()

            self.assertEqual(payload["metrics"]["candidate_count"], 1)
            self.assertEqual(payload["candidates"][0]["name"], "中证500ETF南方")
            self.assertEqual(payload["candidates"][0]["index_name"], "中证500")
            self.assertEqual(payload["candidates"][0]["plan_signal_close"], 0.0)
            self.assertEqual(payload["candidates"][0]["date"], "2026-05-30")
            self.assertEqual(payload["candidates"][0]["status_label"], "观察")
            self.assertEqual(payload["candidates"][0]["entry_price"], 7.1)
            self.assertEqual(payload["candidates"][0]["stop_loss_price"], 6.8)
            self.assertEqual(payload["candidates"][0]["take_profit_price"], 7.6)
            self.assertEqual(payload["polling"]["default_interval_seconds"], 18)
            self.assertEqual(payload["polling"]["min_interval_seconds"], 6)
            self.assertIn("研究日报", payload["daily_report"]["content"])

    def test_save_daily_report_accepts_markdown_field(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask is not installed")

        from haitong_quant.ops.web_dashboard import create_flask_app

        with tempfile.TemporaryDirectory() as tmp:
            trade_plan = Path(tmp) / "trade_plan.json"
            daily_report = Path(tmp) / "daily_report.md"
            trade_plan.write_text(json.dumps({"items": []}), encoding="utf-8")
            app = create_flask_app(trade_plan_path=trade_plan, daily_report_path=daily_report)

            client = app.test_client()
            response = client.post("/api/save-daily-report", json={"markdown": "# 新日报\n\n已保存"})

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["success"])
            self.assertIn("新日报", daily_report.read_text(encoding="utf-8-sig"))

    def test_realtime_prices_api_returns_quote_metadata(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask is not installed")

        from haitong_quant.ops.web_dashboard import create_flask_app

        class FakeTencentResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return 'v_s_sh510500="1~中证500ETF~510500~7.123~0.07~1.23";'.encode("gbk")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_flask_app(
                trade_plan_path=Path(tmp) / "trade_plan.json",
                daily_report_path=Path(tmp) / "daily_report.md",
            )
            client = app.test_client()
            with patch("urllib.request.urlopen", return_value=FakeTencentResponse()):
                response = client.get("/api/realtime-prices?symbols=510500:7.100")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["510500"]["price"], 7.123)
            self.assertEqual(payload["510500"]["name"], "中证500ETF")
            self.assertEqual(payload["510500"]["source"], "live")
            self.assertEqual(payload["__meta__"]["source"], "live")
            self.assertEqual(payload["__meta__"]["source_label"], "实时行情")
            self.assertIn("refreshed_at_label", payload["__meta__"])

    def test_security_trend_api_resolves_name_and_returns_klines(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask is not installed")

        from haitong_quant.ops.web_dashboard import create_flask_app

        class FakeResponse:
            def __init__(self, text: str, encoding: str = "utf-8"):
                self.text = text
                self.encoding = encoding

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self.text.encode(self.encoding)

        def fake_urlopen(req, timeout=0):
            url = getattr(req, "full_url", str(req))
            if "qt.gtimg.cn" in url:
                return FakeResponse('v_s_sh510500="1~中证500ETF南方~510500~8.424~-0.019~-0.23~1035812~87359~~365.18~ETF~";', "gbk")
            return FakeResponse(
                json.dumps(
                    {
                        "data": {
                            "klines": [
                                "2026-05-01,8.000,8.100,8.120,7.980,1,1,1,1,1,1",
                                "2026-05-02,8.100,8.200,8.220,8.080,1,1,1,1,1,1",
                                "2026-05-03,8.200,8.300,8.320,8.180,1,1,1,1,1,1",
                                "2026-05-04,8.300,8.424,8.450,8.250,1,1,1,1,1,1",
                            ]
                        }
                    }
                )
            )

        with tempfile.TemporaryDirectory() as tmp:
            app = create_flask_app(
                trade_plan_path=Path(tmp) / "trade_plan.json",
                daily_report_path=Path(tmp) / "daily_report.md",
            )
            client = app.test_client()
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                response = client.get("/api/security-trend?query=中证500ETF南方")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["symbol"], "510500")
            self.assertEqual(payload["name"], "中证500ETF南方")
            self.assertEqual(payload["price"], 8.424)
            self.assertEqual(len(payload["klines"]), 4)
            self.assertIn("trend_label", payload["trend"])


if __name__ == "__main__":
    unittest.main()
