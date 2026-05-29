"""自动日报测试。"""

import unittest

from haitong_quant.analysis import (
    KlineNewsScreener,
    NewsCSVSource,
    build_trade_plan,
    generate_daily_report,
)
from haitong_quant.analysis.journal import JournalSummary
from haitong_quant.data import CSVDataSource


class DailyReportTests(unittest.TestCase):
    def test_daily_report_generates_complete_markdown(self):
        """日报包含所有必要章节。"""
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        news = NewsCSVSource("data/sample_news_scores.csv").load()
        screener = KlineNewsScreener(min_score=45)
        candidates = screener.screen(bars, news_by_symbol=news, top_n=3)
        plan = build_trade_plan(candidates, order_value=10000)

        content = generate_daily_report(
            candidates=candidates,
            trade_plan=plan,
            rejected_symbols={"600000": "成交额不足", "000001": "涨停附近"},
            config_path="configs/default.json",
        )

        # 验证六个章节都存在
        self.assertIn("研究日报", content)
        self.assertIn("一、候选名单", content)
        self.assertIn("二、明日触发价一览", content)
        self.assertIn("三、被剔除标的及原因", content)
        self.assertIn("四、风险提示汇总", content)
        self.assertIn("五、复盘统计", content)
        self.assertIn("六、持仓规则提醒", content)
        # 验证剔除原因
        self.assertIn("600000", content)
        self.assertIn("成交额不足", content)

    def test_daily_report_with_journal_summary(self):
        """日报包含复盘统计数据。"""
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        candidates = KlineNewsScreener(min_score=45).screen(bars, top_n=1)
        plan = build_trade_plan(candidates, order_value=10000)

        summary = JournalSummary(
            total_signals=10, triggered=8, filled=6, exited=5,
            wins=3, losses=2, win_rate=0.6, avg_pnl=0.05,
            avg_win=0.12, avg_loss=-0.06, profit_factor=2.0,
            max_consecutive_losses=1, total_pnl=0.25,
        )
        content = generate_daily_report(
            candidates=candidates,
            trade_plan=plan,
            journal_summary=summary,
        )

        self.assertIn("胜率: 60.0%", content)
        self.assertIn("盈亏比: 2.00", content)

    def test_daily_report_empty_candidates(self):
        """无候选时日报仍能正常生成。"""
        content = generate_daily_report(
            candidates=[],
            trade_plan=[],
        )

        self.assertIn("研究日报", content)
        self.assertIn("无候选标的通过筛选阈值", content)
