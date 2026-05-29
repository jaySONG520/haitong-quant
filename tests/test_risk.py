from datetime import datetime, time
from pathlib import Path
import unittest

from haitong_quant.models import AccountSnapshot, OrderIntent, Position, Side
from haitong_quant.risk import RiskEngine, RuntimeRiskConfig


def make_engine(**overrides):
    config = RuntimeRiskConfig(
        allowed_symbols={"510300"},
        live_allowed_symbols=set(),
        max_single_order_value=10000,
        max_daily_trade_value=20000,
        max_symbol_weight=0.7,
        trading_start=time(9, 30),
        trading_end=time(14, 55),
        manual_kill_switch_path=None,
        account_mode="mock",
        enable_live_orders=False,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return RiskEngine(config)


def account(cash=20000):
    return AccountSnapshot(
        cash=cash,
        positions={"510300": Position("510300", 100, 4.0)},
        as_of=datetime(2026, 1, 30, 10, 0),
    )


class RiskTests(unittest.TestCase):
    def test_rejects_symbol_outside_whitelist(self):
        engine = make_engine()
        order = OrderIntent("510500", Side.BUY.value, 100, 6.0, "test")

        decision = engine.validate(
            order, account(), {"510300": 4.0}, datetime(2026, 1, 30, 10, 0)
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "symbol_not_in_allowed_whitelist")


    def test_rejects_duplicate_order(self):
        engine = make_engine()
        order = OrderIntent("510300", Side.BUY.value, 100, 4.0, "test")
        now = datetime(2026, 1, 30, 10, 0)

        self.assertTrue(engine.validate(order, account(), {"510300": 4.0}, now).approved)
        duplicate = engine.validate(order, account(), {"510300": 4.0}, now)

        self.assertFalse(duplicate.approved)
        self.assertEqual(duplicate.reason, "duplicate_order_intent")


    def test_live_mode_requires_explicit_live_whitelist(self):
        engine = make_engine(account_mode="live", enable_live_orders=True)
        order = OrderIntent("510300", Side.BUY.value, 100, 4.0, "test")

        decision = engine.validate(
            order, account(), {"510300": 4.0}, datetime(2026, 1, 30, 10, 0)
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "empty_live_allowed_symbols")


    def test_kill_switch_blocks_orders(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            kill = Path(tmp) / "KILL_SWITCH"
            kill.write_text("on", encoding="utf-8")
            engine = make_engine(manual_kill_switch_path=kill)
            order = OrderIntent("510300", Side.BUY.value, 100, 4.0, "test")

            decision = engine.validate(
                order, account(), {"510300": 4.0}, datetime(2026, 1, 30, 10, 0)
            )

            self.assertFalse(decision.approved)
            self.assertEqual(decision.reason, "manual_kill_switch_active")
