from __future__ import annotations

from datetime import datetime
from pathlib import Path

from haitong_quant.analysis.screener import CandidateScore


def render_research_report(
    candidates: list[CandidateScore],
    *,
    title: str = "Quant Candidate Research Report",
    config_path: str = "",
    news_path: str = "",
    order_value: float = 10000.0,
    min_score: float = 55.0,
) -> str:
    lines: list[str] = [
        f"# {title}",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Config: {config_path or 'n/a'}",
        f"- News input: {news_path or 'none'}",
        f"- Assumed order value: {order_value:.2f}",
        f"- Minimum score: {min_score:.2f}",
        "",
        "> Research output only. This is a rules-based screen, not a return guarantee or personalized buy/sell instruction.",
        "",
    ]
    if not candidates:
        lines.extend(
            [
                "## No Candidates Passed",
                "",
                "No symbol met the configured score threshold. Review the universe, news input, and threshold before changing risk limits.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.append("## Ranked Candidates")
    lines.append("")
    for index, candidate in enumerate(candidates, start=1):
        rule = candidate.trading_rules
        lines.extend(
            [
                f"### {index}. {candidate.symbol}",
                "",
                f"- Close: {candidate.close}",
                f"- Total score: {candidate.total_score}",
                f"- Short-term bias: {candidate.short_term_bias}",
                f"- Medium-term bias: {candidate.medium_term_bias}",
                f"- News score: {candidate.news_score}",
                f"- News summary: {candidate.news_summary}",
                f"- News URL: {candidate.news_url or 'n/a'}",
                "",
                "Advantages:",
            ]
        )
        lines.extend(f"- {item}" for item in candidate.advantages)
        lines.extend(["", "Risks:"])
        lines.extend(f"- {item}" for item in candidate.risks)
        lines.extend(
            [
                "",
                "Key metrics:",
                f"- 5-day return: {candidate.metrics['ret5']:.2%}",
                f"- 20-day return: {candidate.metrics['ret20']:.2%}",
                f"- MA5 / MA20 / MA60: {candidate.metrics['ma5']} / {candidate.metrics['ma20']} / {candidate.metrics['ma60']}",
                f"- RSI14: {candidate.metrics['rsi14']}",
                f"- ATR14 pct: {candidate.metrics['atr14_pct']:.2%}",
                f"- Volume ratio 5/20: {candidate.metrics['volume_ratio_5_20']}",
                f"- 20-day drawdown: {candidate.metrics['drawdown20']:.2%}",
                "",
                "Fee-aware rules:",
                f"- Entry trigger: {rule.entry_trigger_pct:.2%}",
                f"- Stop loss: {rule.stop_loss_pct:.2%}",
                f"- Take profit: {rule.take_profit_pct:.2%}",
                f"- Trailing stop: {rule.trailing_stop_pct:.2%}",
                f"- Round-trip fee drag: {rule.round_trip_fee_pct:.2%}",
                f"- Minimum order value for about 30 bps fee drag: {rule.minimum_order_value_for_30bps_fee_drag:.2f}",
                f"- Rule text: {rule.rule_text}",
                "",
            ]
        )
    return "\n".join(lines)


def write_research_report(path: str | Path, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8-sig")
