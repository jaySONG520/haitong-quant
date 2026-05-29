from datetime import date
import unittest

from haitong_quant.data import CSVDataSource
from haitong_quant.models import Side
from haitong_quant.strategy import EtfRotationStrategy


class StrategyTests(unittest.TestCase):
    def test_strategy_selects_top_momentum_without_future_date(self):
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

        signals = strategy.generate_signals(bars, as_of=date(2026, 1, 30))

        selected = [signal.symbol for signal in signals if signal.side == Side.BUY.value]
        self.assertEqual(selected, ["512100", "518880"])
        self.assertTrue(
            all(signal.generated_at.date() == date(2026, 1, 30) for signal in signals)
        )
