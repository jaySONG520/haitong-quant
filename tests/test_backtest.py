import unittest

from haitong_quant.backtest import BacktestEngine
from haitong_quant.data import CSVDataSource
from haitong_quant.strategy import EtfRotationStrategy


class BacktestTests(unittest.TestCase):
    def test_backtest_produces_orders_and_metrics(self):
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        strategy = EtfRotationStrategy(
            strategy_id="test",
            whitelist=("510300", "510500", "512100", "518880"),
            lookback_days=10,
            top_n=2,
            min_momentum=-1.0,
        )
        engine = BacktestEngine(strategy, starting_cash=100000, rebalance_days=5)

        result = engine.run(bars)

        self.assertTrue(result.orders)
        self.assertGreater(result.metrics["final_equity"], 0)
        self.assertIn("max_drawdown", result.metrics)
