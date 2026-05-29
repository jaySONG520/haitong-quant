"""组合仓位风控规则测试。"""

import unittest
from datetime import date, datetime

from haitong_quant.models import AccountSnapshot, Position
from haitong_quant.risk.portfolio_rules import PortfolioRiskChecker, PortfolioRiskConfig


class PortfolioRulesTests(unittest.TestCase):
    def _make_account(self, cash=50000, positions=None):
        return AccountSnapshot(
            cash=cash,
            positions=positions or {},
            as_of=datetime(2025, 6, 1, 15, 0),
        )

    def test_total_exposure_within_limit(self):
        """总仓位未超限时通过。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_total_exposure=0.8))
        account = self._make_account(cash=60000, positions={
            "510300": Position("510300", 1000, 4.0),
        })
        prices = {"510300": 4.0}
        passed, reason = checker.check_total_exposure(account, prices)
        self.assertTrue(passed)

    def test_total_exposure_exceeds_limit(self):
        """总仓位超限时拒绝。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_total_exposure=0.3))
        account = self._make_account(cash=10000, positions={
            "510300": Position("510300", 10000, 4.0),
        })
        prices = {"510300": 4.0}
        passed, reason = checker.check_total_exposure(account, prices)
        self.assertFalse(passed)
        self.assertIn("超过上限", reason)

    def test_daily_entries_limit(self):
        """单日开仓数超限时拒绝。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_daily_entries=2))
        today = date(2025, 6, 1)
        checker.record_entry(today)
        checker.record_entry(today)

        passed, reason = checker.check_daily_entries(today)
        self.assertFalse(passed)
        self.assertIn("达到上限", reason)

    def test_industry_limit(self):
        """单行业权重超限时拒绝。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_industry_weight=0.3))
        account = self._make_account(cash=50000, positions={
            "510300": Position("510300", 5000, 4.0),
        })
        prices = {"510300": 4.0}
        industry_map = {"510300": "金融", "600036": "金融"}

        passed, reason = checker.check_industry_limit(
            "600036", industry_map, account, prices, order_value=20000,
        )
        self.assertFalse(passed)
        self.assertIn("金融", reason)

    def test_correlation_check(self):
        """高相关性标的被拒绝。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_correlation=0.85))
        corr = {("510300", "510500"): 0.92}

        passed, reason = checker.check_correlation("510500", ["510300"], corr)
        self.assertFalse(passed)
        self.assertIn("相关性", reason)

    def test_full_check_passes(self):
        """全部检查通过的场景。"""
        checker = PortfolioRiskChecker()
        account = self._make_account(cash=80000, positions={
            "510300": Position("510300", 500, 4.0),
        })
        prices = {"510300": 4.0}
        passed, reason = checker.full_check(
            "510500", account, prices, order_value=5000,
        )
        self.assertTrue(passed)

    def test_single_symbol_weight_exceeded(self):
        """单标的权重超限时拒绝。"""
        checker = PortfolioRiskChecker(PortfolioRiskConfig(max_single_symbol_weight=0.2))
        account = self._make_account(cash=50000, positions={
            "510300": Position("510300", 2000, 4.0),
        })
        prices = {"510300": 4.0}
        passed, reason = checker.check_single_symbol_weight(
            "510300", account, prices, order_value=10000,
        )
        self.assertFalse(passed)
