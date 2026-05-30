from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
import logging
from pathlib import Path
from time import sleep
from typing import Callable

from haitong_quant.ops.notifiers import Notifier


LOGGER = logging.getLogger(__name__)


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
    sent_keys = _load_existing_alert_keys(alerts_path)
    while True:
        alerts = [
            alert
            for alert in evaluate_trade_plan(trade_plan_path, price_loader())
            if _alert_key(alert) not in sent_keys
        ]
        if alerts:
            append_alerts(alerts_path, alerts)
            for alert in alerts:
                sent_keys.add(_alert_key(alert))
                try:
                    notifier.send(_alert_title(alert), _alert_body(alert))
                except Exception as exc:
                    LOGGER.warning(
                        "notifier_send_failed",
                        extra={
                            "symbol": alert.symbol,
                            "alert_type": alert.alert_type,
                            "error": str(exc),
                        },
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


def _load_existing_alert_keys(path: str | Path) -> set[str]:
    alerts_path = Path(path)
    if not alerts_path.exists():
        return set()
    keys: set[str] = set()
    for line in alerts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        symbol = str(data.get("symbol", ""))
        alert_type = str(data.get("alert_type", ""))
        threshold = float(data.get("threshold") or 0)
        if symbol and alert_type:
            keys.add(f"{symbol}|{alert_type}|{threshold:.6f}")
    return keys


def _alert_key(alert: MonitorAlert) -> str:
    return f"{alert.symbol}|{alert.alert_type}|{alert.threshold:.6f}"


def _alert_title(alert: MonitorAlert) -> str:
    labels = {
        "entry_triggered": "入场触发",
        "pre_entry_invalidated": "入场前失效",
        "stop_loss_triggered": "止损触发",
        "take_profit_triggered": "止盈触发",
    }
    label = labels.get(alert.alert_type, alert.alert_type)
    return f"{alert.symbol} {label}"


def _alert_body(alert: MonitorAlert) -> str:
    labels = {
        "entry_triggered": "当前价格已达到或高于入场触发价，请复核交易计划。",
        "pre_entry_invalidated": "当前价格已跌破入场前失效价，本次入场计划应标记失效。",
        "stop_loss_triggered": "当前价格已触及止损价，请按风控规则复核。",
        "take_profit_triggered": "当前价格已触及止盈价，请复核是否减仓或退出。",
    }
    prefix = labels.get(alert.alert_type, "监控条件已触发，请复核。")
    return (
        f"{prefix}\n"
        f"当前价：{alert.price:.4f}\n"
        f"阈值：{alert.threshold:.4f}\n"
        f"触发时间：{alert.generated_at}"
    )


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
