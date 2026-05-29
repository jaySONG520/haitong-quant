from __future__ import annotations

from datetime import datetime
from itertools import count

from haitong_quant.broker.base import BrokerAdapter
from haitong_quant.models import (
    AccountSnapshot,
    OrderIntent,
    OrderRecord,
    Position,
    Side,
    TradeRecord,
)


class MockBroker(BrokerAdapter):
    def __init__(self, starting_cash: float = 100000.0, fee_bps: float = 2.0) -> None:
        self.cash = starting_cash
        self.fee_bps = fee_bps
        self.positions: dict[str, Position] = {}
        self.orders: list[OrderRecord] = []
        self.trades: list[TradeRecord] = []
        self._order_seq = count(1)
        self._trade_seq = count(1)
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def get_cash(self) -> float:
        return self.cash

    def get_positions(self) -> dict[str, Position]:
        return dict(self.positions)

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            cash=self.cash,
            positions=dict(self.positions),
            as_of=datetime.now(),
        )

    def submit_order(self, order: OrderIntent) -> OrderRecord:
        self._require_connected()
        order_id = f"MOCK-O{next(self._order_seq):06d}"
        fee = order.notional * self.fee_bps / 10000.0
        if order.side == Side.BUY.value:
            total_cost = order.notional + fee
            if total_cost > self.cash:
                record = OrderRecord(order_id, order, "rejected", datetime.now(), "insufficient_cash")
                self.orders.append(record)
                return record
            self.cash -= total_cost
            current = self.positions.get(order.symbol, Position(order.symbol, 0, 0.0))
            new_quantity = current.quantity + order.quantity
            new_cost = (
                current.quantity * current.cost_basis + order.quantity * order.limit_price
            ) / new_quantity
            self.positions[order.symbol] = Position(order.symbol, new_quantity, new_cost)
        elif order.side == Side.SELL.value:
            current = self.positions.get(order.symbol, Position(order.symbol, 0, 0.0))
            if current.quantity < order.quantity:
                record = OrderRecord(
                    order_id,
                    order,
                    "rejected",
                    datetime.now(),
                    "sell_quantity_exceeds_position",
                )
                self.orders.append(record)
                return record
            self.cash += order.notional - fee
            remaining = current.quantity - order.quantity
            if remaining:
                self.positions[order.symbol] = Position(
                    order.symbol, remaining, current.cost_basis
                )
            else:
                self.positions.pop(order.symbol, None)
        else:
            record = OrderRecord(order_id, order, "rejected", datetime.now(), "unsupported_side")
            self.orders.append(record)
            return record

        record = OrderRecord(order_id, order, "filled", datetime.now())
        trade = TradeRecord(
            trade_id=f"MOCK-T{next(self._trade_seq):06d}",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.limit_price,
            traded_at=record.created_at,
            fees=fee,
        )
        self.orders.append(record)
        self.trades.append(trade)
        return record

    def cancel_order(self, order_id: str) -> OrderRecord:
        self._require_connected()
        for record in self.orders:
            if record.order_id == order_id:
                if record.status == "filled":
                    return OrderRecord(
                        order_id,
                        record.intent,
                        "cancel_rejected",
                        datetime.now(),
                        "already_filled",
                    )
                return OrderRecord(order_id, record.intent, "cancelled", datetime.now())
        raise KeyError(order_id)

    def get_orders(self) -> list[OrderRecord]:
        return list(self.orders)

    def get_trades(self) -> list[TradeRecord]:
        return list(self.trades)

    def _require_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("MockBroker is not connected")
