from __future__ import annotations

import csv
import logging
from pathlib import Path
from time import sleep
from typing import Protocol

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class IndustryMapSource(Protocol):
    def load(self, symbols: tuple[str, ...] | list[str] | None = None) -> dict[str, str]:
        ...


class CSVIndustryMapSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, symbols: tuple[str, ...] | list[str] | None = None) -> dict[str, str]:
        if not self.path.exists():
            return {}
        wanted = set(symbols or ())
        mapping: dict[str, str] = {}
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or row.get("code") or row.get("代码") or "").strip()
                industry = (
                    row.get("industry")
                    or row.get("name")
                    or row.get("industry_name")
                    or row.get("行业")
                    or ""
                ).strip()
                if not symbol or not industry:
                    continue
                if wanted and symbol not in wanted:
                    continue
                mapping[symbol] = industry
        return mapping


class AKShareIndustryMapSource:
    """Best-effort Eastmoney industry map loader.

    The primary production path remains a local CSV. This source enriches it
    when AKShare board constituent APIs are available in the installed version.
    """

    def __init__(self, retries: int = 1, retry_seconds: float = 1.0) -> None:
        self.retries = retries
        self.retry_seconds = retry_seconds

    def load(self, symbols: tuple[str, ...] | list[str] | None = None) -> dict[str, str]:
        try:
            import akshare as ak  # type: ignore[import-not-found]
        except ImportError:
            LOGGER.warning("akshare_not_installed_for_industry_map")
            return {}

        wanted = set(symbols or ())
        result: dict[str, str] = {}
        board_frame = self._call_with_retry(ak.stock_board_industry_name_em)
        if board_frame is None:
            return result

        board_names = [
            str(row.get("板块名称") or row.get("行业名称") or row.get("name") or "")
            for _, row in board_frame.iterrows()
        ]
        for board_name in [name for name in board_names if name]:
            loader = getattr(ak, "stock_board_industry_cons_em", None)
            if loader is None:
                break
            frame = self._call_with_retry(loader, symbol=board_name)
            if frame is None:
                continue
            for _, row in frame.iterrows():
                symbol = str(row.get("代码") or row.get("symbol") or row.get("code") or "")
                if not symbol:
                    continue
                if wanted and symbol not in wanted:
                    continue
                result[symbol] = board_name
            if wanted and wanted.issubset(result):
                break
        return result

    def _call_with_retry(self, fn, **kwargs):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return fn(**kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    sleep(self.retry_seconds)
        LOGGER.warning("akshare_industry_fetch_failed", extra={"error": str(last_error)})
        return None


def load_industry_map(
    csv_path: str | Path,
    symbols: tuple[str, ...] | list[str],
    *,
    use_akshare: bool = False,
) -> dict[str, str]:
    mapping = CSVIndustryMapSource(csv_path).load(symbols)
    if use_akshare:
        remote = AKShareIndustryMapSource().load(symbols)
        mapping.update({k: v for k, v in remote.items() if k not in mapping})
    return mapping
