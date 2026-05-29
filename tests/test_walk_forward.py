"""Walk-forward 回测测试。"""

import unittest

from haitong_quant.backtest.walk_forward import WalkForwardEngine
from haitong_quant.data import CSVDataSource
from haitong_quant.strategy import EtfRotationStrategy


class WalkForwardTests(unittest.TestCase):
    def test_walk_forward_produces_multiple_windows(self):
        """样本数据能产生至少一个窗口。"""
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        strategy = EtfRotationStrategy(
            strategy_id="test_wf",
            whitelist=("510300", "510500", "512100", "518880"),
            lookback_days=5,
            top_n=2,
            min_momentum=-0.02,
        )
        # 样本数据约30天，用小窗口测试
        engine = WalkForwardEngine(
            strategy=strategy,
            train_days=15,
            test_days=8,
            step_days=5,
        )
        result = engine.run(bars)

        self.assertGreater(len(result.windows), 0)
        self.assertIn("avg_test_return", result.aggregate_metrics)
        self.assertIn("parameter_stability", result.aggregate_metrics)
        self.assertEqual(
            result.aggregate_metrics["window_count"],
            float(len(result.windows)),
        )

    def test_walk_forward_insufficient_data_raises(self):
        """数据不足时应抛异常。"""
        bars = CSVDataSource("data/sample_prices.csv").load_bars(
            ["510300", "510500", "512100", "518880"]
        )
        strategy = EtfRotationStrategy(
            strategy_id="test_wf",
            whitelist=("510300", "510500", "512100", "518880"),
            lookback_days=5,
            top_n=2,
        )
        engine = WalkForwardEngine(
            strategy=strategy,
            train_days=500,  # 远超样本数据
            test_days=200,
        )
        with self.assertRaises(ValueError):
            engine.run(bars)
