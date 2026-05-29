from __future__ import annotations

from haitong_quant.broker.base import BrokerAdapter, LiveTradingDisabled
from haitong_quant.models import AccountSnapshot, OrderIntent, OrderRecord, TradeRecord


class GuiReadonlyBroker(BrokerAdapter):
    """Placeholder for ordinary client GUI research.

    This class intentionally refuses order submission. It exists so future
    read-only window/control inspection can share the broker interface without
    creating a path to GUI-based live orders.
    """

    def connect(self) -> None:
        return None

    def get_cash(self) -> float:
        raise NotImplementedError("GUI read-only cash query is not implemented")

    def get_positions(self) -> dict:
        raise NotImplementedError("GUI read-only position query is not implemented")

    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError("GUI read-only account query is not implemented")

    def submit_order(self, order: OrderIntent) -> OrderRecord:
        raise LiveTradingDisabled("GUI order submission is forbidden in v1")

    def cancel_order(self, order_id: str) -> OrderRecord:
        raise LiveTradingDisabled("GUI cancellation is forbidden in v1")

    def get_orders(self) -> list[OrderRecord]:
        raise NotImplementedError("GUI read-only order query is not implemented")

    def get_trades(self) -> list[TradeRecord]:
        raise NotImplementedError("GUI read-only trade query is not implemented")
