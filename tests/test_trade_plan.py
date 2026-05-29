import json
import tempfile
import unittest
from pathlib import Path

from haitong_quant.analysis import (
    KlineNewsScreener,
    NewsCSVSource,
    build_trade_plan,
    write_trade_plan_csv,
    write_trade_plan_json,
)
from haitong_quant.data import CSVDataSource


class TradePlanTests(unittest.TestCase):
    def test_trade_plan_has_prices_and_fee_estimates(self):
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        news = NewsCSVSource("data/sample_news_scores.csv").load()
        candidates = KlineNewsScreener(min_score=45).screen(bars, news_by_symbol=news, top_n=2)

        plan = build_trade_plan(candidates, order_value=10000)

        self.assertTrue(plan)
        self.assertGreater(plan[0].entry_price, plan[0].signal_close)
        self.assertLess(plan[0].stop_loss_price_if_entry_fills, plan[0].entry_price)
        self.assertGreater(plan[0].take_profit_price_if_entry_fills, plan[0].entry_price)
        self.assertEqual(plan[0].estimated_round_trip_fee, 15.0)

    def test_trade_plan_writes_json_and_csv(self):
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        candidates = KlineNewsScreener(min_score=45).screen(bars, top_n=1)
        plan = build_trade_plan(candidates, order_value=10000)

        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "plan.json"
            csv_path = Path(tmp) / "plan.csv"
            write_trade_plan_json(
                json_path,
                plan,
                config_path="configs/default.json",
                news_path="",
                min_score=45,
            )
            write_trade_plan_csv(csv_path, plan)
            payload = json.loads(json_path.read_text(encoding="utf-8-sig"))

            self.assertTrue(csv_path.exists())
            self.assertTrue(payload["research_only"])
            self.assertEqual(payload["items"][0]["symbol"], plan[0].symbol)
