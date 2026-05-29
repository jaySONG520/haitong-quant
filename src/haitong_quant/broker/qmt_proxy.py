from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib import request

from haitong_quant.broker.base import BrokerAdapter, LiveTradingDisabled
from haitong_quant.models import AccountSnapshot, OrderIntent, OrderRecord, Position, TradeRecord


class QmtProxyBroker(BrokerAdapter):
    """REST adapter for a local QMT/miniQMT proxy.

    The adapter is deliberately conservative: order submission raises unless
    `allow_orders=True` is passed by the caller after compliance and mock
    validation are complete.
    """

    def __init__(self, base_url: str, account_name: str, allow_orders: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.account_name = account_name
        self.allow_orders = allow_orders
        self.session_id: str | None = None

    def connect(self) -> None:
        response = self._post("/api/v1/trading/sessions", {"account_name": self.account_name})
        self.session_id = str(response.get("session_id") or response.get("id") or "")
        if not self.session_id:
            raise RuntimeError("QMT proxy did not return a session id")

    def get_cash(self) -> float:
        snapshot = self.get_account_snapshot()
        return snapshot.cash

    def get_positions(self) -> dict[str, Position]:
        return self.get_account_snapshot().positions

    def get_account_snapshot(self) -> AccountSnapshot:
        self._require_session()
        payload = self._get(f"/api/v1/trading/sessions/{self.session_id}/account")
        positions: dict[str, Position] = {}
        for item in payload.get("positions", []):
            symbol = str(item["symbol"])
            positions[symbol] = Position(
                symbol=symbol,
                quantity=int(item.get("quantity", item.get("volume", 0))),
                cost_basis=float(item.get("cost_basis", item.get("avg_price", 0.0))),
            )
        return AccountSnapshot(
            cash=float(payload.get("cash", payload.get("available_cash", 0.0))),
            positions=positions,
            as_of=datetime.now(),
        )

    def submit_order(self, order: OrderIntent) -> OrderRecord:
        self._require_session()
        if not self.allow_orders:
            raise LiveTradingDisabled("QMT proxy live order submission is disabled")
        payload = {
            "session_id": self.session_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "limit_price": order.limit_price,
            "strategy_id": order.strategy_id,
            "risk_tags": list(order.risk_tags),
        }
        result = self._post("/api/v1/trading/orders", payload)
        return OrderRecord(
            order_id=str(result.get("order_id", "")),
            intent=order,
            status=str(result.get("status", "submitted")),
            created_at=datetime.now(),
            message=str(result.get("message", "")),
        )

    def cancel_order(self, order_id: str) -> OrderRecord:
        self._require_session()
        result = self._post(f"/api/v1/trading/orders/{order_id}/cancel", {})
        placeholder = OrderIntent("", "sell", 0, 0.0, "unknown")
        return OrderRecord(
            order_id=order_id,
            intent=placeholder,
            status=str(result.get("status", "cancel_requested")),
            created_at=datetime.now(),
            message=str(result.get("message", "")),
        )

    def get_orders(self) -> list[OrderRecord]:
        self._require_session()
        payload = self._get(f"/api/v1/trading/sessions/{self.session_id}/orders")
        return [
            OrderRecord(
                order_id=str(item.get("order_id", "")),
                intent=OrderIntent(
                    symbol=str(item.get("symbol", "")),
                    side=str(item.get("side", "sell")),
                    quantity=int(item.get("quantity", 0)),
                    limit_price=float(item.get("limit_price", 0.0)),
                    strategy_id=str(item.get("strategy_id", "external")),
                ),
                status=str(item.get("status", "")),
                created_at=datetime.now(),
                message=str(item.get("message", "")),
            )
            for item in payload.get("orders", [])
        ]

    def get_trades(self) -> list[TradeRecord]:
        self._require_session()
        payload = self._get(f"/api/v1/trading/sessions/{self.session_id}/trades")
        trades: list[TradeRecord] = []
        for item in payload.get("trades", []):
            trades.append(
                TradeRecord(
                    trade_id=str(item.get("trade_id", "")),
                    order_id=str(item.get("order_id", "")),
                    symbol=str(item.get("symbol", "")),
                    side=str(item.get("side", "")),
                    quantity=int(item.get("quantity", 0)),
                    price=float(item.get("price", 0.0)),
                    traded_at=datetime.now(),
                    fees=float(item.get("fees", 0.0)),
                    raw=dict(item),
                )
            )
        return trades

    def _get(self, path: str) -> dict[str, Any]:
        with request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _require_session(self) -> None:
        if not self.session_id:
            raise RuntimeError("QMT proxy session is not connected")
