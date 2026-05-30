from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
            )

            self.assertEqual(summary["metrics"]["candidate_count"], 0)
            self.assertEqual(summary["daily_report"]["content"], "")
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
            )

            client = app.test_client()
            response = client.get("/api/dashboard-summary")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()

            self.assertEqual(payload["metrics"]["candidate_count"], 1)
            self.assertEqual(payload["candidates"][0]["status_label"], "观察")
            self.assertIn("研究日报", payload["daily_report"]["content"])


if __name__ == "__main__":
    unittest.main()
