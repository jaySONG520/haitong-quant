from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class DecisionJsonlHandler(logging.Handler):
    def __init__(self, path: str | Path) -> None:
        super().__init__(level=logging.INFO)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() != "risk_decision":
            return
        formatter = logging.Formatter()
        payload = {
            "created_at": formatter.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "logger": record.name,
            "symbol": getattr(record, "symbol", ""),
            "side": getattr(record, "side", ""),
            "approved": getattr(record, "approved", None),
            "reason": getattr(record, "reason", ""),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def setup_logging(
    *,
    log_path: str | Path = "logs/haitong_quant.log",
    decisions_path: str | Path = "logs/decisions.jsonl",
    level: int = logging.INFO,
    console: bool = True,
) -> None:
    root = logging.getLogger()
    if getattr(root, "_haitong_logging_configured", False):
        return
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    file_path = Path(log_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        file_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    root.addHandler(DecisionJsonlHandler(decisions_path))
    setattr(root, "_haitong_logging_configured", True)


def safe_log_extra(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if "key" not in key.lower()
        and "secret" not in key.lower()
        and "token" not in key.lower()
        and "password" not in key.lower()
    }
