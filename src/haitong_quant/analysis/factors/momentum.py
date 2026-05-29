from __future__ import annotations


def period_return(closes: list[float], days: int) -> float:
    if len(closes) <= days or closes[-1 - days] <= 0:
        return 0.0
    return closes[-1] / closes[-1 - days] - 1.0


def scale(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return (value - low) / (high - low) * 100.0
