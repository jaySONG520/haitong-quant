from __future__ import annotations

from statistics import mean


def volume_ratio(volumes: list[float], short_days: int, long_days: int) -> float:
    if not volumes or all(volume == 0 for volume in volumes):
        return 1.0
    short = mean(volumes[-min(short_days, len(volumes)) :])
    long = mean(volumes[-min(long_days, len(volumes)) :])
    return short / long if long else 1.0
