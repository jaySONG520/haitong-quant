from __future__ import annotations

from datetime import datetime
from pathlib import Path

from haitong_quant.ops.dashboard import build_dashboard_summary, render_static_dashboard


def create_flask_app(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    dashboard_poll_interval_seconds: int = 30,
    dashboard_min_poll_interval_seconds: int = 5,
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
                dashboard_poll_interval_seconds=dashboard_poll_interval_seconds,
                dashboard_min_poll_interval_seconds=dashboard_min_poll_interval_seconds,
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

    @app.get("/api/dashboard-summary")
    def dashboard_summary():
        return jsonify(
            build_dashboard_summary(
                trade_plan_path=trade_plan_path,
                daily_report_path=daily_report_path,
                dashboard_poll_interval_seconds=dashboard_poll_interval_seconds,
                dashboard_min_poll_interval_seconds=dashboard_min_poll_interval_seconds,
            )
        )

    @app.post("/api/save-daily-report")
    def save_daily_report():
        from flask import request
        req_data = request.json or {}
        content = req_data.get("content", req_data.get("markdown", ""))
        path = Path(daily_report_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8-sig")
            return jsonify({"success": True, "message": "日报修改已成功发布"})
        except Exception as exc:
            return jsonify({"success": False, "message": f"保存失败：{exc}"}), 500

    @app.get("/api/realtime-prices")
    def realtime_prices():
        from flask import request
        symbols_str = request.args.get("symbols", "")
        if not symbols_str:
            return jsonify({})
        symbols_list = [s.strip() for s in symbols_str.split(",") if s.strip()]
        now = datetime.now()
        refreshed_at = now.isoformat(timespec="seconds")
        refreshed_at_label = now.strftime("%Y-%m-%d %H:%M:%S")
        
        results = {}
        try:
            import urllib.request
            queries = []
            for s in symbols_list:
                # 前端传入可能带有 close 价格，比如 '510300:3.895'
                sym = s.split(":")[0]
                prefix = "sh" if sym.startswith(("5", "6", "9")) else "sz"
                queries.append(f"s_{prefix}{sym}")
            
            url = f"http://qt.gtimg.cn/q={','.join(queries)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                content = response.read().decode("gbk", errors="ignore")
                
            for line in content.split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                parts = line.split("=", 1)
                symbol_part = parts[0].split("_")[-1]
                symbol = symbol_part[-6:]
                data_str = parts[1].strip('"')
                data_parts = data_str.split("~")
                if len(data_parts) >= 6:
                    price = float(data_parts[3])
                    change_pct = float(data_parts[5])
                    results[symbol] = {
                        "price": price,
                        "change_pct": change_pct,
                        "source": "live",
                        "source_label": "实时行情",
                        "refreshed_at": refreshed_at,
                    }
        except Exception:
            pass

        # 针对网络超时或脱机情况，启用自适应随机微幅震荡
        import random
        for s in symbols_list:
            parts = s.split(":")
            sym = parts[0]
            if sym not in results:
                close_val = 2.0
                if len(parts) > 1:
                    try:
                        close_val = float(parts[1])
                    except ValueError:
                        pass
                # 产生极其柔和的 -0.05% 到 +0.05% 的真实跳动模拟
                oscillation = random.uniform(-0.0005, 0.0005)
                simulated_price = round(close_val * (1.0 + oscillation), 4)
                simulated_change = round(oscillation * 100.0, 2)
                results[sym] = {
                    "price": simulated_price,
                    "change_pct": simulated_change,
                    "source": "simulated",
                    "source_label": "模拟行情",
                    "refreshed_at": refreshed_at,
                }

        quote_values = [value for key, value in results.items() if not key.startswith("__")]
        live_count = sum(1 for value in quote_values if value.get("source") == "live")
        if live_count == len(quote_values) and quote_values:
            source = "live"
            source_label = "实时行情"
        elif live_count > 0:
            source = "mixed"
            source_label = "实时/模拟混合行情"
        else:
            source = "simulated"
            source_label = "模拟行情"
        results["__meta__"] = {
            "refreshed_at": refreshed_at,
            "refreshed_at_label": refreshed_at_label,
            "source": source,
            "source_label": source_label,
            "live_count": live_count,
            "total_count": len(quote_values),
        }
        return jsonify(results)

    return app


def serve_dashboard(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    host: str = "127.0.0.1",
    port: int = 8765,
    dashboard_poll_interval_seconds: int = 30,
    dashboard_min_poll_interval_seconds: int = 5,
) -> None:
    app = create_flask_app(
        trade_plan_path=trade_plan_path,
        daily_report_path=daily_report_path,
        dashboard_poll_interval_seconds=dashboard_poll_interval_seconds,
        dashboard_min_poll_interval_seconds=dashboard_min_poll_interval_seconds,
    )
    app.run(host=host, port=port)
