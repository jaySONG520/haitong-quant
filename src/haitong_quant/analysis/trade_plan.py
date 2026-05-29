from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from haitong_quant.analysis.screener import CandidateScore


@dataclass(frozen=True)
class TradePlanItem:
    symbol: str
    status: str
    signal_close: float
    total_score: float
    short_term_bias: str
    medium_term_bias: str
    entry_trigger_pct: float
    entry_price: float
    pre_entry_invalidation_price: float
    stop_loss_pct: float
    stop_loss_price_if_entry_fills: float
    take_profit_pct: float
    take_profit_price_if_entry_fills: float
    trailing_stop_pct: float
    round_trip_fee_pct: float
    assumed_order_value: float
    estimated_round_trip_fee: float
    minimum_order_value_for_30bps_fee_drag: float
    advantages: tuple[str, ...]
    risks: tuple[str, ...]
    news_score: float
    news_summary: str
    news_url: str


def build_trade_plan(
    candidates: list[CandidateScore],
    *,
    order_value: float = 10000.0,
) -> list[TradePlanItem]:
    items: list[TradePlanItem] = []
    for candidate in candidates:
        rule = candidate.trading_rules
        entry_price = candidate.close * (1.0 + rule.entry_trigger_pct)
        pre_entry_invalidation = candidate.close * (1.0 - rule.stop_loss_pct)
        stop_loss_price = entry_price * (1.0 - rule.stop_loss_pct)
        take_profit_price = entry_price * (1.0 + rule.take_profit_pct)
        status = _status(candidate)
        items.append(
            TradePlanItem(
                symbol=candidate.symbol,
                status=status,
                signal_close=candidate.close,
                total_score=candidate.total_score,
                short_term_bias=candidate.short_term_bias,
                medium_term_bias=candidate.medium_term_bias,
                entry_trigger_pct=rule.entry_trigger_pct,
                entry_price=round(entry_price, 4),
                pre_entry_invalidation_price=round(pre_entry_invalidation, 4),
                stop_loss_pct=rule.stop_loss_pct,
                stop_loss_price_if_entry_fills=round(stop_loss_price, 4),
                take_profit_pct=rule.take_profit_pct,
                take_profit_price_if_entry_fills=round(take_profit_price, 4),
                trailing_stop_pct=rule.trailing_stop_pct,
                round_trip_fee_pct=rule.round_trip_fee_pct,
                assumed_order_value=round(order_value, 2),
                estimated_round_trip_fee=round(order_value * rule.round_trip_fee_pct, 2),
                minimum_order_value_for_30bps_fee_drag=rule.minimum_order_value_for_30bps_fee_drag,
                advantages=candidate.advantages,
                risks=candidate.risks,
                news_score=candidate.news_score,
                news_summary=candidate.news_summary,
                news_url=candidate.news_url,
            )
        )
    return items


def write_trade_plan_json(
    path: str | Path,
    items: list[TradePlanItem],
    *,
    config_path: str,
    news_path: str,
    min_score: float,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "research_only": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": config_path,
        "news_input": news_path or None,
        "min_score": min_score,
        "items": [asdict(item) for item in items],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8-sig",
    )


def write_trade_plan_csv(path: str | Path, items: list[TradePlanItem]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "symbol",
        "status",
        "signal_close",
        "total_score",
        "short_term_bias",
        "medium_term_bias",
        "entry_price",
        "pre_entry_invalidation_price",
        "stop_loss_price_if_entry_fills",
        "take_profit_price_if_entry_fills",
        "trailing_stop_pct",
        "round_trip_fee_pct",
        "assumed_order_value",
        "estimated_round_trip_fee",
        "minimum_order_value_for_30bps_fee_drag",
        "news_score",
        "news_summary",
        "news_url",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            data = asdict(item)
            writer.writerow({field: data[field] for field in fields})


def _status(candidate: CandidateScore) -> str:
    if (
        candidate.total_score >= 70
        and candidate.short_term_bias == "rule_constructive"
        and candidate.medium_term_bias == "rule_constructive"
    ):
        return "entry_candidate"
    if candidate.total_score >= 40:
        return "watch_only"
    return "skip"
