"""自动日报生成器。

每天收盘后生成研究日报，包含：候选名单、剔除原因、持仓规则、
明日触发价、风险提示、复盘统计。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from haitong_quant.analysis.journal import JournalSummary
from haitong_quant.analysis.screener import CandidateScore
from haitong_quant.analysis.trade_plan import TradePlanItem


def generate_daily_report(
    *,
    candidates: list[CandidateScore],
    trade_plan: list[TradePlanItem],
    rejected_symbols: dict[str, str] | None = None,
    journal_summary: JournalSummary | None = None,
    report_date: str = "",
    config_path: str = "",
    order_value: float = 10000.0,
) -> str:
    """生成收盘后的研究日报 Markdown。"""
    now = report_date or datetime.now().strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# 研究日报 — {now}",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 配置: {config_path or 'n/a'}",
        f"- 假定单笔金额: {order_value:.2f}",
        "",
        "> 本报告为规则筛选结果，不构成投资建议，不保证收益。",
        "",
    ]

    # ---- 候选名单 ----
    lines.append("## 一、候选名单")
    lines.append("")
    if trade_plan:
        lines.append("| 代码 | 状态 | 评分 | 入场价 | 止损价 | 止盈价 | 跟踪止损 | 往返费用 |")
        lines.append("|------|------|------|--------|--------|--------|----------|----------|")
        for item in trade_plan:
            lines.append(
                f"| {item.symbol} | {item.status} | {item.total_score:.1f} "
                f"| {item.entry_price:.4f} | {item.stop_loss_price_if_entry_fills:.4f} "
                f"| {item.take_profit_price_if_entry_fills:.4f} "
                f"| {item.trailing_stop_pct:.2%} | {item.estimated_round_trip_fee:.2f} |"
            )
        lines.append("")
    else:
        lines.extend(["无候选标的通过筛选阈值。", ""])

    # ---- 明日触发价一览 ----
    entry_candidates = [item for item in trade_plan if item.status == "entry_candidate"]
    if entry_candidates:
        lines.append("## 二、明日触发价一览")
        lines.append("")
        lines.append("| 代码 | 信号收盘价 | 入场触发价 | 失效价 |")
        lines.append("|------|-----------|-----------|--------|")
        for item in entry_candidates:
            lines.append(
                f"| {item.symbol} | {item.signal_close:.4f} "
                f"| {item.entry_price:.4f} | {item.pre_entry_invalidation_price:.4f} |"
            )
        lines.append("")
    else:
        lines.extend(["## 二、明日触发价一览", "", "无 entry_candidate 状态标的。", ""])

    # ---- 剔除原因 ----
    lines.append("## 三、被剔除标的及原因")
    lines.append("")
    if rejected_symbols:
        for symbol, reason in sorted(rejected_symbols.items()):
            lines.append(f"- **{symbol}**: {reason}")
        lines.append("")
    else:
        lines.extend(["暂无剔除记录（所有已配置标的均参与筛选）。", ""])

    # ---- 风险提示 ----
    lines.append("## 四、风险提示汇总")
    lines.append("")
    all_risks: dict[str, list[str]] = {}
    for c in candidates:
        if c.risks:
            all_risks[c.symbol] = list(c.risks)
    if all_risks:
        for symbol, risks in sorted(all_risks.items()):
            lines.append(f"**{symbol}**:")
            for risk in risks:
                lines.append(f"  - {risk}")
        lines.append("")
    else:
        lines.extend(["各候选标的暂无突出风险标记。", ""])

    # ---- 复盘统计 ----
    lines.append("## 五、复盘统计")
    lines.append("")
    if journal_summary and journal_summary.total_signals > 0:
        s = journal_summary
        lines.extend([
            f"- 总信号数: {s.total_signals}",
            f"- 已触发: {s.triggered}",
            f"- 已成交: {s.filled}",
            f"- 已退出: {s.exited}",
            f"- 胜率: {s.win_rate:.1%}",
            f"- 平均盈亏: {s.avg_pnl:.4f}",
            f"- 平均盈利: {s.avg_win:.4f}",
            f"- 平均亏损: {s.avg_loss:.4f}",
            f"- 盈亏比: {s.profit_factor:.2f}",
            f"- 最大连亏: {s.max_consecutive_losses}",
            f"- 累计盈亏: {s.total_pnl:.4f}",
            "",
        ])
    else:
        lines.extend(["暂无复盘数据。首次使用 `journal` 命令记录信号后，此处将显示统计。", ""])

    # ---- 持仓规则提醒 ----
    lines.append("## 六、持仓规则提醒")
    lines.append("")
    lines.extend([
        "- 所有候选仅为规则筛选结果，**不是**买卖指令。",
        "- entry_candidate 状态表示规则层面的强候选，仍需人工确认。",
        "- watch_only 状态表示仅观察，不应自动转成市价买入。",
        "- 请在成交前确认新闻面无重大变化。",
        "- 遵守单笔/单日/总仓位限额。",
        "",
    ])

    return "\n".join(lines)


def write_daily_report(path: str | Path, content: str) -> None:
    """写入日报文件。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8-sig")
