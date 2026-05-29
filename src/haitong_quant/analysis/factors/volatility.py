from __future__ import annotations

from statistics import mean

from haitong_quant.models import Bar


def rsi(closes: list[float], days: int) -> float:
    if len(closes) <= days:
        return 50.0
    gains = []
    losses = []
    for prev, current in zip(closes[-days - 1 : -1], closes[-days:]):
        change = current - prev
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def atr_pct(bars: list[Bar], days: int) -> float:
    if len(bars) <= 1:
        return 0.0
    window = bars[-min(days, len(bars) - 1) :]
    true_ranges = []
    previous_close = bars[-len(window) - 1].close
    for bar in window:
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
        previous_close = bar.close
    close = bars[-1].close
    return mean(true_ranges) / close if close > 0 else 0.0
