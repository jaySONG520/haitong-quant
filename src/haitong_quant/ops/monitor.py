from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Callable

from haitong_quant.ops.notifiers import Notifier


@dataclass(frozen=True)
class MonitorAlert:
    symbol: str
    alert_type: str
    price: float
    threshold: float
    generated_at: str


def evaluate_trade_plan(
    trade_plan_path: str | Path,
    current_prices: dict[str, float],
) -> list[MonitorAlert]:
    payload = json.loads(Path(trade_plan_path).read_text(encoding="utf-8-sig"))
    alerts: list[MonitorAlert] = []
    for item in payload.get("items", []):
        symbol = item.get("symbol", "")
        price = current_prices.get(symbol)
        if price is None:
            continue
        alerts.extend(_alerts_for_item(item, price))
    return alerts


def monitor_loop(
    *,
    trade_plan_path: str | Path,
    price_loader: Callable[[], dict[str, float]],
    alerts_path: str | Path,
    notifier: Notifier,
    interval_seconds: float = 60.0,
    once: bool = False,
) -> list[MonitorAlert]:
    all_alerts: list[MonitorAlert] = []
    while True:
        alerts = evaluate_trade_plan(trade_plan_path, price_loader())
        if alerts:
            append_alerts(alerts_path, alerts)
            for alert in alerts:
                notifier.send(
                    f"{alert.symbol} {alert.alert_type}",
                    f"price={alert.price:.4f}; threshold={alert.threshold:.4f}",
                )
            all_alerts.extend(alerts)
        if once:
            return all_alerts
        sleep(interval_seconds)


def append_alerts(path: str | Path, alerts: list[MonitorAlert]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(json.dumps(asdict(alert), ensure_ascii=False) + "\n")


def _alerts_for_item(item: dict, price: float) -> list[MonitorAlert]:
    now = datetime.now().isoformat(timespec="seconds")
    alerts: list[MonitorAlert] = []
    symbol = str(item.get("symbol", ""))
    status = str(item.get("status", ""))
    entry = float(item.get("entry_price") or 0)
    invalidation = float(item.get("pre_entry_invalidation_price") or 0)
    stop_loss = float(item.get("stop_loss_price_if_entry_fills") or 0)
    take_profit = float(item.get("take_profit_price_if_entry_fills") or 0)

    if status in {"entry_candidate", "watch_only"}:
        if entry > 0 and price >= entry:
            alerts.append(MonitorAlert(symbol, "entry_triggered", price, entry, now))
        if invalidation > 0 and price <= invalidation:
            alerts.append(MonitorAlert(symbol, "pre_entry_invalidated", price, invalidation, now))
    if stop_loss > 0 and price <= stop_loss:
        alerts.append(MonitorAlert(symbol, "stop_loss_triggered", price, stop_loss, now))
    if take_profit > 0 and price >= take_profit:
        alerts.append(MonitorAlert(symbol, "take_profit_triggered", price, take_profit, now))
    return alerts
