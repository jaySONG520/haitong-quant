from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from haitong_quant.ops.dashboard import (
    SECURITY_INDEX_MAP,
    SECURITY_NAME_MAP,
    build_dashboard_summary,
    render_static_dashboard,
)


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
        return jsonify(fetch_realtime_quotes(symbols_list))

    @app.get("/api/security-trend")
    def security_trend():
        from flask import request

        query = (request.args.get("query") or request.args.get("symbol") or "").strip()
        symbol = resolve_symbol(query, trade_plan_path)
        if not symbol:
            return jsonify({"error": "未找到匹配标的"}), 404

        quotes = fetch_realtime_quotes([symbol])
        quote = quotes.get(symbol, {})
        price = float(quote.get("price") or 0.0)
        klines = fetch_eastmoney_klines(symbol, limit=60)
        trend_source_label = "东方财富日线"
        if not klines:
            klines = fetch_local_klines(symbol, latest_price=price)
            trend_source_label = "本地样例趋势"
        latest_close = klines[-1]["close"] if klines else 0.0
        price = price or latest_close or 0.0
        now = datetime.now()
        return jsonify(
            {
                "query": query,
                "symbol": symbol,
                "name": quote.get("name") or SECURITY_NAME_MAP.get(symbol) or symbol,
                "asset_type": quote.get("asset_type") or "A股/ETF",
                "price": price,
                "change_pct": float(quote.get("change_pct") or 0.0),
                "source": quote.get("source") or "unknown",
                "source_label": quote.get("source_label") or "行情",
                "updated_at": quote.get("refreshed_at") or now.isoformat(timespec="seconds"),
                "updated_at_label": now.strftime("%Y-%m-%d %H:%M:%S"),
                "trend_source_label": trend_source_label,
                "klines": klines,
                "trend": build_trend_metrics(klines, price),
            }
        )

    return app


def resolve_symbol(query: str, trade_plan_path: str | Path = "reports/trade_plan.json") -> str | None:
    normalized = "".join(ch for ch in query.strip() if ch.isalnum())
    if len(normalized) == 6 and normalized.isdigit():
        return normalized

    lower_query = query.strip().lower()
    candidates: list[tuple[str, str, str]] = []
    try:
        path = Path(trade_plan_path)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            for item in payload.get("items", []):
                symbol = str(item.get("symbol") or "")
                if symbol:
                    candidates.append(
                        (
                            symbol,
                            str(item.get("name") or SECURITY_NAME_MAP.get(symbol) or ""),
                            str(item.get("index_name") or SECURITY_INDEX_MAP.get(symbol) or ""),
                        )
                    )
    except Exception:
        candidates = []

    for symbol, name in SECURITY_NAME_MAP.items():
        candidates.append((symbol, name, SECURITY_INDEX_MAP.get(symbol, "")))

    for symbol, name, index_name in candidates:
        haystack = " ".join([symbol, name, index_name]).lower()
        if lower_query and lower_query in haystack:
            return symbol
    return None


