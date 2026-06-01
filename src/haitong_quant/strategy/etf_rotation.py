from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from haitong_quant.models import Bar, Side, Signal


@dataclass(frozen=True)
class EtfRotationStrategy:
    strategy_id: str
    whitelist: tuple[str, ...]
    lookback_days: int = 20
    top_n: int = 2
    min_momentum: float = 0.0

    def generate_signals(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        as_of: date | None = None,
    ) -> list[Signal]:
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")

        effective_as_of = as_of or _latest_common_date(bars_by_symbol, self.whitelist)
        generated_at = datetime.combine(effective_as_of, time(hour=15, minute=1))
        momentum: list[tuple[str, float]] = []
        insufficient: set[str] = set()

        for symbol in self.whitelist:
            history = [
                bar for bar in bars_by_symbol.get(symbol, []) if bar.date <= effective_as_of
            ]
            history.sort(key=lambda item: item.date)
            if len(history) <= self.lookback_days:
                insufficient.add(symbol)
                continue
            latest = history[-1].close
            base = history[-1 - self.lookback_days].close
            if base <= 0:
                insufficient.add(symbol)
                continue
            momentum.append((symbol, latest / base - 1.0))

        ranked = sorted(momentum, key=lambda item: item[1], reverse=True)
        selected = [
            symbol
            for symbol, value in ranked[: self.top_n]
            if value >= self.min_momentum
        ]
        target_weight = 1.0 / len(selected) if selected else 0.0

        signals: list[Signal] = []
        momentum_by_symbol = dict(momentum)
        for symbol in self.whitelist:
            if symbol in insufficient:
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=Side.HOLD.value,
                        target_weight=0.0,
                        reason="insufficient_history",
                        generated_at=generated_at,
                    )
                )
            elif symbol in selected:
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=Side.BUY.value,
                        target_weight=target_weight,
                        reason=f"ranked_momentum={momentum_by_symbol[symbol]:.6f}",
                        generated_at=generated_at,
                    )
                )
            else:
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=Side.SELL.value,
                        target_weight=0.0,
                        reason=f"not_selected_momentum={momentum_by_symbol.get(symbol, 0):.6f}",
                        generated_at=generated_at,
                    )
                )
        return signals


def _latest_common_date(bars_by_symbol: dict[str, list[Bar]], symbols: tuple[str, ...]) -> date:
    dates: list[date] = []
    for symbol in symbols:
        bars = bars_by_symbol.get(symbol, [])
        if not bars:
            continue
        dates.append(max(bar.date for bar in bars))
    if not dates:
        raise ValueError("No bars loaded for any of the symbols in the strategy whitelist")
    return min(dates)
