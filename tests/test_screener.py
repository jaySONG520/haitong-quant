import unittest

from pathlib import Path
import tempfile

from haitong_quant.analysis import (
    KeywordNewsScorer,
    KlineNewsScreener,
    NewsCSVSource,
    RawNewsCSVSource,
    write_news_scores,
)
from haitong_quant.data import CSVDataSource


class ScreenerTests(unittest.TestCase):
    def test_screener_ranks_candidates_with_news_and_fee_rules(self):
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        news = NewsCSVSource("data/sample_news_scores.csv").load()
        screener = KlineNewsScreener(
            min_trade_fee=5,
            stock_sell_tax_bps=5,
            default_order_value=10000,
            min_score=45,
        )

        results = screener.screen(bars, news_by_symbol=news, top_n=3)

        self.assertTrue(results)
        self.assertGreaterEqual(results[0].total_score, results[-1].total_score)
        self.assertGreater(results[0].trading_rules.stop_loss_pct, 0)
        self.assertGreater(results[0].trading_rules.take_profit_pct, 0)
        self.assertAlmostEqual(results[0].trading_rules.round_trip_fee_pct, 0.0015)
        self.assertTrue(results[0].advantages)

    def test_news_csv_clamps_scores(self):
        news = NewsCSVSource("data/sample_news_scores.csv").load()

        self.assertIn("512100", news)
        self.assertLessEqual(news["512100"].score, 1.0)
        self.assertGreaterEqual(news["512100"].score, -1.0)

    def test_raw_news_can_be_scored_and_exported(self):
        raw_items = RawNewsCSVSource("data/sample_raw_news.csv").load()
        scores = KeywordNewsScorer().score_items(raw_items)

        self.assertIn("512100", scores)
        self.assertGreater(scores["512100"].score, 0)
        self.assertIn("行业ETF", scores["512100"].summary)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "scores.csv"
            write_news_scores(output, scores)
            loaded = NewsCSVSource(output).load()

        self.assertEqual(set(loaded), set(scores))
