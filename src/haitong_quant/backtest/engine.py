from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor
from statistics import mean, pstdev

from haitong_quant.models import Bar, OrderIntent, Position, Side
from haitong_quant.strategy import EtfRotationStrategy


@dataclass(frozen=True)
class EquityPoint:
    date: date
    equity: float
    cash: float
    positions_value: float


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: list[EquityPoint]
    orders: list[OrderIntent]
    metrics: dict[str, float]


class BacktestEngine:
    def __init__(
        self,
        strategy: EtfRotationStrategy,
        starting_cash: float = 100000.0,
        commission_bps: float = 2.0,
        slippage_bps: float = 5.0,
        rebalance_days: int = 5,
        lot_size: int = 100,
    ) -> None:
        self.strategy = strategy
        self.starting_cash = starting_cash
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.rebalance_days = rebalance_days
        self.lot_size = lot_size

    def run(self, bars_by_symbol: dict[str, list[Bar]]) -> BacktestResult:
        dates = _common_dates(bars_by_symbol, self.strategy.whitelist)
        if len(dates) <= self.strategy.lookback_days + 1:
            raise ValueError("Not enough common dates for backtest")

        cash = self.starting_cash
        positions: dict[str, Position] = {}
        orders: list[OrderIntent] = []
        equity_curve: list[EquityPoint] = []

        for index in range(1, len(dates)):
            trade_date = dates[index]
            signal_date = dates[index - 1]
            prices = _close_prices_on(bars_by_symbol, trade_date)
            if (index - self.strategy.lookback_days) >= 1 and (
                (index - self.strategy.lookback_days) % self.rebalance_days == 0
            ):
                signals = self.strategy.generate_signals(bars_by_symbol, as_of=signal_date)
                equity = _portfolio_value(cash, positions, prices)
                target_by_symbol = {
                    signal.symbol: signal.target_weight
                    for signal in signals
                    if signal.side != Side.HOLD.value
                }
                for symbol, target_weight in target_by_symbol.items():
                    price = prices[symbol]
                    current_qty = positions.get(symbol, Position(symbol, 0)).quantity
                    current_value = current_qty * price
                    target_value = equity * target_weight
                    delta_value = target_value - current_value
                    if abs(delta_value) < price * self.lot_size:
                        continue
                    if delta_value > 0:
                        qty = floor(delta_value / price / self.lot_size) * self.lot_size
                        fill_price = price * (1 + self.slippage_bps / 10000.0)
                        notional = qty * fill_price
                        fee = notional * self.commission_bps / 10000.0
                        if qty > 0 and notional + fee <= cash:
                            cash -= notional + fee
                            old = positions.get(symbol, Position(symbol, 0, 0.0))
                            new_qty = old.quantity + qty
                            new_cost = (
                                old.quantity * old.cost_basis + qty * fill_price
                            ) / new_qty
                            positions[symbol] = Position(symbol, new_qty, new_cost)
                            orders.append(
                                OrderIntent(symbol, Side.BUY.value, qty, fill_price, self.strategy.strategy_id)
                            )
                    elif delta_value < 0 and current_qty > 0:
                        qty = min(
                            current_qty,
                            floor(abs(delta_value) / price / self.lot_size) * self.lot_size,
                        )
                        fill_price = price * (1 - self.slippage_bps / 10000.0)
                        notional = qty * fill_price
                        fee = notional * self.commission_bps / 10000.0
                        if qty > 0:
                            cash += notional - fee
                            remaining = current_qty - qty
                            if remaining:
                                positions[symbol] = Position(
                                    symbol, remaining, positions[symbol].cost_basis
                                )
                            else:
                                positions.pop(symbol, None)
                            orders.append(
                                OrderIntent(symbol, Side.SELL.value, qty, fill_price, self.strategy.strategy_id)
                            )
            positions_value = _positions_value(positions, prices)
            equity_curve.append(
                EquityPoint(
                    date=trade_date,
                    equity=cash + positions_value,
                    cash=cash,
                    positions_value=positions_value,
                )
            )

        return BacktestResult(
            equity_curve=equity_curve,
            orders=orders,
            metrics=_metrics(equity_curve, self.starting_cash),
        )


def _common_dates(bars_by_symbol: dict[str, list[Bar]], symbols: tuple[str, ...]) -> list[date]:
    date_sets = []
    for symbol in symbols:
        if symbol not in bars_by_symbol:
            raise ValueError(f"Missing bars for {symbol}")
        date_sets.append({bar.date for bar in bars_by_symbol[symbol]})
    return sorted(set.intersection(*date_sets))


def _close_prices_on(bars_by_symbol: dict[str, list[Bar]], trade_date: date) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        for bar in bars:
            if bar.date == trade_date:
                prices[symbol] = bar.close
                break
    return prices


def _positions_value(positions: dict[str, Position], prices: dict[str, float]) -> float:
    return sum(position.quantity * prices.get(symbol, 0.0) for symbol, position in positions.items())


def _portfolio_value(cash: float, positions: dict[str, Position], prices: dict[str, float]) -> float:
    return cash + _positions_value(positions, prices)


def _metrics(equity_curve: list[EquityPoint], starting_cash: float) -> dict[str, float]:
    if not equity_curve:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "final_equity": starting_cash,
            "sharpe": 0.0,
        }
    final_equity = equity_curve[-1].equity
    peak = starting_cash
    max_drawdown = 0.0
    previous = starting_cash
    daily_returns: list[float] = []
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, point.equity / peak - 1.0)
        if previous > 0:
            daily_returns.append(point.equity / previous - 1.0)
        previous = point.equity
    sharpe = 0.0
    if len(daily_returns) > 1:
        volatility = pstdev(daily_returns)
        if volatility > 0:
            sharpe = mean(daily_returns) / volatility * (252**0.5)
    return {
        "total_return": final_equity / starting_cash - 1.0,
        "max_drawdown": max_drawdown,
        "final_equity": final_equity,
        "sharpe": round(sharpe, 6),
    }
