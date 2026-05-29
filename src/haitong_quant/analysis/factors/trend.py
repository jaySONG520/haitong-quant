from __future__ import annotations

from statistics import mean


def moving_average(values: list[float], days: int) -> float:
    window = values[-min(days, len(values)) :]
    return mean(window)
