from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from haitong_quant.models import Bar

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class DataCache:
    """Small SQLite cache for bars, universe rows, news scores, and correlations."""

    def __init__(self, db_path: str | Path = "data/cache.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        self._migrate_bars(conn)
        self._migrate_universe(conn)
        self._migrate_news_scores(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS correlations (
                source     TEXT NOT NULL DEFAULT '',
                asset_type TEXT NOT NULL DEFAULT '',
                adjust     TEXT NOT NULL DEFAULT '',
                window     INTEGER NOT NULL,
                symbol_a   TEXT NOT NULL,
                symbol_b   TEXT NOT NULL,
                value      REAL NOT NULL,
                cached_at  TEXT NOT NULL,
                PRIMARY KEY (source, asset_type, adjust, window, symbol_a, symbol_b)
            )
            """
        )
        conn.commit()

    def _migrate_bars(self, conn: sqlite3.Connection) -> None:
        if not _table_exists(conn, "bars"):
            conn.execute(
                """
                CREATE TABLE bars (
                    source    TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL DEFAULT '',
                    adjust    TEXT NOT NULL DEFAULT '',
                    symbol    TEXT NOT NULL,
                    bar_date  TEXT NOT NULL,
                    open      REAL NOT NULL,
                    high      REAL NOT NULL,
                    low       REAL NOT NULL,
                    close     REAL NOT NULL,
                    volume    REAL NOT NULL DEFAULT 0,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (source, asset_type, adjust, symbol, bar_date)
                )
                """
            )
            return

        columns = _columns(conn, "bars")
        if {"source", "asset_type", "adjust"}.issubset(columns):
            return
        conn.execute("ALTER TABLE bars RENAME TO bars_old")
        conn.execute(
            """
            CREATE TABLE bars (
                source    TEXT NOT NULL DEFAULT '',
                asset_type TEXT NOT NULL DEFAULT '',
                adjust    TEXT NOT NULL DEFAULT '',
                symbol    TEXT NOT NULL,
                bar_date  TEXT NOT NULL,
                open      REAL NOT NULL,
                high      REAL NOT NULL,
                low       REAL NOT NULL,
                close     REAL NOT NULL,
                volume    REAL NOT NULL DEFAULT 0,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (source, asset_type, adjust, symbol, bar_date)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO bars
                (source, asset_type, adjust, symbol, bar_date, open, high, low, close, volume, cached_at)
            SELECT '', '', '', symbol, bar_date, open, high, low, close, volume, cached_at
            FROM bars_old
            """
        )
        conn.execute("DROP TABLE bars_old")

    def _migrate_universe(self, conn: sqlite3.Connection) -> None:
        if not _table_exists(conn, "universe"):
            conn.execute(
                """
                CREATE TABLE universe (
                    source     TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL,
                    symbol     TEXT NOT NULL,
                    data_json  TEXT NOT NULL,
                    cached_at  TEXT NOT NULL,
                    PRIMARY KEY (source, asset_type, symbol)
                )
                """
            )
            return

        columns = _columns(conn, "universe")
        if "source" in columns:
            return
        conn.execute("ALTER TABLE universe RENAME TO universe_old")
        conn.execute(
            """
            CREATE TABLE universe (
                source     TEXT NOT NULL DEFAULT '',
                asset_type TEXT NOT NULL,
                symbol     TEXT NOT NULL,
                data_json  TEXT NOT NULL,
                cached_at  TEXT NOT NULL,
                PRIMARY KEY (source, asset_type, symbol)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO universe (source, asset_type, symbol, data_json, cached_at)
            SELECT '', asset_type, symbol, data_json, cached_at FROM universe_old
            """
        )
        conn.execute("DROP TABLE universe_old")

    def _migrate_news_scores(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_scores (
                symbol      TEXT NOT NULL,
                score       REAL NOT NULL,
                summary     TEXT NOT NULL DEFAULT '',
                url         TEXT NOT NULL DEFAULT '',
                as_of       TEXT NOT NULL DEFAULT '',
                event_type  TEXT NOT NULL DEFAULT 'other',
                confidence  REAL NOT NULL DEFAULT 0,
                source_name TEXT NOT NULL DEFAULT '',
                cached_at   TEXT NOT NULL,
                PRIMARY KEY (symbol)
            )
            """
        )
        columns = _columns(conn, "news_scores")
        for name, ddl in {
            "event_type": "ALTER TABLE news_scores ADD COLUMN event_type TEXT NOT NULL DEFAULT 'other'",
            "confidence": "ALTER TABLE news_scores ADD COLUMN confidence REAL NOT NULL DEFAULT 0",
            "source_name": "ALTER TABLE news_scores ADD COLUMN source_name TEXT NOT NULL DEFAULT ''",
        }.items():
            if name not in columns:
                conn.execute(ddl)

    def get_bars(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        *,
        source: str = "",
        asset_type: str = "",
        adjust: str = "",
    ) -> list[Bar] | None:
        conn = self._get_conn()
        query = """
            SELECT bar_date, open, high, low, close, volume
            FROM bars
            WHERE source = ? AND asset_type = ? AND adjust = ? AND symbol = ?
        """
        params: list[Any] = [source, asset_type, adjust, symbol]
        if start:
            query += " AND bar_date >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND bar_date <= ?"
            params.append(end.isoformat())
        query += " ORDER BY bar_date"
        rows = conn.execute(query, params).fetchall()
        if not rows:
            return None
        return [
            Bar(
                date=date.fromisoformat(row[0]),
                symbol=symbol,
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
            )
            for row in rows
        ]

    def put_bars(
        self,
        symbol: str,
        bars: list[Bar],
        *,
        source: str = "",
        asset_type: str = "",
        adjust: str = "",
    ) -> None:
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.executemany(
            """
            INSERT OR REPLACE INTO bars
                (source, asset_type, adjust, symbol, bar_date, open, high, low, close, volume, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source,
                    asset_type,
                    adjust,
                    symbol,
                    bar.date.isoformat(),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    now,
                )
                for bar in bars
            ],
        )
        conn.commit()

    def get_or_fetch_bars(
        self,
        symbol: str,
        fetcher: Callable[[str], list[Bar]],
        start: date | None = None,
        end: date | None = None,
        *,
        source: str = "",
        asset_type: str = "",
        adjust: str = "",
        max_age_days: int | None = None,
    ) -> list[Bar]:
        if max_age_days is not None and self._bars_are_fresh(
            symbol, source, asset_type, adjust, max_age_days
        ):
            cached = self.get_bars(
                symbol, start, end, source=source, asset_type=asset_type, adjust=adjust
            )
            if cached:
                LOGGER.info("bars_cache_hit", extra={"symbol": symbol})
                return cached
        try:
            bars = fetcher(symbol)
            self.put_bars(symbol, bars, source=source, asset_type=asset_type, adjust=adjust)
            LOGGER.info("bars_cache_refresh", extra={"symbol": symbol, "rows": len(bars)})
            return _filter_bars(bars, start, end)
        except Exception:
            cached = self.get_bars(
                symbol, start, end, source=source, asset_type=asset_type, adjust=adjust
            )
            if cached:
                LOGGER.warning("bars_fetch_failed_using_cache", extra={"symbol": symbol})
                return cached
            raise

    def _bars_are_fresh(
        self,
        symbol: str,
        source: str,
        asset_type: str,
        adjust: str,
        max_age_days: int,
    ) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT MAX(cached_at) FROM bars
            WHERE source = ? AND asset_type = ? AND adjust = ? AND symbol = ?
            """,
            (source, asset_type, adjust, symbol),
        ).fetchone()
        if not row or not row[0]:
            return False
        cached_at = datetime.fromisoformat(row[0])
        return cached_at >= datetime.now() - timedelta(days=max_age_days)

    def get_universe(self, asset_type: str, *, source: str = "") -> list[dict[str, Any]] | None:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT data_json FROM universe
            WHERE source = ? AND asset_type = ?
            ORDER BY symbol
            """,
            (source, asset_type),
        ).fetchall()
        if not rows:
            return None
        return [json.loads(row[0]) for row in rows]

    def put_universe(
        self,
        asset_type: str,
        rows: list[dict[str, Any]],
        *,
        source: str = "",
    ) -> None:
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "DELETE FROM universe WHERE source = ? AND asset_type = ?",
            (source, asset_type),
        )
        conn.executemany(
            """
            INSERT INTO universe (source, asset_type, symbol, data_json, cached_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    source,
                    asset_type,
                    _row_symbol(row),
                    json.dumps(row, ensure_ascii=False),
                    now,
                )
                for row in rows
            ],
        )
        conn.commit()

    def get_or_fetch_universe(
        self,
        asset_type: str,
        fetcher: Callable[[str], list[dict[str, Any]]],
        *,
        source: str = "",
        max_age_days: int | None = None,
    ) -> list[dict[str, Any]]:
        if max_age_days is not None and self._universe_is_fresh(
            source, asset_type, max_age_days
        ):
            cached = self.get_universe(asset_type, source=source)
            if cached:
                LOGGER.info("universe_cache_hit", extra={"asset_type": asset_type})
                return cached
        try:
            rows = fetcher(asset_type)
            self.put_universe(asset_type, rows, source=source)
            LOGGER.info(
                "universe_cache_refresh",
                extra={"asset_type": asset_type, "rows": len(rows)},
            )
            return rows
        except Exception:
            cached = self.get_universe(asset_type, source=source)
            if cached:
                LOGGER.warning("universe_fetch_failed_using_cache", extra={"asset_type": asset_type})
                return cached
            raise

    def _universe_is_fresh(self, source: str, asset_type: str, max_age_days: int) -> bool:
        row = self._get_conn().execute(
            "SELECT MAX(cached_at) FROM universe WHERE source = ? AND asset_type = ?",
            (source, asset_type),
        ).fetchone()
        if not row or not row[0]:
            return False
        cached_at = datetime.fromisoformat(row[0])
        return cached_at >= datetime.now() - timedelta(days=max_age_days)

    def get_news_scores(self) -> dict[str, dict[str, Any]] | None:
        rows = self._get_conn().execute(
            """
            SELECT symbol, score, summary, url, as_of, event_type, confidence, source_name
            FROM news_scores ORDER BY symbol
            """
        ).fetchall()
        if not rows:
            return None
        return {
            row[0]: {
                "symbol": row[0],
                "score": row[1],
                "summary": row[2],
                "url": row[3],
                "as_of": row[4],
                "event_type": row[5],
                "confidence": row[6],
                "source_name": row[7],
            }
            for row in rows
        }

    def put_news_scores(self, scores: dict[str, dict[str, Any]]) -> None:
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        for symbol, data in scores.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO news_scores
                    (symbol, score, summary, url, as_of, event_type, confidence, source_name, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    float(data.get("score", 0)),
                    str(data.get("summary", "")),
                    str(data.get("url", "")),
                    str(data.get("as_of", "")),
                    str(data.get("event_type", "other")),
                    float(data.get("confidence", 0)),
                    str(data.get("source_name", "")),
                    now,
                ),
            )
        conn.commit()

    def get_correlation_matrix(
        self,
        *,
        window: int,
        source: str = "",
        asset_type: str = "",
        adjust: str = "",
    ) -> dict[tuple[str, str], float] | None:
        rows = self._get_conn().execute(
            """
            SELECT symbol_a, symbol_b, value FROM correlations
            WHERE source = ? AND asset_type = ? AND adjust = ? AND window = ?
            """,
            (source, asset_type, adjust, window),
        ).fetchall()
        if not rows:
            return None
        return {(row[0], row[1]): float(row[2]) for row in rows}

    def put_correlation_matrix(
        self,
        matrix: dict[tuple[str, str], float],
        *,
        window: int,
        source: str = "",
        asset_type: str = "",
        adjust: str = "",
    ) -> None:
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            DELETE FROM correlations
            WHERE source = ? AND asset_type = ? AND adjust = ? AND window = ?
            """,
            (source, asset_type, adjust, window),
        )
        conn.executemany(
            """
            INSERT INTO correlations
                (source, asset_type, adjust, window, symbol_a, symbol_b, value, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source,
                    asset_type,
                    adjust,
                    window,
                    min(a, b),
                    max(a, b),
                    float(value),
                    now,
                )
                for (a, b), value in matrix.items()
            ],
        )
        conn.commit()

    def invalidate_bars(self, older_than_days: int = 30) -> int:
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat(timespec="seconds")
        cursor = self._get_conn().execute("DELETE FROM bars WHERE cached_at < ?", (cutoff,))
        self._get_conn().commit()
        return cursor.rowcount

    def invalidate_all(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            "DELETE FROM bars; DELETE FROM universe; DELETE FROM news_scores; DELETE FROM correlations;"
        )
        conn.commit()


def _filter_bars(
    bars: list[Bar], start: date | None = None, end: date | None = None
) -> list[Bar]:
    return [
        bar
        for bar in bars
        if (start is None or bar.date >= start) and (end is None or bar.date <= end)
    ]


def _row_symbol(row: dict[str, Any]) -> str:
    for key in ("代码", "symbol", "code"):
        value = row.get(key)
        if value not in {"", None, "-"}:
            return str(value)
    return ""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
