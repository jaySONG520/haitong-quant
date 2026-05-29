"""交易后复盘日志。

自动记录每次信号、是否触发、买卖价格、盈亏、是否按规则执行，
形成胜率和回撤统计。存储在本地 SQLite 中。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SignalRecord:
    """单次信号记录。"""
    signal_id: str
    signal_date: str
    symbol: str
    direction: str  # buy / sell
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    score: float
    status: str  # pending / triggered / expired / filled / exited
    fill_price: float = 0.0
    exit_price: float = 0.0
    exit_date: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    followed_rules: bool = True
    notes: str = ""


@dataclass(frozen=True)
class JournalSummary:
    """复盘统计汇总。"""
    total_signals: int
    triggered: int
    filled: int
    exited: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_consecutive_losses: int
    total_pnl: float


class TradeJournal:
    """基于 SQLite 的交易复盘日志。"""

    def __init__(self, db_path: str | Path = "data/journal.db") -> None:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_id       TEXT PRIMARY KEY,
                signal_date     TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                direction       TEXT NOT NULL,
                entry_price     REAL NOT NULL,
                stop_loss_price REAL NOT NULL DEFAULT 0,
                take_profit_price REAL NOT NULL DEFAULT 0,
                score           REAL NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'pending',
                fill_price      REAL NOT NULL DEFAULT 0,
                exit_price      REAL NOT NULL DEFAULT 0,
                exit_date       TEXT NOT NULL DEFAULT '',
                pnl             REAL NOT NULL DEFAULT 0,
                pnl_pct         REAL NOT NULL DEFAULT 0,
                followed_rules  INTEGER NOT NULL DEFAULT 1,
                notes           TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """
        )
        conn.commit()

    # ------------------------------------------------------------------
    # 写入操作
    # ------------------------------------------------------------------

    def record_signal(
        self,
        signal_id: str,
        signal_date: str,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
        score: float = 0.0,
        notes: str = "",
    ) -> None:
        """记录一条新信号。"""
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT OR REPLACE INTO signals
                (signal_id, signal_date, symbol, direction, entry_price,
                 stop_loss_price, take_profit_price, score, status, notes,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (signal_id, signal_date, symbol, direction, entry_price,
             stop_loss_price, take_profit_price, score, notes, now, now),
        )
        conn.commit()

    def record_trigger(self, signal_id: str) -> None:
        """标记信号已触发（价格突破入场价）。"""
        self._update_status(signal_id, "triggered")

    def record_fill(self, signal_id: str, fill_price: float) -> None:
        """标记信号已成交。"""
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE signals SET status='filled', fill_price=?, updated_at=? WHERE signal_id=?",
            (fill_price, now, signal_id),
        )
        conn.commit()

    def record_exit(
        self,
        signal_id: str,
        exit_price: float,
        exit_date: str = "",
        followed_rules: bool = True,
        notes: str = "",
    ) -> None:
        """标记退出，自动计算盈亏。"""
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        row = conn.execute(
            "SELECT fill_price, direction FROM signals WHERE signal_id=?",
            (signal_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"信号不存在: {signal_id}")
        fill_price, direction = row[0], row[1]
        if fill_price <= 0:
            raise ValueError(f"信号 {signal_id} 尚未成交，不能标记退出")
        if direction == "buy":
            pnl = exit_price - fill_price
            pnl_pct = pnl / fill_price if fill_price > 0 else 0.0
        else:
            pnl = fill_price - exit_price
            pnl_pct = pnl / fill_price if fill_price > 0 else 0.0
        conn.execute(
            """
            UPDATE signals SET
                status='exited', exit_price=?, exit_date=?,
                pnl=?, pnl_pct=?, followed_rules=?, notes=?, updated_at=?
            WHERE signal_id=?
            """,
            (exit_price, exit_date or now[:10], pnl, pnl_pct,
             1 if followed_rules else 0, notes, now, signal_id),
        )
        conn.commit()

    def record_expired(self, signal_id: str, notes: str = "") -> None:
        """标记信号失效（未触发即过期）。"""
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE signals SET status='expired', notes=?, updated_at=? WHERE signal_id=?",
            (notes, now, signal_id),
        )
        conn.commit()

    def _update_status(self, signal_id: str, status: str) -> None:
        conn = self._get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE signals SET status=?, updated_at=? WHERE signal_id=?",
            (status, now, signal_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_signal(self, signal_id: str) -> SignalRecord | None:
        """按 ID 查询单条信号。"""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT signal_id, signal_date, symbol, direction, entry_price,
                      stop_loss_price, take_profit_price, score, status,
                      fill_price, exit_price, exit_date, pnl, pnl_pct,
                      followed_rules, notes
               FROM signals WHERE signal_id=?""",
            (signal_id,),
        ).fetchone()
        if not row:
            return None
        return SignalRecord(
            signal_id=row[0], signal_date=row[1], symbol=row[2],
            direction=row[3], entry_price=row[4], stop_loss_price=row[5],
            take_profit_price=row[6], score=row[7], status=row[8],
            fill_price=row[9], exit_price=row[10], exit_date=row[11],
            pnl=row[12], pnl_pct=row[13], followed_rules=bool(row[14]),
            notes=row[15],
        )

    def get_all_signals(self, symbol: str | None = None) -> list[SignalRecord]:
        """查询全部信号，可按 symbol 过滤。"""
        conn = self._get_conn()
        if symbol:
            rows = conn.execute(
                """SELECT signal_id, signal_date, symbol, direction, entry_price,
                          stop_loss_price, take_profit_price, score, status,
                          fill_price, exit_price, exit_date, pnl, pnl_pct,
                          followed_rules, notes
                   FROM signals WHERE symbol=? ORDER BY signal_date""",
                (symbol,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT signal_id, signal_date, symbol, direction, entry_price,
                          stop_loss_price, take_profit_price, score, status,
                          fill_price, exit_price, exit_date, pnl, pnl_pct,
                          followed_rules, notes
                   FROM signals ORDER BY signal_date"""
            ).fetchall()
        return [
            SignalRecord(
                signal_id=r[0], signal_date=r[1], symbol=r[2],
                direction=r[3], entry_price=r[4], stop_loss_price=r[5],
                take_profit_price=r[6], score=r[7], status=r[8],
                fill_price=r[9], exit_price=r[10], exit_date=r[11],
                pnl=r[12], pnl_pct=r[13], followed_rules=bool(r[14]),
                notes=r[15],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def summary(self) -> JournalSummary:
        """生成复盘统计汇总。"""
        signals = self.get_all_signals()
        total = len(signals)
        triggered = sum(1 for s in signals if s.status in ("triggered", "filled", "exited"))
        filled = sum(1 for s in signals if s.status in ("filled", "exited"))
        exited = [s for s in signals if s.status == "exited"]
        exits_count = len(exited)
        wins = [s for s in exited if s.pnl > 0]
        losses = [s for s in exited if s.pnl <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / exits_count if exits_count > 0 else 0.0
        total_pnl = sum(s.pnl for s in exited)
        avg_pnl = total_pnl / exits_count if exits_count > 0 else 0.0
        avg_win = sum(s.pnl for s in wins) / win_count if win_count > 0 else 0.0
        avg_loss = sum(s.pnl for s in losses) / loss_count if loss_count > 0 else 0.0
        gross_profit = sum(s.pnl for s in wins)
        gross_loss = abs(sum(s.pnl for s in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        # 最大连亏
        max_consec_losses = 0
        current_streak = 0
        for s in exited:
            if s.pnl <= 0:
                current_streak += 1
                max_consec_losses = max(max_consec_losses, current_streak)
            else:
                current_streak = 0

        return JournalSummary(
            total_signals=total,
            triggered=triggered,
            filled=filled,
            exited=exits_count,
            wins=win_count,
            losses=loss_count,
            win_rate=round(win_rate, 4),
            avg_pnl=round(avg_pnl, 4),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            profit_factor=round(profit_factor, 4),
            max_consecutive_losses=max_consec_losses,
            total_pnl=round(total_pnl, 4),
        )
