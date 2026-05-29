from __future__ import annotations

from datetime import date
from typing import Protocol

from haitong_quant.models import Bar, Signal


class Strategy(Protocol):
    strategy_id: str

    def generate_signals(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        as_of: date | None = None,
    ) -> list[Signal]:
        ...
