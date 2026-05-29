import unittest

from haitong_quant.analysis import KlineNewsScreener, NewsCSVSource, render_research_report
from haitong_quant.data import CSVDataSource


class ReportTests(unittest.TestCase):
    def test_report_renders_candidate_rules(self):
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        news = NewsCSVSource("data/sample_news_scores.csv").load()
        candidates = KlineNewsScreener(min_score=45).screen(bars, news_by_symbol=news, top_n=2)

        report = render_research_report(
            candidates,
            config_path="configs/default.json",
            news_path="data/sample_news_scores.csv",
            order_value=10000,
            min_score=45,
        )

        self.assertIn("# Quant Candidate Research Report", report)
        self.assertIn("Fee-aware rules", report)
        self.assertIn("512100", report)
        self.assertIn("Research output only", report)