def fetch_realtime_quotes(symbols_list: list[str]) -> dict:
    now = datetime.now()
    refreshed_at = now.isoformat(timespec="seconds")
    refreshed_at_label = now.strftime("%Y-%m-%d %H:%M:%S")
    clean_symbols = [_extract_symbol(item) for item in symbols_list]
    close_hints = {_extract_symbol(item): _extract_close_hint(item) for item in symbols_list}
    results: dict[str, dict] = {}

    try:
        queries = [f"s_{_market_prefix(symbol)}{symbol}" for symbol in clean_symbols if symbol]
        if queries:
            url = f"http://qt.gtimg.cn/q={','.join(queries)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                content = response.read().decode("gbk", errors="ignore")
            for line in content.split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                parts = line.split("=", 1)
                symbol = parts[0].split("_")[-1][-6:]
                data_parts = parts[1].strip('"').split("~")
                if len(data_parts) >= 6:
                    results[symbol] = {
                        "name": data_parts[1] or SECURITY_NAME_MAP.get(symbol) or symbol,
                        "price": float(data_parts[3]),
                        "change": _safe_float(data_parts[4]),
                        "change_pct": _safe_float(data_parts[5]),
                        "volume": _safe_float(data_parts[6]) if len(data_parts) > 6 else 0.0,
                        "amount": _safe_float(data_parts[9]) if len(data_parts) > 9 else 0.0,
                        "asset_type": data_parts[10] if len(data_parts) > 10 else "A股/ETF",
                        "source": "live",
                        "source_label": "实时行情",
                        "refreshed_at": refreshed_at,
                    }
    except Exception:
        pass

    import random

    for symbol in clean_symbols:
        if symbol and symbol not in results:
            close_val = close_hints.get(symbol) or 2.0
            oscillation = random.uniform(-0.0005, 0.0005)
            results[symbol] = {
                "name": SECURITY_NAME_MAP.get(symbol) or symbol,
                "price": round(close_val * (1.0 + oscillation), 4),
                "change": 0.0,
                "change_pct": round(oscillation * 100.0, 2),
                "volume": 0.0,
                "amount": 0.0,
                "asset_type": "A股/ETF",
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
    return results


def fetch_eastmoney_klines(symbol: str, limit: int = 60) -> list[dict]:
    secid = f"{_eastmoney_market(symbol)}.{symbol}"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": str(limit),
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4.0) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        klines = payload.get("data", {}).get("klines", []) or []
    except Exception:
        return []

    rows = []
    for raw in klines:
        parts = raw.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": _safe_float(parts[1]),
                "close": _safe_float(parts[2]),
                "high": _safe_float(parts[3]),
                "low": _safe_float(parts[4]),
                "volume": _safe_float(parts[5]),
                "amount": _safe_float(parts[6]),
                "amplitude_pct": _safe_float(parts[7]),
                "change_pct": _safe_float(parts[8]),
                "change": _safe_float(parts[9]),
                "turnover_pct": _safe_float(parts[10]),
            }
        )
    return rows


def fetch_local_klines(symbol: str, latest_price: float = 0.0, path: str | Path = "data/sample_prices.csv") -> list[dict]:
    import csv

    csv_path = Path(path)
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("symbol") != symbol:
                    continue
                rows.append(
                    {
                        "date": str(row.get("date") or ""),
                        "open": _safe_float(row.get("open")),
                        "close": _safe_float(row.get("close")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "volume": _safe_float(row.get("volume")),
                        "amount": 0.0,
                        "amplitude_pct": 0.0,
                        "change_pct": 0.0,
                        "change": 0.0,
                        "turnover_pct": 0.0,
                    }
                )
    except Exception:
        return []

    rows = rows[-60:]
    if latest_price > 0 and rows and rows[-1]["close"] > 0:
        scale = latest_price / rows[-1]["close"]
        for row in rows:
            for field in ("open", "close", "high", "low"):
                row[field] = round(row[field] * scale, 4)
        rows[-1]["close"] = latest_price
    return rows


def build_trend_metrics(klines: list[dict], latest_price: float) -> dict:
    closes = [float(item["close"]) for item in klines if item.get("close")]
    if latest_price > 0:
        closes = closes[:-1] + [latest_price] if closes else [latest_price]
    ma5 = sum(closes[-5:]) / min(5, len(closes)) if closes else 0.0
    ma20 = sum(closes[-20:]) / min(20, len(closes)) if closes else 0.0
    return_5d = _period_return(closes, 5)
    return_20d = _period_return(closes, 20)
    if len(closes) >= 20 and latest_price >= ma5 >= ma20 and return_20d >= 0:
        trend_label = "偏强上行"
    elif len(closes) >= 20 and latest_price <= ma5 <= ma20 and return_20d < 0:
        trend_label = "偏弱下行"
    else:
        trend_label = "震荡观察"
    return {
        "ma5": round(ma5, 4),
        "ma20": round(ma20, 4),
        "return_5d_pct": round(return_5d * 100, 2) if return_5d is not None else None,
        "return_20d_pct": round(return_20d * 100, 2) if return_20d is not None else None,
        "trend_label": trend_label,
    }


def _period_return(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or closes[-1 - days] == 0:
        return None
    return closes[-1] / closes[-1 - days] - 1.0


def _extract_symbol(value: str) -> str:
    return value.split(":", 1)[0].strip()


def _extract_close_hint(value: str) -> float | None:
    if ":" not in value:
        return None
    try:
        return float(value.split(":", 1)[1])
    except ValueError:
        return None


def _market_prefix(symbol: str) -> str:
    return "sh" if symbol.startswith(("5", "6", "9")) else "sz"


def _eastmoney_market(symbol: str) -> str:
    return "1" if symbol.startswith(("5", "6", "9")) else "0"


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
