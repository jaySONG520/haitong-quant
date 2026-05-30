from __future__ import annotations

from pathlib import Path

from haitong_quant.ops.dashboard import render_static_dashboard


def create_flask_app(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
):
    try:
        from flask import Flask, Response, jsonify
    except ImportError as exc:
        raise RuntimeError("Dashboard server requires Flask. Install with: python -m pip install -e .[web]") from exc

    app = Flask(__name__)

    @app.get("/")
    def index():
        return Response(
            render_static_dashboard(
                trade_plan_path=trade_plan_path,
                daily_report_path=daily_report_path,
            ),
            mimetype="text/html",
        )

    @app.get("/api/trade-plan")
    def trade_plan():
        path = Path(trade_plan_path)
        if not path.exists():
            return jsonify({"items": []})
        return Response(path.read_text(encoding="utf-8-sig"), mimetype="application/json")

    @app.get("/api/daily-report")
    def daily_report():
        path = Path(daily_report_path)
        return jsonify({"path": str(path), "content": path.read_text(encoding="utf-8-sig") if path.exists() else ""})

    return app


def serve_dashboard(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    app = create_flask_app(
        trade_plan_path=trade_plan_path,
        daily_report_path=daily_report_path,
    )
    app.run(host=host, port=port)
