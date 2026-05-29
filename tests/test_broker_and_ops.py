from datetime import datetime
import unittest

from haitong_quant.broker import LiveTradingDisabled, MockBroker, QmtProxyBroker
from haitong_quant.models import AccountSnapshot, OrderIntent, Position, Side, Signal
from haitong_quant.ops import build_order_intents


class BrokerAndOpsTests(unittest.TestCase):
    def test_mock_broker_executes_buy_order(self):
        broker = MockBroker(starting_cash=10000)
        broker.connect()
        order = OrderIntent("510300", Side.BUY.value, 100, 4.0, "test")

        record = broker.submit_order(order)

        self.assertEqual(record.status, "filled")
        self.assertEqual(broker.get_positions()["510300"].quantity, 100)
        self.assertLess(broker.get_cash(), 10000)


    def test_build_order_intents_respects_lot_size(self):
        signals = [
            Signal("510300", Side.BUY.value, 0.5, "test", datetime(2026, 1, 30, 15, 1)),
            Signal("510500", Side.SELL.value, 0.0, "test", datetime(2026, 1, 30, 15, 1)),
        ]
        snapshot = AccountSnapshot(
            cash=10000,
            positions={"510500": Position("510500", 300, 6.0)},
            as_of=datetime(2026, 1, 30, 10, 0),
        )

        intents = build_order_intents(
            signals,
            snapshot,
            {"510300": 4.0, "510500": 6.0},
            strategy_id="test",
            lot_size=100,
        )

        self.assertEqual([intent.symbol for intent in intents], ["510300", "510500"])
        self.assertTrue(all(intent.quantity % 100 == 0 for intent in intents))


    def test_qmt_proxy_refuses_orders_until_enabled(self):
        broker = QmtProxyBroker("http://localhost:8000", "test-account", allow_orders=False)
        broker.session_id = "connected-for-unit-test"
        order = OrderIntent("510300", Side.BUY.value, 100, 4.0, "test")

        with self.assertRaises(LiveTradingDisabled):
            broker.submit_order(order)
