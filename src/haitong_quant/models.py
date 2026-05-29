from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    target_weight: float
    reason: str
    generated_at: datetime


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: int
    limit_price: float
    strategy_id: str
    risk_tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.limit_price)

    @property
    def idempotency_key(self) -> str:
        return (
            f"{self.strategy_id}:{self.symbol}:{self.side}:"
            f"{self.quantity}:{self.limit_price:.4f}"
        )


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    adjusted_order: OrderIntent | None = None


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    cost_basis: float = 0.0


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    positions: dict[str, Position]
    as_of: datetime


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    intent: OrderIntent
    status: str
    created_at: datetime
    message: str = ""


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    traded_at: datetime
    fees: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
