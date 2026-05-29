from __future__ import annotations


def ensure_backtrader_available() -> None:
    try:
        import backtrader  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Backtrader is not installed. Install .[research].") from exc
