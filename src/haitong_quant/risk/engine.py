from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

from haitong_quant.models import AccountSnapshot, OrderIntent, RiskDecision, Side
from haitong_quant.risk.portfolio_rules import PortfolioRiskChecker

LOGGER = logging.getLogger(__name__)

@dataclass
class RuntimeRiskConfig:
    allowed_symbols: set[str]
    live_allowed_symbols: set[str] = field(default_factory=set)
    max_single_order_value: float = 0.0
    max_daily_trade_value: float = 0.0
    max_symbol_weight: float = 1.0
    trading_start: time = time(hour=9, minute=30)
    trading_end: time = time(hour=14, minute=55)
    manual_kill_switch_path: Path | None = None
    max_consecutive_rejections: int = 3
    account_mode: str = "mock"
    enable_live_orders: bool = False
    portfolio_checker: PortfolioRiskChecker | None = None
    industry_map: dict[str, str] = field(default_factory=dict)
    correlation_matrix: dict[tuple[str, str], float] = field(default_factory=dict)
    max_intraday_drawdown_pct: float = 0.03
    max_total_drawdown_pct: float = 0.08


class RiskEngine:
    def __init__(self, config: RuntimeRiskConfig) -> None:
        self.config = config
        self._daily_notional: dict[str, float] = {}
        self._seen_order_keys: set[str] = set()
        self._consecutive_rejections = 0
        self._daily_peak_equity: dict[str, float] = {}
        self._lifetime_peak_equity: float = 0.0

    def validate(
        self,
        order: OrderIntent,
        account: AccountSnapshot,
        last_prices: dict[str, float],
        now: datetime | None = None,
    ) -> RiskDecision:
        effective_now = now or datetime.now()
        decision = self._validate(order, account, last_prices, effective_now)
        if decision.approved:
            self._consecutive_rejections = 0
            self._record(order, effective_now)
        else:
            self._consecutive_rejections += 1
        LOGGER.info(
            "risk_decision",
            extra={
                "symbol": order.symbol,
                "side": order.side,
                "approved": decision.approved,
                "reason": decision.reason,
            },
        )
        return decision

    def _validate(
        self,
        order: OrderIntent,
        account: AccountSnapshot,
        last_prices: dict[str, float],
        now: datetime,
    ) -> RiskDecision:
        if self._kill_switch_active():
            return RiskDecision(False, "manual_kill_switch_active")
        if self._consecutive_rejections >= self.config.max_consecutive_rejections:
            return RiskDecision(False, "max_consecutive_rejections_reached")
        if order.symbol not in self.config.allowed_symbols:
            return RiskDecision(False, "symbol_not_in_allowed_whitelist")
        if self.config.account_mode == "live":
            if not self.config.enable_live_orders:
                return RiskDecision(False, "live_orders_disabled")
            if not self.config.live_allowed_symbols:
                return RiskDecision(False, "empty_live_allowed_symbols")
            if order.symbol not in self.config.live_allowed_symbols:
                return RiskDecision(False, "symbol_not_in_live_whitelist")
        if not (self.config.trading_start <= now.time() <= self.config.trading_end):
            return RiskDecision(False, "outside_trading_window")
        if order.quantity <= 0:
            return RiskDecision(False, "non_positive_quantity")
        if order.limit_price <= 0:
            return RiskDecision(False, "non_positive_limit_price")
        if order.side not in {Side.BUY.value, Side.SELL.value}:
            return RiskDecision(False, "unsupported_order_side")
        if order.idempotency_key in self._seen_order_keys:
            return RiskDecision(False, "duplicate_order_intent")
        if order.side == Side.BUY.value:
            drawdown_decision = self._check_drawdown_breaker(account, last_prices, now)
            if drawdown_decision is not None:
                return drawdown_decision
        if order.notional > self.config.max_single_order_value:
            return RiskDecision(False, "single_order_value_limit_exceeded")
        day_key = now.date().isoformat()
        used_today = self._daily_notional.get(day_key, 0.0)
        if used_today + order.notional > self.config.max_daily_trade_value:
            return RiskDecision(False, "daily_trade_value_limit_exceeded")
        if order.side == Side.SELL.value:
            held = account.positions.get(order.symbol)
            if held is None or held.quantity < order.quantity:
                return RiskDecision(False, "sell_quantity_exceeds_position")
        if order.side == Side.BUY.value:
            if order.notional > account.cash:
                return RiskDecision(False, "insufficient_cash")
            price = last_prices.get(order.symbol, order.limit_price)
            equity = _total_equity(account, last_prices)
            current_quantity = account.positions.get(order.symbol)
            current_value = (current_quantity.quantity if current_quantity else 0) * price
            future_weight = (current_value + order.notional) / equity if equity > 0 else 1.0
            if future_weight > self.config.max_symbol_weight:
                return RiskDecision(False, "max_symbol_weight_exceeded")
            if self.config.portfolio_checker is not None:
                passed, reason = self.config.portfolio_checker.full_check(
                    order.symbol,
                    account,
                    last_prices,
                    order.notional,
                    industry_map=self.config.industry_map or None,
                    correlation_matrix=self.config.correlation_matrix or None,
                    today=now.date(),
                )
                if not passed:
                    return RiskDecision(False, f"portfolio_risk:{reason}")
        return RiskDecision(True, "approved", adjusted_order=order)

    def _record(self, order: OrderIntent, now: datetime) -> None:
        self._seen_order_keys.add(order.idempotency_key)
        day_key = now.date().isoformat()
        self._daily_notional[day_key] = self._daily_notional.get(day_key, 0.0) + order.notional
        if order.side == Side.BUY.value and self.config.portfolio_checker is not None:
            self.config.portfolio_checker.record_entry(now.date())

    def _check_drawdown_breaker(
        self,
        account: AccountSnapshot,
        last_prices: dict[str, float],
        now: datetime,
    ) -> RiskDecision | None:
        equity = _total_equity(account, last_prices)
        if equity <= 0:
            return RiskDecision(False, "non_positive_equity")

        day_key = now.date().isoformat()
        daily_peak = max(self._daily_peak_equity.get(day_key, equity), equity)
        self._daily_peak_equity[day_key] = daily_peak
        self._lifetime_peak_equity = max(self._lifetime_peak_equity, equity)

        if (
            self.config.max_intraday_drawdown_pct > 0
            and daily_peak > 0
            and equity / daily_peak - 1.0 <= -self.config.max_intraday_drawdown_pct
        ):
            return RiskDecision(False, "intraday_drawdown_breaker_active")

        if (
            self.config.max_total_drawdown_pct > 0
            and self._lifetime_peak_equity > 0
            and equity / self._lifetime_peak_equity - 1.0 <= -self.config.max_total_drawdown_pct
        ):
            self._activate_kill_switch("total_drawdown_breaker_active")
            return RiskDecision(False, "total_drawdown_breaker_active")
        return None

    def _kill_switch_active(self) -> bool:
        path = self.config.manual_kill_switch_path
        if path is None or not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore").strip().lower()
        return text not in {"", "0", "off", "false"}

    def _activate_kill_switch(self, reason: str) -> None:
        path = self.config.manual_kill_switch_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(reason, encoding="utf-8")


def _total_equity(account: AccountSnapshot, last_prices: dict[str, float]) -> float:
    positions_value = 0.0
    for symbol, position in account.positions.items():
        positions_value += position.quantity * last_prices.get(symbol, position.cost_basis)
    return account.cash + positions_value
