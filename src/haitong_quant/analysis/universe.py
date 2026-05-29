from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from time import sleep
from typing import Any

from haitong_quant.data.cache import DataCache

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    name: str
    asset_type: str
    last_price: float
    pct_change: float
    amount: float
    turnover: float
    market_cap: float
    reason: str


@dataclass(frozen=True)
class UniverseFilter:
    asset_type: str = "stock"
    top_n: int = 30
    min_amount: float = 50_000_000.0
    min_price: float = 2.0
    max_price: float = 500.0
    max_abs_pct_change: float = 9.5
    min_turnover: float = 0.2
    exclude_st: bool = True
    include_bj: bool = False


class AKShareUniverseSource:
    def __init__(
        self,
        retries: int = 2,
        retry_seconds: float = 2.0,
        cache: DataCache | None = None,
        cache_max_age_days: int | None = None,
    ) -> None:
        self.retries = retries
        self.retry_seconds = retry_seconds
        self.cache = cache
        self.cache_max_age_days = cache_max_age_days

    def fetch_rows(self, asset_type: str) -> list[dict[str, Any]]:
        if self.cache is not None:
            return self.cache.get_or_fetch_universe(
                asset_type,
                self._fetch_rows_uncached,
                source="akshare",
                max_age_days=self.cache_max_age_days,
            )
        return self._fetch_rows_uncached(asset_type)

    def _fetch_rows_uncached(self, asset_type: str) -> list[dict[str, Any]]:
        try:
            import akshare as ak  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed. Install .[research].") from exc

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                frame = ak.fund_etf_spot_em() if asset_type == "etf" else ak.stock_zh_a_spot_em()
                rows = [dict(row) for _, row in frame.iterrows()]
                LOGGER.info(
                    "akshare_universe_loaded",
                    extra={"asset_type": asset_type, "rows": len(rows)},
                )
                return rows
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    sleep(self.retry_seconds)
        raise RuntimeError(f"AKShare universe fetch failed: {last_error}") from last_error


class CSVUniverseSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch_rows(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]


class UniverseSelector:
    def __init__(self, config: UniverseFilter) -> None:
        self.config = config

    def select(self, rows: list[dict[str, Any]]) -> list[UniverseMember]:
        members = [
            member
            for row in rows
            if (member := self._member_from_row(row)) is not None
        ]
        members.sort(key=lambda item: (item.amount, item.market_cap), reverse=True)
        return members[: self.config.top_n]

    def _member_from_row(self, row: dict[str, Any]) -> UniverseMember | None:
        symbol = str(_pick(row, "代码", "symbol", "code")).strip()
        name = str(_pick(row, "名称", "name", default="")).strip()
        if not symbol:
            return None
        if self.config.asset_type == "stock" and not self.config.include_bj:
            if symbol.startswith(("8", "4")):
                return None
        if self.config.exclude_st and ("ST" in name.upper() or "退" in name):
            return None

        last_price = _float(_pick(row, "最新价", "last_price", "price"))
        pct_change = _float(_pick(row, "涨跌幅", "pct_change", "change_pct"))
        amount = _float(_pick(row, "成交额", "amount"))
        turnover = _float(_pick(row, "换手率", "turnover", default=0.0))
        market_cap = _float(_pick(row, "总市值", "market_cap", default=0.0))

        if last_price < self.config.min_price or last_price > self.config.max_price:
            return None
        if amount < self.config.min_amount:
            return None
        if abs(pct_change) > self.config.max_abs_pct_change:
            return None
        if self.config.asset_type == "stock" and turnover < self.config.min_turnover:
            return None

        reason = (
            f"amount={amount:.0f}; price={last_price:.2f}; "
            f"pct_change={pct_change:.2f}; turnover={turnover:.2f}"
        )
        return UniverseMember(
            symbol=symbol,
            name=name,
            asset_type=self.config.asset_type,
            last_price=last_price,
            pct_change=pct_change,
            amount=amount,
            turnover=turnover,
            market_cap=market_cap,
            reason=reason,
        )


def write_universe_csv(path: str | Path, members: list[UniverseMember]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "name",
                "asset_type",
                "last_price",
                "pct_change",
                "amount",
                "turnover",
                "market_cap",
                "reason",
            ],
        )
        writer.writeheader()
        for member in members:
            writer.writerow(asdict(member))


def write_config_with_universe(
    *,
    base_config_path: str | Path,
    output_path: str | Path,
    members: list[UniverseMember],
    asset_type: str,
) -> None:
    base_path = Path(base_config_path)
    data = json.loads(base_path.read_text(encoding="utf-8-sig"))
    symbols = [member.symbol for member in members]
    data["data"]["source"] = "akshare"
    data["data"]["asset_type"] = asset_type
    data["strategy"]["symbols"] = symbols
    data["risk"]["allowed_symbols"] = symbols
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8-sig",
    )


def _pick(row: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row and row[name] not in {"", None, "-"}:
            return row[name]
    return default


def _float(value: Any) -> float:
    if value in {"", None, "-"}:
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
