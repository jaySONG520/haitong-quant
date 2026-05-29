"""组合仓位风控规则。

在单只候选规则之上，新增总仓位上限、单行业上限、
单日最大开仓数、相关性过滤等组合级风控检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from haitong_quant.models import AccountSnapshot, Position


@dataclass(frozen=True)
class PortfolioRiskConfig:
    """组合仓位风控参数。"""
    max_total_exposure: float = 0.8          # 总仓位上限（占净值比例）
    max_industry_weight: float = 0.3         # 单行业权重上限
    max_daily_entries: int = 3               # 单日最大开仓数
    max_correlation: float = 0.85            # 相关性上限（高于此值拒绝）
    max_single_symbol_weight: float = 0.25   # 单标的权重上限


class PortfolioRiskChecker:
    """组合级风控检查器。"""

    def __init__(self, config: PortfolioRiskConfig | None = None) -> None:
        self.config = config or PortfolioRiskConfig()
        self._daily_entries: dict[str, int] = {}

    def check_total_exposure(
        self,
        account: AccountSnapshot,
        prices: dict[str, float],
    ) -> tuple[bool, str]:
        """检查总仓位是否超过上限。"""
        equity = _total_equity(account, prices)
        if equity <= 0:
            return False, "净值为零或负值"
        positions_value = sum(
            pos.quantity * prices.get(sym, pos.cost_basis)
            for sym, pos in account.positions.items()
        )
        exposure = positions_value / equity
        if exposure > self.config.max_total_exposure:
            return False, f"总仓位 {exposure:.1%} 超过上限 {self.config.max_total_exposure:.1%}"
        return True, "ok"

    def check_industry_limit(
        self,
        symbol: str,
        industry_map: dict[str, str],
        account: AccountSnapshot,
        prices: dict[str, float],
        order_value: float,
    ) -> tuple[bool, str]:
        """检查单行业权重是否超过上限。"""
        equity = _total_equity(account, prices)
        if equity <= 0:
            return False, "净值为零或负值"
        target_industry = industry_map.get(symbol, "unknown")
        industry_value = order_value  # 本笔订单
        for sym, pos in account.positions.items():
            if industry_map.get(sym, "unknown") == target_industry:
                industry_value += pos.quantity * prices.get(sym, pos.cost_basis)
        weight = industry_value / equity
        if weight > self.config.max_industry_weight:
            return False, f"行业 {target_industry} 权重 {weight:.1%} 超过上限 {self.config.max_industry_weight:.1%}"
        return True, "ok"

    def check_daily_entries(self, today: date | None = None) -> tuple[bool, str]:
        """检查单日开仓数是否超过上限。"""
        day_key = (today or date.today()).isoformat()
        count = self._daily_entries.get(day_key, 0)
        if count >= self.config.max_daily_entries:
            return False, f"今日已开仓 {count} 次，达到上限 {self.config.max_daily_entries}"
        return True, "ok"

    def record_entry(self, today: date | None = None) -> None:
        """记录一次开仓。"""
        day_key = (today or date.today()).isoformat()
        self._daily_entries[day_key] = self._daily_entries.get(day_key, 0) + 1

    def check_correlation(
        self,
        symbol: str,
        existing_symbols: list[str],
        correlation_matrix: dict[tuple[str, str], float] | None = None,
    ) -> tuple[bool, str]:
        """检查与现有持仓的相关性。"""
        if not correlation_matrix or not existing_symbols:
            return True, "ok"
        for existing in existing_symbols:
            key = (min(symbol, existing), max(symbol, existing))
            corr = correlation_matrix.get(key, 0.0)
            if abs(corr) > self.config.max_correlation:
                return False, f"{symbol} 与 {existing} 相关性 {corr:.2f} 超过上限 {self.config.max_correlation:.2f}"
        return True, "ok"

    def check_single_symbol_weight(
        self,
        symbol: str,
        account: AccountSnapshot,
        prices: dict[str, float],
        order_value: float,
    ) -> tuple[bool, str]:
        """检查单标的权重是否超过上限。"""
        equity = _total_equity(account, prices)
        if equity <= 0:
            return False, "净值为零或负值"
        current_pos = account.positions.get(symbol)
        current_value = current_pos.quantity * prices.get(symbol, current_pos.cost_basis) if current_pos else 0.0
        future_weight = (current_value + order_value) / equity
        if future_weight > self.config.max_single_symbol_weight:
            return False, f"{symbol} 权重 {future_weight:.1%} 超过上限 {self.config.max_single_symbol_weight:.1%}"
        return True, "ok"

    def full_check(
        self,
        symbol: str,
        account: AccountSnapshot,
        prices: dict[str, float],
        order_value: float,
        industry_map: dict[str, str] | None = None,
        correlation_matrix: dict[tuple[str, str], float] | None = None,
        today: date | None = None,
    ) -> tuple[bool, str]:
        """执行全部组合级风控检查。返回第一个失败的原因。"""
        checks = [
            self.check_total_exposure(account, prices),
            self.check_daily_entries(today),
            self.check_single_symbol_weight(symbol, account, prices, order_value),
        ]
        if industry_map:
            checks.append(
                self.check_industry_limit(symbol, industry_map, account, prices, order_value)
            )
        if correlation_matrix:
            existing = list(account.positions.keys())
            checks.append(self.check_correlation(symbol, existing, correlation_matrix))

        for passed, reason in checks:
            if not passed:
                return False, reason
        return True, "all_checks_passed"


def _total_equity(account: AccountSnapshot, prices: dict[str, float]) -> float:
    positions_value = sum(
        pos.quantity * prices.get(sym, pos.cost_basis)
        for sym, pos in account.positions.items()
    )
    return account.cash + positions_value
