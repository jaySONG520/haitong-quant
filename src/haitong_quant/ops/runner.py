from __future__ import annotations

from datetime import datetime, time
from math import floor
from pathlib import Path

from haitong_quant.config import QuantConfig
from haitong_quant.models import AccountSnapshot, Bar, OrderIntent, Position, Side, Signal
from haitong_quant.risk import (
    PortfolioRiskChecker,
    PortfolioRiskConfig,
    RiskEngine,
    RuntimeRiskConfig,
)


def latest_close_prices(bars_by_symbol: dict[str, list[Bar]]) -> dict[str, float]:
    return {
        symbol: sorted(bars, key=lambda item: item.date)[-1].close
        for symbol, bars in bars_by_symbol.items()
        if bars
    }


def build_order_intents(
    signals: list[Signal],
    account: AccountSnapshot,
    prices: dict[str, float],
    strategy_id: str,
    lot_size: int = 100,
    slippage_bps: float = 0.0,
) -> list[OrderIntent]:
    total_equity = _total_equity(account, prices)
    intents: list[OrderIntent] = []
    for signal in signals:
        if signal.side == Side.HOLD.value:
            continue
        price = prices.get(signal.symbol)
        if not price:
            continue
        position = account.positions.get(signal.symbol, Position(signal.symbol, 0))
        current_value = position.quantity * price
        target_value = total_equity * signal.target_weight
        delta_value = target_value - current_value
        if abs(delta_value) < price * lot_size:
            continue
        if delta_value > 0:
            quantity = floor(delta_value / price / lot_size) * lot_size
            if quantity <= 0:
                continue
            limit_price = price * (1 + slippage_bps / 10000.0)
            side = Side.BUY.value
        else:
            quantity = min(
                position.quantity,
                floor(abs(delta_value) / price / lot_size) * lot_size,
            )
            if quantity <= 0:
                continue
            limit_price = price * (1 - slippage_bps / 10000.0)
            side = Side.SELL.value
        intents.append(
            OrderIntent(
                symbol=signal.symbol,
                side=side,
                quantity=quantity,
                limit_price=round(limit_price, 4),
                strategy_id=strategy_id,
                risk_tags=("etf_rotation", "auto_generated"),
            )
        )
    return intents


def make_risk_engine(
    config: QuantConfig,
    *,
    industry_map: dict[str, str] | None = None,
    correlation_matrix: dict[tuple[str, str], float] | None = None,
) -> RiskEngine:
    risk = config.risk
    execution = config.execution
    portfolio = risk.portfolio
    return RiskEngine(
        RuntimeRiskConfig(
            allowed_symbols=set(risk.allowed_symbols),
            live_allowed_symbols=set(risk.live_allowed_symbols),
            max_single_order_value=risk.max_single_order_value,
            max_daily_trade_value=risk.max_daily_trade_value,
            max_symbol_weight=risk.max_symbol_weight,
            trading_start=_parse_hhmm(risk.trading_start),
            trading_end=_parse_hhmm(risk.trading_end),
            manual_kill_switch_path=Path(risk.manual_kill_switch_path),
            max_consecutive_rejections=risk.max_consecutive_rejections,
            account_mode=execution.account_mode,
            enable_live_orders=execution.enable_live_orders,
            portfolio_checker=PortfolioRiskChecker(
                PortfolioRiskConfig(
                    max_total_exposure=portfolio.max_total_exposure,
                    max_industry_weight=portfolio.max_industry_weight,
                    max_daily_entries=portfolio.max_daily_entries,
                    max_correlation=portfolio.max_correlation,
                    max_single_symbol_weight=portfolio.max_single_symbol_weight,
                )
            ),
            industry_map=industry_map or {},
            correlation_matrix=correlation_matrix or {},
            max_intraday_drawdown_pct=risk.max_intraday_drawdown_pct,
            max_total_drawdown_pct=risk.max_total_drawdown_pct,
        )
    )


def _parse_hhmm(value: str) -> time:
    parsed = datetime.strptime(value, "%H:%M")
    return time(hour=parsed.hour, minute=parsed.minute)


def _total_equity(account: AccountSnapshot, prices: dict[str, float]) -> float:
    return account.cash + sum(
        position.quantity * prices.get(symbol, position.cost_basis)
        for symbol, position in account.positions.items()
    )
