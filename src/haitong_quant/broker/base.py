from __future__ import annotations

from abc import ABC, abstractmethod

from haitong_quant.models import AccountSnapshot, OrderIntent, OrderRecord, TradeRecord


class LiveTradingDisabled(RuntimeError):
    pass


class BrokerAdapter(ABC):
    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_cash(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order: OrderIntent) -> OrderRecord:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderRecord:
        raise NotImplementedError

    @abstractmethod
    def get_orders(self) -> list[OrderRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_trades(self) -> list[TradeRecord]:
        raise NotImplementedError
