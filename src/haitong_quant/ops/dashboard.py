from __future__ import annotations

import html
import json
from pathlib import Path


def render_static_dashboard(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    paper_report: dict | None = None,
) -> str:
    items = _load_trade_plan_items(trade_plan_path)
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('symbol', '')))}</td>"
        f"<td>{html.escape(str(item.get('status', '')))}</td>"
        f"<td>{float(item.get('total_score') or 0):.2f}</td>"
        f"<td>{float(item.get('entry_price') or 0):.4f}</td>"
        f"<td>{float(item.get('stop_loss_price_if_entry_fills') or 0):.4f}</td>"
        f"<td>{float(item.get('take_profit_price_if_entry_fills') or 0):.4f}</td>"
        "</tr>"
        for item in items
    )
    paper_summary = html.escape(str((paper_report or {}).get("summary", "n/a")))
    daily_exists = Path(daily_report_path).exists()
    daily_link = html.escape(str(daily_report_path)) if daily_exists else "n/a"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Haitong Quant Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #202124; background: #f7f8fa; }}
    main {{ max-width: 1080px; margin: 0 auto; }}
    section {{ background: #fff; border: 1px solid #dde1e6; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e8eaed; padding: 8px; text-align: left; font-size: 14px; }}
    th {{ background: #f1f3f4; }}
  </style>
</head>
<body>
<main>
  <h1>Haitong Quant Dashboard</h1>
  <section>
    <h2>Trade Plan</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Status</th><th>Score</th><th>Entry</th><th>Stop</th><th>Take Profit</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Paper Trading</h2>
    <p>{paper_summary}</p>
  </section>
  <section>
    <h2>Daily Report</h2>
    <p>{daily_link}</p>
  </section>
</main>
</body>
</html>
"""


def write_static_dashboard(path: str | Path, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def _load_trade_plan_items(path: str | Path) -> list[dict]:
    plan_path = Path(path)
    if not plan_path.exists():
        return []
    payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    items = payload.get("items", [])
    return items if isinstance(items, list) else []
