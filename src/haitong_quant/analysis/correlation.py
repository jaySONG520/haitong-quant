from __future__ import annotations

from itertools import combinations
from math import sqrt

from haitong_quant.data.cache import DataCache
from haitong_quant.models import Bar


def calculate_correlation_matrix(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    window: int = 60,
    min_overlap: int = 20,
) -> dict[tuple[str, str], float]:
    closes = {
        symbol: {bar.date: bar.close for bar in sorted(bars, key=lambda item: item.date)[-window:]}
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
    matrix: dict[tuple[str, str], float] = {}
    for left, right in combinations(sorted(closes), 2):
        common_dates = sorted(set(closes[left]).intersection(closes[right]))
        if len(common_dates) < min_overlap:
            continue
        xs = [closes[left][item] for item in common_dates[-window:]]
        ys = [closes[right][item] for item in common_dates[-window:]]
        value = _pearson(xs, ys)
        if value is not None:
            matrix[(left, right)] = value
    return matrix


def get_or_calculate_correlation_matrix(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    cache: DataCache | None = None,
    window: int = 60,
    source: str = "",
    asset_type: str = "",
    adjust: str = "",
) -> dict[tuple[str, str], float]:
    if cache is not None:
        cached = cache.get_correlation_matrix(
            window=window, source=source, asset_type=asset_type, adjust=adjust
        )
        if cached:
            return cached
    matrix = calculate_correlation_matrix(bars_by_symbol, window=window)
    if cache is not None:
        cache.put_correlation_matrix(
            matrix,
            window=window,
            source=source,
            asset_type=asset_type,
            adjust=adjust,
        )
    return matrix


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [value - mean_x for value in xs]
    dy = [value - mean_y for value in ys]
    denom_x = sqrt(sum(value * value for value in dx))
    denom_y = sqrt(sum(value * value for value in dy))
    denom = denom_x * denom_y
    if denom == 0:
        return 0.0
    return sum(a * b for a, b in zip(dx, dy)) / denom
