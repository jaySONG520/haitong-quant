"""模拟撮合引擎测试。"""

import unittest
from datetime import datetime

from haitong_quant.broker.paper_engine import PaperTradingEngine
from haitong_quant.models import OrderIntent, Position


class PaperEngineTests(unittest.TestCase):
    def test_normal_orders_pass(self):
        """正常订单全部通过。"""
        engine = PaperTradingEngine(starting_cash=100000)
        orders = [
            OrderIntent("510300", "buy", 100, 4.05, "test_strategy"),
            OrderIntent("510500", "buy", 100, 7.20, "test_strategy"),
        ]
        prices = {"510300": 4.00, "510500": 7.15}

        report = engine.validate(orders, prices)

        self.assertTrue(report.all_passed)
        self.assertEqual(len(report.results), 2)
        self.assertIn("全部通过", report.summary)

    def test_duplicate_order_rejected(self):
        """重复单被拒绝。"""
        engine = PaperTradingEngine(starting_cash=100000)
        order = OrderIntent("510300", "buy", 100, 4.05, "test_strategy")
        orders = [order, order]  # 同一笔提交两次
        prices = {"510300": 4.00}

        report = engine.validate(orders, prices)

        self.assertFalse(report.all_passed)
        rejected = [r for r in report.results if not r.passed]
        self.assertEqual(len(rejected), 1)
        self.assertIn("重复单", rejected[0].reason)

    def test_slippage_anomaly_rejected(self):
        """滑点异常被拒绝。"""
        engine = PaperTradingEngine(starting_cash=100000, max_slippage_pct=0.01)
        orders = [
            OrderIntent("510300", "buy", 100, 4.50, "test_strategy"),  # 远高于市价
        ]
        prices = {"510300": 4.00}

        report = engine.validate(orders, prices)

        self.assertFalse(report.all_passed)
        self.assertIn("滑点异常", report.results[0].reason)

    def test_sell_exceeds_position_rejected(self):
        """卖出超过持仓被拒绝。"""
        engine = PaperTradingEngine(starting_cash=100000)
        orders = [
            OrderIntent("510300", "sell", 1000, 4.00, "test_strategy"),
        ]
        prices = {"510300": 4.00}
        positions = {"510300": Position("510300", 100, 4.0)}

        report = engine.validate(orders, prices, existing_positions=positions)

        self.assertFalse(report.all_passed)
        self.assertIn("拒绝", report.results[0].reason)

    def test_insufficient_cash_rejected(self):
        """资金不足被拒绝。"""
        engine = PaperTradingEngine(starting_cash=100)  # 很少的资金
        orders = [
            OrderIntent("510300", "buy", 10000, 4.00, "test_strategy"),
        ]
        prices = {"510300": 4.00}

        report = engine.validate(orders, prices)

        self.assertFalse(report.all_passed)

    def test_sell_with_sufficient_position_passes(self):
        """持仓充足时卖出通过。"""
        engine = PaperTradingEngine(starting_cash=100000)
        orders = [
            OrderIntent("510300", "sell", 100, 4.00, "test_strategy"),
        ]
        prices = {"510300": 4.00}
        positions = {"510300": Position("510300", 500, 3.8)}

        report = engine.validate(orders, prices, existing_positions=positions)

        self.assertTrue(report.all_passed)
