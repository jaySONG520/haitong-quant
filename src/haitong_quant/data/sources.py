from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from time import sleep
from typing import Iterable, Protocol, Sequence

from haitong_quant.data.cache import DataCache
from haitong_quant.models import Bar

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class MarketDataSource(Protocol):
    def load_bars(
        self, symbols: Iterable[str], start: date | None = None, end: date | None = None
    ) -> dict[str, list[Bar]]:
        ...


class CSVDataSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_bars(
        self, symbols: Iterable[str], start: date | None = None, end: date | None = None
    ) -> dict[str, list[Bar]]:
        wanted = set(symbols)
        grouped: dict[str, list[Bar]] = defaultdict(list)
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = row["symbol"].strip()
                bar_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
                if wanted and symbol not in wanted:
                    continue
                if start and bar_date < start:
                    continue
                if end and bar_date > end:
                    continue
                grouped[symbol].append(
                    Bar(
                        date=bar_date,
                        symbol=symbol,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                    )
                )
        for bars in grouped.values():
            bars.sort(key=lambda item: item.date)
        return dict(grouped)


class AKShareDataSource:
    """AKShare-backed daily bar loader with optional SQLite caching."""

    def __init__(
        self,
        adjust: str = "qfq",
        asset_type: str = "etf",
        retries: int = 4,
        retry_seconds: float = 2.0,
        use_stock_tx_fallback: bool = True,
        cache: DataCache | None = None,
        cache_max_age_days: int | None = None,
    ) -> None:
        self.adjust = adjust
        self.asset_type = asset_type
        self.retries = retries
        self.retry_seconds = retry_seconds
        self.use_stock_tx_fallback = use_stock_tx_fallback
        self.cache = cache
        self.cache_max_age_days = cache_max_age_days

    def load_bars(
        self, symbols: Iterable[str], start: date | None = None, end: date | None = None
    ) -> dict[str, list[Bar]]:
        try:
            import akshare as ak  # type: ignore[import-not-found]
        except ImportError as exc:
            if self.cache is not None:
                cached: dict[str, list[Bar]] = {}
                for symbol in symbols:
                    bars = self.cache.get_bars(
                        symbol,
                        start,
                        end,
                        source="akshare",
                        asset_type=self.asset_type,
                        adjust=self.adjust,
                    )
                    if not bars:
                        raise RuntimeError("AKShare is not installed. Install .[research].") from exc
                    cached[symbol] = bars
                LOGGER.warning("akshare_missing_using_cached_bars")
                return cached
            raise RuntimeError("AKShare is not installed. Install .[research].") from exc

        start_text = (start or date(2000, 1, 1)).strftime("%Y%m%d")
        end_text = (end or date.today()).strftime("%Y%m%d")
        grouped: dict[str, list[Bar]] = {}

        for symbol in symbols:
            if self.cache is not None:
                try:
                    grouped[symbol] = self.cache.get_or_fetch_bars(
                        symbol,
                        lambda item, ak_module=ak: self._fetch_bars(
                            ak_module, item, start_text, end_text
                        ),
                        start=start,
                        end=end,
                        source="akshare",
                        asset_type=self.asset_type,
                        adjust=self.adjust,
                        max_age_days=self.cache_max_age_days,
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "AKShare live fetch failed for %s, trying SQLite cache fallback. Error: %s",
                        symbol,
                        exc,
                    )
                    cached_bars = self.cache.get_bars(
                        symbol,
                        start,
                        end,
                        source="akshare",
                        asset_type=self.asset_type,
                        adjust=self.adjust,
                    )
                    if cached_bars:
                        grouped[symbol] = cached_bars
                    else:
                        LOGGER.error("No SQLite cache available for %s during fallback. Skipping symbol.", symbol)
                        continue
            else:
                grouped[symbol] = self._fetch_bars(ak, symbol, start_text, end_text)
        return grouped

    def _fetch_bars(self, ak, symbol: str, start_text: str, end_text: str) -> list[Bar]:
        frame, aliases = self._fetch_frame(ak, symbol, start_text, end_text)
        bars = _bars_from_frame(symbol, frame, aliases)
        LOGGER.info("akshare_bars_loaded", extra={"symbol": symbol, "rows": len(bars)})
        return bars

    def _fetch_frame(self, ak, symbol: str, start_text: str, end_text: str):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if self.asset_type == "stock":
                    return (
                        ak.stock_zh_a_hist(
                            symbol=symbol,
                            period="daily",
                            start_date=start_text,
                            end_date=end_text,
                            adjust=self.adjust,
                        ),
                        EASTMONEY_BAR_ALIASES,
                    )
                return (
                    ak.fund_etf_hist_em(
                        symbol=symbol,
                        period="daily",
                        start_date=start_text,
                        end_date=end_text,
                        adjust=self.adjust,
                    ),
                    EASTMONEY_BAR_ALIASES,
                )
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    sleep(self.retry_seconds)

        if self.asset_type == "stock" and self.use_stock_tx_fallback:
            return (
                ak.stock_zh_a_hist_tx(
                    symbol=_stock_symbol_with_market(symbol),
                    start_date=start_text,
                    end_date=end_text,
                    adjust=self.adjust,
                ),
                TX_BAR_ALIASES,
            )
        raise RuntimeError(f"AKShare bar fetch failed for {symbol}: {last_error}") from last_error


EASTMONEY_BAR_ALIASES: dict[str, Sequence[str]] = {
    "date": ("日期", "date"),
    "open": ("开盘", "open"),
    "high": ("最高", "high"),
    "low": ("最低", "low"),
    "close": ("收盘", "close"),
    "volume": ("成交量", "volume"),
}

TX_BAR_ALIASES: dict[str, Sequence[str]] = {
    "date": ("date", "日期"),
    "open": ("open", "开盘"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "close": ("close", "收盘"),
    "volume": ("amount", "volume", "成交量"),
}


def _coerce_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _bars_from_frame(
    symbol: str, frame, field_aliases: dict[str, Sequence[str]]
) -> list[Bar]:
    bars: list[Bar] = []
    for _, row in frame.iterrows():
        bars.append(
            Bar(
                date=_coerce_date(_row_value(row, field_aliases["date"])),
                symbol=symbol,
                open=float(_row_value(row, field_aliases["open"])),
                high=float(_row_value(row, field_aliases["high"])),
                low=float(_row_value(row, field_aliases["low"])),
                close=float(_row_value(row, field_aliases["close"])),
                volume=float(_row_value(row, field_aliases["volume"], default=0.0)),
            )
        )
    bars.sort(key=lambda item: item.date)
    return bars


def _row_value(row, aliases: Sequence[str], default: object | None = None) -> object:
    for alias in aliases:
        try:
            value = row[alias]
        except (KeyError, TypeError):
            value = row.get(alias) if hasattr(row, "get") else None
        if value not in {"", None, "-"}:
            return value
    if default is not None:
        return default
    available = ", ".join(str(item) for item in getattr(row, "index", []))
    raise KeyError(f"Missing AKShare field aliases {tuple(aliases)} in row fields: {available}")


def _stock_symbol_with_market(symbol: str) -> str:
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"
