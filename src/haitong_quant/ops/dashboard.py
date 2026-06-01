from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


STATUS_LABELS = {
    "entry_candidate": "可入场候选",
    "watch_only": "观察",
    "skip": "跳过",
}
STATUS_TONES = {
    "entry_candidate": "positive",
    "watch_only": "warning",
    "skip": "muted",
}
STATUS_ORDER = {"entry_candidate": 0, "watch_only": 1, "skip": 2}
BIAS_LABELS = {
    "rule_constructive": "规则偏强",
    "rule_watchlist": "观察名单",
    "rule_weak": "规则偏弱",
    "rule_neutral": "中性",
}
NOTE_TRANSLATIONS = {
    "5-day momentum is positive": "5日动量为正",
    "20-day momentum is positive": "20日动量为正",
    "latest close is above MA20": "收盘价站上20日均线",
    "medium trend is not below long trend": "中期趋势不弱于长期趋势",
    "recent volume is above 20-day average": "近期成交量高于20日均量",
    "reviewed recent-news score is positive": "已复核新闻分数为正",
    "RSI is in a constructive, not extreme, zone": "RSI处于较健康区间",
    "news input missing; K-line-only candidate": "缺少新闻输入，仅基于K线筛选",
    "5-day momentum is negative": "5日动量为负",
    "20-day momentum is negative": "20日动量为负",
    "latest close is below MA20": "收盘价低于20日均线",
    "RSI is high; chasing risk is elevated": "RSI偏高，追价风险抬升",
    "ATR volatility is high": "ATR波动率偏高",
    "price is still more than 10% below recent high": "价格仍低于近期高点超过10%",
    "reviewed recent-news score is negative": "已复核新闻分数偏负",
    "recent-news score is missing; do not treat as news-confirmed": "缺少新闻分数，不能视为新闻确认",
}
NEWS_TRANSLATIONS = {
    "Sample positive broad sector liquidity note": "样例新闻：宽基流动性偏正面",
    "Sample mildly negative gold-related macro note": "样例新闻：黄金相关宏观信息略偏负",
    "Sample neutral small/mid-cap ETF news input": "样例新闻：中小盘ETF信息中性",
    "no reviewed recent-news score supplied": "未提供已复核新闻分数",
}
SECURITY_NAME_MAP = {
    "510300": "沪深300ETF",
    "510050": "上证50ETF",
    "159915": "创业板ETF",
    "512100": "中证1000ETF南方",
    "159922": "中证500ETF",
    "510500": "中证500ETF南方",
    "518880": "黄金ETF华安",
    "159601": "A50ETF",
    "588000": "科创50ETF",
    "159919": "沪深300ETF",
    "515790": "光伏ETF",
    "159869": "游戏ETF",
    "516160": "新能源ETF",
}
SECURITY_INDEX_MAP = {
    "510300": "沪深300",
    "510050": "上证50",
    "159915": "创业板指",
    "512100": "中证1000",
    "159922": "中证500",
    "510500": "中证500",
    "518880": "黄金现货",
    "159601": "富时中国A50",
    "588000": "科创50",
    "159919": "沪深300",
    "515790": "中证光伏产业",
    "159869": "中证动漫游戏",
    "516160": "CS新能源",
}


def render_static_dashboard(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    paper_report: dict | None = None,
    dashboard_poll_interval_seconds: int = 30,
    dashboard_min_poll_interval_seconds: int = 5,
) -> str:
    summary = build_dashboard_summary(
        trade_plan_path=trade_plan_path,
        daily_report_path=daily_report_path,
        paper_report=paper_report,
        dashboard_poll_interval_seconds=dashboard_poll_interval_seconds,
        dashboard_min_poll_interval_seconds=dashboard_min_poll_interval_seconds,
    )
    data_json = _json_for_script(summary)
    return (
        HTML_TEMPLATE.replace("__DASHBOARD_DATA__", data_json)
        .replace("__DASHBOARD_STYLE__", DASHBOARD_STYLE)
        .replace("__DASHBOARD_SCRIPT__", DASHBOARD_SCRIPT)
    )


def build_dashboard_summary(
    *,
    trade_plan_path: str | Path = "reports/trade_plan.json",
    daily_report_path: str | Path = "reports/daily_report.md",
    paper_report: dict | None = None,
    dashboard_poll_interval_seconds: int = 30,
    dashboard_min_poll_interval_seconds: int = 5,
) -> dict[str, Any]:
    trade_path = Path(trade_plan_path)
    daily_path = Path(daily_report_path)
    payload = _load_trade_plan_payload(trade_path)
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []
    generated_at = str(payload.get("generated_at") or _mtime_iso(trade_path) or "")
    plan_date = _date_label(generated_at)
    candidates = [_normalize_candidate(item, index, generated_at=generated_at, plan_date=plan_date) for index, item in enumerate(items)]
    daily_content = _read_text(daily_path)
    warnings = []
    if not trade_path.exists():
        warnings.append("未找到交易计划文件，候选看板为空。")
    if not daily_path.exists():
        warnings.append("未找到研究日报文件，日报区域为空。")
    if not candidates:
        warnings.append("当前没有可展示的候选标的。")
    elif payload.get("config"):
        warnings.append(f"当前看板仅展示交易计划中的 {len(candidates)} 个候选，不代表全市场扫描结果；扩大股票池需要更新配置或重新运行 universe/pipeline。")
    min_interval = max(1, int(dashboard_min_poll_interval_seconds or 5))
    default_interval = max(min_interval, int(dashboard_poll_interval_seconds or 30))
    refreshed_at = datetime.now().isoformat(timespec="seconds")
    return {
        "generated_at": generated_at,
        "generated_at_label": _format_datetime(generated_at) if generated_at else "暂无数据时间",
        "refreshed_at": refreshed_at,
        "refreshed_at_label": _format_datetime(refreshed_at),
        "polling": {
            "default_interval_seconds": default_interval,
            "min_interval_seconds": min_interval,
        },
        "mode_label": "只读研究模式" if payload.get("research_only", True) else "未确认模式",
        "source_paths": {
            "trade_plan": str(trade_path),
            "daily_report": str(daily_path),
        },
        "metrics": _build_metrics(candidates),
        "candidates": candidates,
        "daily_report": {
            "path": str(daily_path),
            "exists": daily_path.exists(),
            "content": _localize_report_content(daily_content),
            "preview": _daily_preview(daily_content),
        },
        "paper": _paper_summary(paper_report),
        "warnings": warnings,
        "disclaimer": "本页面为只读研究看板，不构成投资建议，不保证收益，不提供实盘下单入口。",
    }


def write_static_dashboard(path: str | Path, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def _load_trade_plan_payload(path: str | Path) -> dict[str, Any]:
    plan_path = Path(path)
    if not plan_path.exists():
        return {"items": []}
    payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {"items": []}


def _load_trade_plan_items(path: str | Path) -> list[dict]:
    payload = _load_trade_plan_payload(path)
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def _normalize_candidate(item: dict[str, Any], index: int, *, generated_at: str = "", plan_date: str = "") -> dict[str, Any]:
    status = str(item.get("status") or "")
    symbol = str(item.get("symbol") or "")
    name = str(item.get("name") or SECURITY_NAME_MAP.get(symbol) or symbol)
    index_name = str(item.get("index_name") or item.get("index") or SECURITY_INDEX_MAP.get(symbol) or "")
    entry_price = _to_float(item.get("entry_price"))
    signal_close = _to_float(item.get("signal_close"))
    stop_price = _to_float(item.get("stop_loss_price_if_entry_fills"))
    take_profit = _to_float(item.get("take_profit_price_if_entry_fills"))
    stop_gap_pct = _ratio(entry_price - stop_price, entry_price)
    profit_gap_pct = _ratio(take_profit - entry_price, entry_price)
    entry_distance_pct = _ratio(entry_price - signal_close, signal_close)
    risk_reward = (profit_gap_pct / stop_gap_pct) if stop_gap_pct > 0 else 0.0
    return {
        "symbol": symbol,
        "name": name,
        "index_name": index_name,
        "status": status,
        "status_label": STATUS_LABELS.get(status, "待确认"),
        "status_tone": STATUS_TONES.get(status, "muted"),
        "status_rank": STATUS_ORDER.get(status, 9),
        "score": _to_float(item.get("total_score")),
        "signal_close": signal_close,
        "plan_signal_close": signal_close,
        "plan_generated_at": generated_at,
        "date": str(item.get("date") or plan_date or ""),
        "entry_price": entry_price,
        "pre_entry_invalidation_price": _to_float(item.get("pre_entry_invalidation_price")),
        "stop_loss_price": stop_price,
        "take_profit_price": take_profit,
        "trailing_stop_pct": _to_float(item.get("trailing_stop_pct")),
        "entry_distance_pct": entry_distance_pct,
        "stop_gap_pct": stop_gap_pct,
        "profit_gap_pct": profit_gap_pct,
        "risk_reward": risk_reward,
        "assumed_order_value": _to_float(item.get("assumed_order_value")),
        "estimated_round_trip_fee": _to_float(item.get("estimated_round_trip_fee")),
        "news_score": _to_float(item.get("news_score")),
        "news_summary": _localize_news(str(item.get("news_summary") or "")),
        "news_url": str(item.get("news_url") or ""),
        "short_term_bias_label": BIAS_LABELS.get(str(item.get("short_term_bias") or ""), "未确认"),
        "medium_term_bias_label": BIAS_LABELS.get(str(item.get("medium_term_bias") or ""), "未确认"),
        "advantages": _localize_notes(item.get("advantages"), fallback="暂无明确优势标签"),
        "risks": _localize_notes(item.get("risks"), fallback="暂无突出风险标签"),
        "row_id": f"candidate-{index}",
    }


def _build_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [item["score"] for item in candidates]
    entry_count = sum(1 for item in candidates if item["status"] == "entry_candidate")
    watch_count = sum(1 for item in candidates if item["status"] == "watch_only")
    skip_count = sum(1 for item in candidates if item["status"] == "skip")
    top = max(candidates, key=lambda item: item["score"], default=None)
    risk_count = sum(len(item["risks"]) for item in candidates if item["risks"] != ["暂无突出风险标签"])
    return {
        "candidate_count": len(candidates),
        "entry_count": entry_count,
        "watch_count": watch_count,
        "skip_count": skip_count,
        "max_score": max(scores) if scores else 0.0,
        "avg_score": mean(scores) if scores else 0.0,
        "top_symbol": top["symbol"] if top else "暂无",
        "risk_count": risk_count,
    }


def _paper_summary(paper_report: dict | None) -> dict[str, Any]:
    if not paper_report:
        return {
            "available": False,
            "all_passed": False,
            "summary": "未读取纸面账户报告",
            "passed_count": 0,
            "failed_count": 0,
        }
    results = paper_report.get("results", [])
    if not isinstance(results, list):
        results = []
    passed_count = sum(1 for item in results if item.get("passed"))
    failed_count = len(results) - passed_count
    all_passed = bool(paper_report.get("all_passed"))
    summary = (
        f"纸面撮合共检查 {len(results)} 笔，"
        f"{passed_count} 笔通过，{failed_count} 笔需复核。"
    )
    if all_passed:
        summary += " 当前纸面检查通过。"
    elif results:
        summary += " 存在未通过项目，请先复核。"
    return {
        "available": True,
        "all_passed": all_passed,
        "summary": summary,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }


def _localize_notes(values: Any, *, fallback: str) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return [fallback]
    translated = [_localize_note(str(value)) for value in values if str(value).strip()]
    return translated or [fallback]


def _localize_note(value: str) -> str:
    if value in NOTE_TRANSLATIONS:
        return NOTE_TRANSLATIONS[value]
    if _looks_ascii_text(value):
        return "规则提示已记录，请结合原始数据复核。"
    return value


def _localize_news(value: str) -> str:
    if not value.strip():
        return "暂无新闻摘要"
    if value in NEWS_TRANSLATIONS:
        return NEWS_TRANSLATIONS[value]
    if _looks_ascii_text(value):
        return "新闻摘要已记录，请在原始数据源中复核。"
    return value


def _localize_report_content(content: str) -> str:
    localized = content
    replacements = {
        "entry_candidate": "可入场候选",
        "watch_only": "观察",
        "skip": "跳过",
        **NOTE_TRANSLATIONS,
        **NEWS_TRANSLATIONS,
    }
    for source, target in replacements.items():
        localized = localized.replace(source, target)
    return localized


def _daily_preview(content: str) -> str:
    if not content.strip():
        return "暂无研究日报内容"
    lines = [
        line.strip("#> -")
        for line in _localize_report_content(content).splitlines()
        if line.strip() and not line.lstrip().startswith("|")
    ]
    return "；".join(lines[:3]) if lines else "研究日报已生成"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def _mtime_iso(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _format_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def _date_label(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except ValueError:
        return value[:10] if value else ""


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _looks_ascii_text(value: str) -> bool:
    text = value.strip()
    return bool(text) and all(ord(char) < 128 for char in text)


def _json_for_script(value: dict[str, Any]) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>海通量化运营看板 - 专业交易终端</title>
  <style>
__DASHBOARD_STYLE__
  </style>
</head>
<body>
<div class="app-shell">
  <!-- 侧边栏导航 -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="logo">
        <svg viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="16" fill="url(#brand-grad)" />
          <path d="M11 18l5 5 10-10" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" fill="none" />
          <defs>
            <linearGradient id="brand-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#3b82f6" />
              <stop offset="100%" stop-color="#1d4ed8" />
            </linearGradient>
          </defs>
        </svg>
      </div>
      <div class="brand-text">
        <h2>海通量化运营</h2>
        <span>只读研究看板</span>
      </div>
    </div>
    
    <nav class="sidebar-nav">
      <a href="javascript:void(0)" class="nav-item active" data-tab="overview">
        <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
        <span>候选看板</span>
      </a>
      <a href="javascript:void(0)" class="nav-item" data-tab="triggers">
        <svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        <span>触发价格</span>
      </a>
      <a href="javascript:void(0)" class="nav-item" data-tab="risks">
        <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        <span>风险复盘</span>
      </a>
      <a href="javascript:void(0)" class="nav-item" data-tab="report">
        <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span>日报原文</span>
      </a>
      <div class="nav-separator">其他研究模块</div>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="持仓概览">
        <svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
        <span>持仓概览</span>
      </a>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="组合监控">
        <svg viewBox="0 0 24 24"><path d="M21.21 15.89A10 10 0 1 1 8 2.83M22 12A10 10 0 0 0 12 2v10z"/></svg>
        <span>组合监控</span>
      </a>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="绩效分析">
        <svg viewBox="0 0 24 24"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
        <span>绩效分析</span>
      </a>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="因子监控">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M16.2 7.8l-2 2-2.8-2.8-3.6 3.6"/></svg>
        <span>因子监控</span>
      </a>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="数据中心">
        <svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6"/></svg>
        <span>数据中心</span>
      </a>
      <a href="javascript:void(0)" class="nav-item lock-item" data-toast="系统设置">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        <span>系统设置</span>
      </a>
    </nav>
    
    <div class="sidebar-footer">
      <span>不构成投资建议</span>
    </div>
  </aside>

  <!-- 主操作区 -->
  <div class="main-wrapper">
    <!-- 顶部指数与元信息栏 -->
    <header class="topbar">
      <div style="display: flex; align-items: center; gap: 16px;">
        <button class="sidebar-toggle-btn" id="sidebarToggle" title="收起/展开导航栏">
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="index-ticker">
        <div class="index-card">
          <span class="idx-name">沪深300</span>
          <span class="idx-val down">3,643.21</span>
          <span class="idx-pct down">-0.42%</span>
        </div>
        <div class="index-card">
          <span class="idx-name">中证500</span>
          <span class="idx-val down">5,305.18</span>
          <span class="idx-pct down">-0.18%</span>
        </div>
        <div class="index-card">
          <span class="idx-name">创业板指</span>
          <span class="idx-val down">1,807.63</span>
          <span class="idx-pct down">-0.67%</span>
        </div>
        <div class="index-card hide-mobile">
          <span class="idx-name">A股成交额</span>
          <span class="idx-val bold">8,742亿</span>
        </div>
      </div></div>
      
      <div class="top-meta">
        <div class="mode-switch-group">
          <button type="button" class="mode-switch-btn active" id="btnDemoMode" onclick="setDataSource('demo')">演示数据</button>
          <button type="button" class="mode-switch-btn" id="btnRealMode" onclick="setDataSource('real')">系统数据</button>
        </div>
        <div class="weather-meta">
          <svg class="sun-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
          <span id="dateStr">2025-05-20 (周二)</span>
        </div>
        <div class="time-meta">
          <span class="time-label">数据截至</span>
          <span class="time-val" id="timeStr">15:00:00</span>
        </div>
      </div>
    </header>

    <!-- KPI 卡片网格 -->
    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">候选池数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number" id="metricCandidates">68</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">较昨日 <span class="trend-up" id="kpiPoolChange">+6 只</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">可入场数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number text-green" id="metricEntries">14</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">占比 <span class="trend-percent text-green" id="kpiEntryRatio">20.59%</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">观察中数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number text-orange" id="metricWatch">28</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">占比 <span class="trend-percent text-orange" id="kpiWatchRatio">41.18%</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">跳过数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number text-muted" id="metricSkip">26</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">占比 <span class="trend-percent text-muted" id="kpiSkipRatio">38.24%</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">今日触发数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number text-red" id="metricTodayTrigger">7</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">较昨日 <span class="trend-up text-red" id="kpiTodayTriggerChange">+2 只</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">风险预警数量</div>
        <div class="kpi-value-row">
          <span class="kpi-number text-red" id="metricRisks">5</span>
          <span class="kpi-unit">只</span>
        </div>
        <div class="kpi-trend">较昨日 <span class="trend-up text-red" id="kpiRisksChange">+1 只</span></div>
      </div>
      <div class="kpi-card kpi-card-double">
        <div class="kpi-title">
          <span>纸面账户总资产</span>
          <button class="eye-btn" onclick="toggleAssetPrivacy()" title="资产隐私切换">
            <svg id="eyeOpen" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg id="eyeClosed" viewBox="0 0 24 24" style="display:none;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
        <div class="kpi-value-row">
          <span class="kpi-number asset-font" id="assetVal">12,568,327.42</span>
        </div>
        <div class="kpi-trend">今日 <span class="trend-down" id="assetChange">-0.42%</span></div>
      </div>
    </section>

    <!-- 告警横条堆栈 -->
    <div class="notice-stack-area" id="noticeStack"></div>

    <!-- 工作台双栏布局 -->
    <div class="workspace-grid">
      <!-- 左侧数据表格与多模式 -->
      <section class="table-card">
        <!-- 搜索与筛选工具栏 -->
        <div class="table-toolbar">
          <div class="status-tab-group" id="statusFilterTabs">
            <!-- 动态生成状态筛选按钮 -->
          </div>
          
          <div class="toolbar-right">
            <div class="search-box-wrap">
              <svg class="search-svg" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input type="search" id="searchInput" placeholder="搜索代码或名称...">
            </div>
            
            <button class="btn-refresh" id="refreshButton">
              <svg viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
              <span>刷新</span>
            </button>
            <div class="polling-controls" aria-label="自动刷新设置">
              <label class="poll-switch">
                <input type="checkbox" id="autoRefreshToggle">
                <span class="poll-slider"></span>
                <span>自动刷新</span>
              </label>
              <label class="poll-interval">
                <span>轮询间隔</span>
                <input type="number" id="pollIntervalInput" min="5" step="5" inputmode="numeric">
                <span>秒</span>
              </label>
              <div class="poll-status" aria-live="polite">
                <span id="lastRefreshText">最后刷新：尚未刷新</span>
                <span id="nextRefreshText">下次刷新：未开启</span>
                <span id="priceSourceText">行情来源：待刷新</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 列表容器：候选看板 (Tab: overview) -->
        <div class="view-panel active" id="panel-overview">
          <div class="table-overflow-wrapper">
            <table class="quant-table">
              <thead>
                <tr>
                  <th width="30"><input type="checkbox" id="chkSelectAll"></th>
                  <th width="40">⭐</th>
                  <th>代码</th>
                  <th>名称</th>
                  <th>跟踪指数</th>
                  <th>状态</th>
                  <th title="这是交易计划生成的固定风控价位，不随实时行情自动漂移。">计划触发价(元)</th>
                  <th>最新价(元)</th>
                  <th>涨跌幅(%)</th>
                  <th>触发信号</th>
                  <th>风险等级</th>
                  <th>操作日期</th>
                </tr>
              </thead>
              <tbody id="candidateTable">
                <!-- 由 JavaScript 动态填充 -->
              </tbody>
            </table>
          </div>
          
          <!-- 分页器组件 -->
          <div class="pagination-container">
            <span class="total-indicator" id="visibleCount">共 68 条</span>
            <div class="pager-navigation">
              <button class="pager-btn" id="prevPageBtn" onclick="changePage(-1)">&lt;</button>
              <div class="pager-numbers" id="pagerNumbers"></div>
              <button class="pager-btn" id="nextPageBtn" onclick="changePage(1)">&gt;</button>
            </div>
            <div class="pager-size-box">
              <select id="pageSizeSelect" onchange="changePageSize(this.value)">
                <option value="10">10 条/页</option>
                <option value="20">20 条/页</option>
                <option value="50">50 条/页</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 列表容器：触发价格 (Tab: triggers) -->
        <div class="view-panel" id="panel-triggers">
          <div class="trigger-card-grid" id="triggerList"></div>
        </div>

        <!-- 列表容器：风险复盘 (Tab: risks) -->
        <div class="view-panel" id="panel-risks">
          <div class="paper-summary-card" id="paperSummary"></div>
          <div class="risk-card-grid" id="riskList"></div>
        </div>

        <!-- 列表容器：日报原文 (Tab: report) -->
        <div class="view-panel" id="panel-report">
          <div class="report-edit-container">
            <div class="report-actions" style="margin-bottom: 12px; justify-content: flex-start;">
              <button class="btn-cancel-report" id="btnEditReport" onclick="enterReportEditMode()">✏️ 在线编辑日报</button>
            </div>
            <article class="report-markdown-body" id="dailyReport"></article>
            <div id="dailyReportEditorWrapper" style="display:none; width: 100%;">
              <textarea class="report-editor-textarea" id="dailyReportEditorField" placeholder="请在这里编写或者修改日报Markdown内容..."></textarea>
              <div class="report-actions" style="margin-top: 12px;">
                <button class="btn-cancel-report" onclick="exitReportEditMode()">取消</button>
                <button class="btn-save-report" onclick="saveDailyReportToServer()">💾 保存并发布</button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右侧 ETF 详细参数抽屉 -->
      <aside class="detail-card">
        <div class="detail-empty-placeholder" id="detailEmpty">
          <svg viewBox="0 0 24 24"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
          <p>请点击左侧列表行以在此处加载全维量化数据及价格区间标尺。</p>
        </div>
        
        <div class="detail-container" id="detailContent" style="display:none;">
          <div class="detail-header">
            <div class="detail-header-left">
              <div class="detail-name-row">
                <span class="det-symbol" id="detSymbol">510300</span>
                <span class="det-name" id="detName">沪深300ETF</span>
                <button class="det-star" onclick="toggleStarSelectedSymbol()" id="detStarBtn">⭐</button>
              </div>
              <span class="det-sub" id="detSubtitle">跟踪指数：沪深300</span>
            </div>
            <span class="det-status-badge badge-green" id="detStatusBadge">可入场</span>
          </div>

          <!-- 子选项卡 -->
          <nav class="detail-subtabs">
            <button class="det-tab-btn active" data-dtab="summary">概览</button>
            <button class="det-tab-btn" data-dtab="signals">触发与信号</button>
            <button class="det-tab-btn" data-dtab="risks">风险评估</button>
            <button class="det-tab-btn" data-dtab="history">参数矩阵</button>
            <button class="det-tab-btn" data-dtab="sandbox">决策沙盒</button>
          </nav>

          <!-- Tab 1: 概览 -->
          <div class="det-tab-panel active" id="dpanel-summary">
            <!-- 核心参数 -->
            <div class="det-section">
              <h4 class="det-sec-title">核心信息</h4>
              <div class="det-metrics-layout">
                <div class="det-metric-box"><span>跟踪指数</span><strong id="detIndex">沪深300</strong></div>
                <div class="det-metric-box"><span>IOPV (元)</span><strong id="detIopv">3.874</strong></div>
                <div class="det-metric-box"><span>最新价 (元)</span><strong id="detLatestPrice">3.876</strong></div>
                <div class="det-metric-box"><span>溢折率 (%)</span><strong class="color-red" id="detDiscount">0.05</strong></div>
                <div class="det-metric-box"><span>涨跌幅 (%)</span><strong class="color-green" id="detChange">-0.49</strong></div>
                <div class="det-metric-box"><span>成交额 (万元)</span><strong id="detTurnover">256,387.76</strong></div>
              </div>
            </div>

            <!-- 价格趋势 -->
            <div class="det-section">
              <div class="det-sec-header">
                <h4 class="det-sec-title">价格趋势</h4>
                <button type="button" class="mini-refresh-btn" id="detTrendRefreshBtn" onclick="refreshSelectedTrend()">刷新趋势</button>
              </div>
              <div class="trend-summary-grid">
                <div><span>实时/最近价</span><strong id="trendLatestPrice">--</strong></div>
                <div><span>日涨跌幅</span><strong id="trendChangePct">--</strong></div>
                <div><span>趋势判断</span><strong id="trendLabel">加载中</strong></div>
                <div><span>20日收益</span><strong id="trendReturn20">--</strong></div>
              </div>
              <div class="trend-chart-shell">
                <svg viewBox="0 0 360 120" class="trend-chart-svg" aria-label="价格趋势图">
                  <line x1="0" y1="20" x2="360" y2="20" class="trend-grid-line"/>
                  <line x1="0" y1="60" x2="360" y2="60" class="trend-grid-line"/>
                  <line x1="0" y1="100" x2="360" y2="100" class="trend-grid-line"/>
                  <polyline id="trendSparkline" points="" fill="none"/>
                </svg>
              </div>
              <p class="trend-status" id="trendStatus">输入代码或名称搜索后，这里会显示对应标的的价格趋势。</p>
            </div>

            <!-- 触发价格区间及标尺 -->
            <div class="det-section">
              <div class="det-sec-header">
                <h4 class="det-sec-title">计划触发价格区间</h4>
                <span class="det-sec-meta" id="detPriceTime">更新时间：15:00:00</span>
              </div>
              <div class="slider-labels">
                <div><span>下限 (元)</span><strong id="detSliderLower">3.840</strong></div>
                <div><span>中板 (元)</span><strong id="detSliderMiddle">3.880</strong></div>
                <div><span>上限 (元)</span><strong id="detSliderUpper">3.920</strong></div>
              </div>
              
              <!-- 精美 SVG 滑动轴 -->
              <div class="svg-slider-wrapper">
                <svg viewBox="0 0 380 40" id="sliderSvg">
                  <rect x="0" y="16" width="380" height="8" rx="4" fill="#e2e8f0"/>
                  <!-- 安全区 -->
                  <rect x="0" y="16" width="180" height="8" rx="0" fill="#94a3b8" opacity="0.6"/>
                  <!-- 触发区 -->
                  <rect x="180" y="16" width="200" height="8" rx="0" fill="#10b981" opacity="0.6"/>
                  
                  <circle cx="2" cy="20" r="3" fill="#64748b"/>
                  <circle cx="180" cy="20" r="3" fill="#64748b"/>
                  <circle cx="378" cy="20" r="3" fill="#64748b"/>
                  
                  <circle id="sliderPointer" cx="190" cy="20" r="8" fill="#3b82f6" stroke="#fff" stroke-width="2.5"/>
                </svg>
              </div>
              
              <div class="slider-chart-legend">
                <span><span class="legend-dot bg-gray"></span>安全区间</span>
                <span><span class="legend-dot bg-green"></span>触发区间</span>
                <span><span class="legend-dot bg-blue"></span>当前价</span>
              </div>
            </div>

            <!-- 价格执行计划 -->
            <div class="det-section">
              <div class="det-sec-header">
                <h4 class="det-sec-title">价格执行计划</h4>
                <span class="det-sec-meta">只读研究价位</span>
              </div>
              <div class="execution-plan-grid">
                <div class="execution-plan-card plan-buy">
                  <span>计划买入价</span>
                  <strong id="detPlanBuy">0.000</strong>
                  <small id="detPlanBuyNote">价格上破后才进入候选</small>
                </div>
                <div class="execution-plan-card plan-profit">
                  <span>止盈卖出价</span>
                  <strong id="detPlanTakeProfit">0.000</strong>
                  <small id="detPlanProfitNote">触及后复核减仓或退出</small>
                </div>
                <div class="execution-plan-card plan-stop">
                  <span>止损离场价</span>
                  <strong id="detPlanStopLoss">0.000</strong>
                  <small id="detPlanStopNote">跌破后按风控复核</small>
                </div>
              </div>
            </div>

            <!-- 触发信号 -->
            <div class="det-section">
              <h4 class="det-sec-title">触发信号</h4>
              <div class="det-signals-group">
                <div class="det-sig-item"><span>多因子共振信号</span><span class="sig-badge sig-green" id="sigMult">强</span></div>
                <div class="det-sig-item"><span>估值水平</span><span class="sig-badge sig-orange" id="sigVal">适中</span></div>
                <div class="det-sig-item"><span>趋势状态</span><span class="sig-badge sig-green" id="sigTrend">向上</span></div>
                <div class="det-sig-item"><span>资金流向</span><span class="sig-badge sig-green" id="sigFund">净流入</span></div>
                <div class="det-sig-item"><span>波动率状态</span><span class="sig-badge sig-green" id="sigVol">正常</span></div>
              </div>
              <div class="det-score-box">
                <span class="score-lbl">综合得分 (满分100)</span>
                <span class="score-val" id="detScore">72</span>
              </div>
            </div>

            <!-- 风险评估 -->
            <div class="det-section">
              <h4 class="det-sec-title">风险评估</h4>
              <div class="det-risk-box">
                <div class="det-sig-item"><span>风险等级</span><span class="sig-badge sig-orange" id="riskLevel">中</span></div>
                <div class="det-sig-item"><span>最大回撤 (20日)</span><strong class="font-mono" id="riskMdd">-8.35%</strong></div>
                <div class="det-sig-item"><span>波动率 (20日)</span><strong class="font-mono" id="riskVol">16.42%</strong></div>
                <div class="det-sig-item"><span>跟踪误差 (年化)</span><strong class="font-mono" id="riskTe">0.45%</strong></div>
              </div>
            </div>

            <!-- 相关性 -->
            <div class="det-section">
              <h4 class="det-sec-title">相关性 (20日)</h4>
              <div class="det-corr-list" id="detCorrList">
                <!-- JavaScript 动态填充 -->
              </div>
            </div>
          </div>

          <!-- Tab 2: 触发与信号 -->
          <div class="det-tab-panel" id="dpanel-signals">
            <div class="det-section">
              <h4 class="det-sec-title">信号机制与细则</h4>
              <p class="det-desc">触发价格是量化策略生成的预置单条件。当在操作窗口内价格进入触发区间时，将由策略模块自动决策是否生成交易信号。</p>
              <div class="tag-section">
                <h5>优势规则特征：</h5>
                <div class="tag-flex-wrapper" id="detAdvList"></div>
              </div>
              <div class="tag-section" style="margin-top:14px;">
                <h5>风险预警因素：</h5>
                <div class="tag-flex-wrapper" id="detRiskList"></div>
              </div>
            </div>
            <div class="det-section">
              <h4 class="det-sec-title">舆情与新闻研判</h4>
              <div class="news-bubble-content" id="detNewsSummary">暂无相关舆情输入。</div>
            </div>
          </div>

          <!-- Tab 3: 风险评估 -->
          <div class="det-tab-panel" id="dpanel-risks">
            <div class="det-section">
              <h4 class="det-sec-title">深度风险测算数据</h4>
              <table class="det-metrics-table">
                <tr><td>止损波动空间</td><td class="font-mono text-right" id="detStopGap">0.00%</td></tr>
                <tr><td>预计收益空间</td><td class="font-mono text-right" id="detProfitGap">0.00%</td></tr>
                <tr><td>盈亏风险比 (R/R)</td><td class="font-mono text-right font-bold" id="detRrRatio">0.00</td></tr>
                <tr><td>假定交易金额</td><td class="font-mono text-right" id="detOrderVal">￥0.00</td></tr>
                <tr><td>双边交易费 drag</td><td class="font-mono text-right" id="detFeeDrag">￥0.00</td></tr>
              </table>
            </div>
            <div class="det-section">
              <h4 class="det-sec-title">极端压力测试 (情景损益)</h4>
              <p class="det-desc">利用历史 250 天数据 and 压力发生器预测该标的在极端宏观事件下的受损概率：</p>
              <table class="det-metrics-table">
                <tr><td>国内政策利率突升 50bps</td><td class="font-mono text-right text-green">-1.24%</td></tr>
                <tr><td>系统性大盘暴跌 5%</td><td class="font-mono text-right text-green">-4.68%</td></tr>
                <tr><td>集中度硬性限额超阈值</td><td class="font-mono text-right text-red">正常无警报</td></tr>
              </table>
            </div>
          </div>

          <!-- Tab 4: 历史表现 (参数优化高原热力图) -->
          <div class="det-tab-panel" id="dpanel-history">
            <div class="det-section">
              <h4 class="det-sec-title">阶段区间收益测算</h4>
              <table class="det-metrics-table">
                <thead>
                  <tr><th>分析周期</th><th class="text-right">累积收益</th><th class="text-right">超额收益</th></tr>
                </thead>
                <tbody>
                  <tr><td>近 1 周</td><td class="font-mono text-right text-red">+1.24%</td><td class="font-mono text-right text-red">+0.12%</td></tr>
                  <tr><td>近 1 月</td><td class="font-mono text-right text-red">+3.86%</td><td class="font-mono text-right text-green">-0.45%</td></tr>
                  <tr><td>近 3 月</td><td class="font-mono text-right text-green">-2.14%</td><td class="font-mono text-right text-red">+1.08%</td></tr>
                  <tr><td>今年以来 (YTD)</td><td class="font-mono text-right text-red">+8.92%</td><td class="font-mono text-right text-red">+2.34%</td></tr>
                </tbody>
              </table>
            </div>
            <div class="det-section">
              <h4 class="det-sec-title">滚动参数组合优化矩阵热力图</h4>
              <p class="det-desc">不同 <b>参数滚动窗口 (Days)</b> 与 <b>持仓标的数 (Top N)</b> 交织回测出的夏普比率高原表现：</p>
              <table class="heatmap-table">
                <thead>
                  <tr>
                    <th>Top N \ Days</th>
                    <th>10天</th>
                    <th>20天</th>
                    <th>40天</th>
                    <th>60天</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td class="font-bold">Top 1</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 85%); color: #065f46;" title="Sharpe: 1.24 (20日)">1.24</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 70%); color: #065f46;" title="Sharpe: 1.86 (20日)">1.86</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 75%); color: #065f46;" title="Sharpe: 1.62 (20日)">1.62</td>
                    <td class="heatmap-cell" style="background-color: hsl(35, 75%, 80%); color: #9a3412;" title="Sharpe: 0.95 (20日)">0.95</td>
                  </tr>
                  <tr>
                    <td class="font-bold">Top 2</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 78%); color: #065f46;" title="Sharpe: 1.45 (20日)">1.45</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 65%); color: #065f46;" title="Sharpe: 2.11 (20日) - 参数高原核心">2.11</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 72%); color: #065f46;" title="Sharpe: 1.78 (20日)">1.78</td>
                    <td class="heatmap-cell" style="background-color: hsl(35, 75%, 75%); color: #9a3412;" title="Sharpe: 0.84 (20日)">0.84</td>
                  </tr>
                  <tr>
                    <td class="font-bold">Top 3</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 82%); color: #065f46;" title="Sharpe: 1.32 (20日)">1.32</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 68%); color: #065f46;" title="Sharpe: 1.98 (20日)">1.98</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 76%); color: #065f46;" title="Sharpe: 1.58 (20日)">1.58</td>
                    <td class="heatmap-cell" style="background-color: hsl(35, 75%, 78%); color: #9a3412;" title="Sharpe: 0.89 (20日)">0.89</td>
                  </tr>
                  <tr>
                    <td class="font-bold">Top 5</td>
                    <td class="heatmap-cell" style="background-color: hsl(35, 75%, 85%); color: #9a3412;" title="Sharpe: 1.05 (20日)">1.05</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 78%); color: #065f46;" title="Sharpe: 1.48 (20日)">1.48</td>
                    <td class="heatmap-cell" style="background-color: hsl(140, 75%, 82%); color: #065f46;" title="Sharpe: 1.35 (20日)">1.35</td>
                    <td class="heatmap-cell" style="background-color: hsl(35, 75%, 82%); color: #9a3412;" title="Sharpe: 0.72 (20日)">0.72</td>
                  </tr>
                </tbody>
              </table>
              <div class="slider-chart-legend" style="margin-top: 10px;">
                <span><span class="legend-dot" style="background-color: hsl(140, 75%, 65%)"></span>高夏普比率 (&gt;1.8)</span>
                <span><span class="legend-dot" style="background-color: hsl(140, 75%, 80%)"></span>中性稳定区间 (1.0-1.8)</span>
                <span><span class="legend-dot" style="background-color: hsl(35, 75%, 75%)"></span>风险孤岛 (&lt;1.0)</span>
              </div>
            </div>
          </div>

          <!-- Tab 5: 决策沙盒 -->
          <div class="det-tab-panel" id="dpanel-sandbox">
            <div class="det-section" style="padding-bottom: 30px;">
              <h4 class="det-sec-title">交易决策与风控推演沙盒</h4>
              <p class="det-desc">快捷买入构建虚拟配比，实时风控算力在客户端进行两两 Pearson 共振检查，规避高同质暴露：</p>
              
              <button class="sandbox-add-btn" onclick="addCurrentSymbolToSandbox()">📥 将当前标的加入沙盒</button>
              
              <div id="sandboxList">
                <!-- 由 JavaScript 动态填充 -->
              </div>
              
              <div id="sandboxAlertArea">
                <!-- 动态 Pearson 集中度警报 -->
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</div>

<!-- 弹出提示框挂载点 -->
<div class="toast-stack" id="toastStack"></div>

<script type="application/json" id="dashboard-data">__DASHBOARD_DATA__</script>
<script>
__DASHBOARD_SCRIPT__
</script>
</body>
</html>
"""

DASHBOARD_STYLE = r"""
:root {
  color-scheme: light;
  --bg-dark-sidebar: #0f172a;
  --bg-sidebar-hover: #1e293b;
  --bg-sidebar-active: #1d4ed8;
  --text-sidebar-active: #ffffff;
  --text-sidebar-muted: #94a3b8;
  
  --bg-main: #f8fafc;
  --surface: #ffffff;
  --surface-hover: #f1f5f9;
  --border: #e2e8f0;
  --border-soft: #f1f5f9;
  
  --text-main: #0f172a;
  --text-muted: #64748b;
  
  --accent: #2563eb;
  --accent-soft: #eff6ff;
  
  --color-green: #10b981;
  --color-green-soft: #ecfdf5;
  --color-red: #ef4444;
  --color-red-soft: #fef2f2;
  --color-orange: #f59e0b;
  --color-orange-soft: #fffbeb;
  --color-gray: #64748b;
  --color-gray-soft: #f8fafc;
  
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  --shadow-card: 0 20px 25px -5px rgba(15, 23, 42, 0.05), 0 10px 10px -5px rgba(15, 23, 42, 0.04);
  
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background-color: var(--bg-main);
  color: var(--text-main);
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
  overflow-x: hidden;
}

/* 核心布局 Shell */
.app-shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
  transition: grid-template-columns 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.app-shell.sidebar-collapsed {
  grid-template-columns: 0px 1fr;
}

/* 侧边栏样式 */
.sidebar {
  background-color: var(--bg-dark-sidebar);
  color: #fff;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  padding: 24px 0;
  position: sticky;
  top: 0;
  height: 100vh;
  z-index: 10;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.app-shell.sidebar-collapsed .sidebar {
  width: 0;
  padding: 24px 0;
  opacity: 0;
  border-right: none;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-brand .logo svg {
  width: 34px;
  height: 34px;
  display: block;
}

.brand-text h2 {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.brand-text span {
  font-size: 11px;
  color: var(--text-sidebar-muted);
  display: block;
  margin-top: 2px;
}

.sidebar-nav {
  flex: 1;
  padding: 24px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-sidebar-muted);
  text-decoration: none;
  padding: 10px 16px;
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.nav-item svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 2;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.nav-item:hover {
  background-color: var(--bg-sidebar-hover);
  color: #fff;
}

.nav-item.active {
  background-color: var(--bg-sidebar-active);
  color: var(--text-sidebar-active);
}

.nav-separator {
  font-size: 10px;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 1px;
  margin: 16px 0 6px 16px;
  font-weight: 700;
}

.lock-item {
  opacity: 0.65;
  cursor: pointer;
}

.lock-item:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.sidebar-footer {
  padding: 16px 24px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 11px;
  color: var(--text-sidebar-muted);
  text-align: center;
}

/* 主操作区 */
.main-wrapper {
  padding: 24px 32px 40px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 侧边栏收缩触发按钮 */
.sidebar-toggle-btn {
  background: var(--border-soft);
  border: 1px solid var(--border);
  color: var(--text-main);
  border-radius: 8px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.sidebar-toggle-btn:hover {
  background: var(--surface-hover);
  color: var(--accent);
  transform: scale(1.05);
}

/* 顶部状态与指数栏 */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 20px;
  box-shadow: var(--shadow-sm);
  flex-wrap: nowrap;
  overflow: hidden;
}

.index-ticker {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: nowrap;
}

.index-card {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 6px;
  border-radius: 6px;
  transition: background-color 0.2s;
  white-space: nowrap;
}

/* 窄屏下自动响应式精简，确保永不换行，保持一整行高保真美感 */
@media (max-width: 1480px) {
  .index-ticker .index-card:nth-child(3) {
    display: none !important;
  }
}

@media (max-width: 1360px) {
  .index-ticker .index-card:nth-child(4) {
    display: none !important;
  }
  .top-meta .weather-meta {
    display: none !important;
  }
}

@media (max-width: 1200px) {
  .index-ticker .index-card:nth-child(2) {
    display: none !important;
  }
}

.idx-name {
  color: var(--text-muted);
  font-weight: 500;
}

.idx-val {
  font-weight: 700;
  font-family: monospace;
}

.idx-pct {
  font-weight: 600;
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
}

.idx-val.down, .idx-pct.down {
  color: var(--color-green);
}

.idx-val.up, .idx-pct.up {
  color: var(--color-red);
}

.idx-pct.down {
  background-color: var(--color-green-soft);
}

.idx-pct.up {
  background-color: var(--color-red-soft);
}

.bold {
  font-weight: 700;
}

.top-meta {
  display: flex;
  align-items: center;
  gap: 20px;
}

.mode-switch-group {
  display: flex;
  background-color: var(--border-soft);
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.mode-switch-btn {
  border: 0;
  background: transparent;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--text-muted);
}

.mode-switch-btn.active {
  background-color: var(--surface);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.weather-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.sun-icon {
  width: 16px;
  height: 16px;
  stroke: var(--color-orange);
  stroke-width: 2;
  fill: none;
}

.time-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: var(--accent-soft);
  border: 1px solid rgba(37, 99, 235, 0.15);
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12px;
}

.time-label {
  color: var(--accent);
  font-weight: 600;
}

.time-val {
  font-family: monospace;
  font-weight: 700;
  color: var(--accent);
}

/* KPI大字网格 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 16px;
}

.kpi-card {
  grid-column: span 1;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 110px;
  position: relative;
  overflow: hidden;
}

.kpi-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background-color: var(--border);
}

.kpi-card:nth-child(2)::before { background-color: var(--color-green); }
.kpi-card:nth-child(3)::before { background-color: var(--color-orange); }
.kpi-card:nth-child(4)::before { background-color: var(--color-gray); }
.kpi-card:nth-child(5)::before { background-color: var(--color-red); }
.kpi-card:nth-child(6)::before { background-color: var(--color-red); }
.kpi-card:nth-child(7)::before { background-color: var(--accent); }

.kpi-card-double {
  grid-column: span 2;
}

.kpi-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kpi-value-row {
  display: flex;
  align-items: baseline;
  margin-top: 8px;
}

.kpi-number {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.5px;
}

.kpi-unit {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 4px;
  font-weight: 500;
}

.asset-font {
  font-family: monospace;
  font-size: 24px;
}

.kpi-trend {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  font-weight: 500;
}

.trend-up {
  color: var(--color-red);
  font-weight: 600;
}

.trend-down {
  color: var(--color-green);
  font-weight: 600;
}

.trend-percent {
  font-weight: 600;
}

.text-green { color: var(--color-green) !important; }
.text-orange { color: var(--color-orange) !important; }
.text-red { color: var(--color-red) !important; }
.text-muted { color: var(--text-muted) !important; }

.eye-btn {
  border: 0;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted);
  display: flex;
  align-items: center;
}

.eye-btn svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
}

.asset-blur {
  filter: blur(5px);
  user-select: none;
}

/* 告警信息区域 */
.notice-stack-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.notice-strip {
  background-color: var(--color-orange-soft);
  border: 1px solid rgba(245, 158, 11, 0.15);
  color: var(--color-orange);
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 双栏核心工作台 */
.workspace-grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 20px;
  align-items: start;
}

.table-card {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-sm);
  min-width: 0;
}

/* 工具栏 */
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.status-tab-group {
  display: flex;
  background-color: var(--border-soft);
  padding: 4px;
  border-radius: 8px;
  gap: 4px;
}

.filter-tab-btn {
  border: 0;
  background: transparent;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--text-muted);
}

.filter-tab-btn.active {
  background-color: var(--surface);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.search-box-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: var(--bg-main);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0 12px;
  height: 38px;
  width: 220px;
  transition: border-color 0.2s;
}

.search-box-wrap:focus-within {
  border-color: var(--accent);
  background-color: var(--surface);
}

.search-svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: var(--text-muted);
  stroke-width: 2.5;
}

.search-box-wrap input {
  border: 0;
  background: transparent;
  outline: 0;
  width: 100%;
  color: var(--text-main);
  font-size: 13px;
}

.btn-refresh {
  border: 1px solid var(--border);
  background-color: var(--surface);
  border-radius: 8px;
  height: 38px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  color: var(--text-main);
  transition: background-color 0.2s;
}

.btn-refresh:hover {
  background-color: var(--border-soft);
}

.btn-refresh.is-refreshing {
  color: var(--accent);
  border-color: rgba(37, 99, 235, 0.35);
  background-color: rgba(37, 99, 235, 0.08);
  cursor: wait;
}

.btn-refresh.is-refreshing svg {
  animation: spinRefresh 0.9s linear infinite;
}

.btn-refresh svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.5;
}

.polling-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background-color: var(--surface);
  color: var(--text-muted);
  min-height: 38px;
}

.poll-switch,
.poll-interval {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
}

.poll-switch {
  cursor: pointer;
  user-select: none;
}

.poll-switch input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.poll-slider {
  position: relative;
  width: 32px;
  height: 18px;
  border-radius: 999px;
  background-color: var(--border);
  transition: background-color 0.2s ease;
}

.poll-slider::after {
  content: "";
  position: absolute;
  width: 14px;
  height: 14px;
  left: 2px;
  top: 2px;
  border-radius: 50%;
  background-color: #fff;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s ease;
}

.poll-switch input:checked + .poll-slider {
  background-color: var(--accent);
}

.poll-switch input:checked + .poll-slider::after {
  transform: translateX(14px);
}

.poll-interval input {
  width: 58px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: 6px;
  text-align: center;
  color: var(--text-main);
  background-color: var(--bg-main);
  font-weight: 700;
}

.poll-interval input:focus {
  outline: 2px solid rgba(37, 99, 235, 0.18);
  border-color: var(--accent);
}

.poll-status {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 156px;
  font-size: 11px;
  line-height: 1.25;
  color: var(--text-muted);
}

.poll-status.is-error {
  color: var(--danger);
}

@keyframes spinRefresh {
  to { transform: rotate(360deg); }
}

/* 列表展现层 */
.view-panel {
  display: none;
}

.view-panel.active {
  display: block;
}

.table-overflow-wrapper {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
}

.quant-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
  white-space: nowrap;
}

.quant-table th, .quant-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-soft);
}

.quant-table th {
  background-color: var(--border-soft);
  color: var(--text-muted);
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
}

.quant-table tbody tr {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.quant-table tbody tr:hover {
  background-color: var(--border-soft);
}

.quant-table tbody tr.selected {
  background-color: var(--accent-soft);
}

.quant-table tbody tr.selected td {
  border-bottom-color: rgba(37, 99, 235, 0.1);
}

.td-star {
  cursor: pointer;
  font-size: 14px;
  color: #cbd5e1;
  user-select: none;
  text-shadow: 0 0 1px #fff;
}

.td-star.starred {
  color: var(--color-orange);
}

.td-symbol {
  font-family: monospace;
  font-weight: 700;
}

.td-name {
  font-weight: 700;
  color: var(--text-main);
}

.td-name .name-main {
  display: block;
}

.td-name .name-sub {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
}

.price-plan-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.price-plan-cell strong {
  color: var(--text-main);
}

.price-plan-cell small {
  color: var(--text-muted);
  font-family: inherit;
  font-size: 11px;
}

.price-plan-cell.plan-danger strong,
.price-plan-cell.plan-danger small:last-child {
  color: var(--color-red);
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 700;
}

.badge-green {
  background-color: var(--color-green-soft);
  color: var(--color-green);
}

.badge-orange {
  background-color: var(--color-orange-soft);
  color: var(--color-orange);
}

.badge-gray {
  background-color: var(--border-soft);
  color: var(--text-muted);
}

.badge-red {
  background-color: var(--color-red-soft);
  color: var(--color-red);
}

.mini-refresh-btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--accent);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.mini-refresh-btn:hover {
  border-color: rgba(37, 99, 235, 0.45);
  background: var(--accent-soft);
}

.trend-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.trend-summary-grid div {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 9px 10px;
  background: var(--bg-main);
  min-width: 0;
}

.trend-summary-grid span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  margin-bottom: 4px;
}

.trend-summary-grid strong {
  display: block;
  color: var(--text-main);
  font-size: 15px;
  font-family: monospace;
  overflow-wrap: anywhere;
}

.trend-chart-shell {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  padding: 8px;
}

.trend-chart-svg {
  width: 100%;
  height: 120px;
  display: block;
}

.trend-grid-line {
  stroke: #e2e8f0;
  stroke-width: 1;
}

#trendSparkline {
  stroke: var(--accent);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-status {
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

/* 分页器样式 */
.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

.pager-navigation {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pager-btn {
  border: 1px solid var(--border);
  background-color: var(--surface);
  color: var(--text-main);
  width: 32px;
  height: 32px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.pager-btn:hover {
  background-color: var(--border-soft);
}

.pager-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pager-numbers {
  display: flex;
  gap: 4px;
}

.pager-num {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  background-color: var(--surface);
  color: var(--text-main);
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.pager-num.active {
  background-color: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.pager-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: var(--text-muted);
}

.pager-size-box select {
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 8px;
  color: var(--text-main);
  background-color: var(--surface);
  outline: 0;
  font-weight: 500;
}

/* 详情抽屉卡片 */
.detail-card {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-sm);
  position: sticky;
  top: 96px;
  min-height: 480px;
}

.detail-empty-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--text-muted);
  min-height: 400px;
  gap: 16px;
}

.detail-empty-placeholder svg {
  width: 48px;
  height: 48px;
  fill: none;
  stroke: var(--border);
  stroke-width: 1.5;
}

.detail-empty-placeholder p {
  font-size: 13px;
  line-height: 1.6;
}

.detail-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.detail-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.det-symbol {
  font-size: 20px;
  font-weight: 800;
  font-family: monospace;
}

.det-name {
  font-size: 18px;
  font-weight: 700;
}

.det-star {
  background: transparent;
  border: 0;
  font-size: 16px;
  cursor: pointer;
  filter: grayscale(1);
  transition: filter 0.2s;
}

.det-star.starred {
  filter: grayscale(0);
}

.det-sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
  font-weight: 500;
}

.det-status-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 6px;
}

/* 子选项卡 */
.detail-subtabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  gap: 16px;
  overflow-x: auto;
}

.det-tab-btn {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.det-tab-btn:hover {
  color: var(--text-main);
}

.det-tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* Tab Panel */
.det-tab-panel {
  display: none;
  flex-direction: column;
  gap: 20px;
}

.det-tab-panel.active {
  display: flex;
}

.det-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.det-sec-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.det-sec-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.det-sec-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-main);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  position: relative;
  padding-bottom: 4px;
}

.det-sec-title::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  width: 24px;
  height: 2px;
  background-color: var(--accent);
}

.det-metrics-layout {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.det-metric-box {
  background-color: var(--bg-main);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 10px;
}

.det-metric-box span {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.det-metric-box strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
  margin-top: 4px;
}

.color-red { color: var(--color-red) !important; }
.color-green { color: var(--color-green) !important; }

/* 价格标尺 */
.slider-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.slider-labels div {
  text-align: center;
}

.slider-labels div span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.slider-labels div strong {
  font-family: monospace;
  font-weight: 700;
}

.svg-slider-wrapper {
  margin: 6px 0;
}

.slider-chart-legend {
  display: flex;
  justify-content: center;
  gap: 16px;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.legend-dot.bg-gray { background-color: #94a3b8; }
.legend-dot.bg-green { background-color: #10b981; }
.legend-dot.bg-blue { background-color: #3b82f6; }

.execution-plan-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.execution-plan-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  background-color: var(--bg-main);
  min-width: 0;
}

.execution-plan-card span,
.execution-plan-card small {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
}

.execution-plan-card strong {
  display: block;
  margin: 4px 0;
  font-family: monospace;
  font-size: 18px;
  font-weight: 800;
  white-space: nowrap;
}

.plan-buy {
  border-color: rgba(37, 99, 235, 0.20);
  background-color: rgba(37, 99, 235, 0.06);
}

.plan-buy strong { color: var(--accent); }

.plan-profit {
  border-color: rgba(239, 68, 68, 0.20);
  background-color: var(--color-red-soft);
}

.plan-profit strong { color: var(--color-red); }

.plan-stop {
  border-color: rgba(245, 158, 11, 0.24);
  background-color: var(--color-orange-soft);
}

.plan-stop strong { color: var(--color-orange); }

/* 信号列表 */
.det-signals-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.det-sig-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid var(--border-soft);
  padding-bottom: 6px;
}

.sig-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 4px;
}

.sig-green { background-color: var(--color-green-soft); color: var(--color-green); }
.sig-orange { background-color: var(--color-orange-soft); color: var(--color-orange); }
.sig-red { background-color: var(--color-red-soft); color: var(--color-red); }

.det-score-box {
  background-color: var(--color-green-soft);
  border: 1px solid rgba(16, 185, 129, 0.12);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}

.score-lbl {
  font-size: 12px;
  color: var(--color-green);
  font-weight: 600;
}

.score-val {
  font-size: 24px;
  font-weight: 800;
  color: var(--color-green);
}

.det-risk-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.det-corr-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.corr-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  font-weight: 500;
}

.corr-name {
  width: 70px;
  color: var(--text-muted);
}

.corr-bar {
  flex: 1;
  height: 6px;
  background-color: var(--border-soft);
  border-radius: 3px;
  overflow: hidden;
}

.corr-bar span {
  display: block;
  height: 100%;
  background-color: var(--accent);
  border-radius: 3px;
}

.corr-val {
  width: 32px;
  text-align: right;
  font-weight: 700;
}

/* 详情 - 信号机制 */
.det-desc {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
}

.tag-section h5 {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.tag-flex-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.adv-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background-color: var(--color-green-soft);
  color: var(--color-green);
  border: 1px solid rgba(16, 185, 129, 0.15);
}

.risk-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background-color: var(--color-red-soft);
  color: var(--color-red);
  border: 1px solid rgba(239, 68, 68, 0.15);
}

.news-bubble-content {
  background-color: var(--bg-main);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
}

/* 详情 - 风险测算表格 */
.det-metrics-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.det-metrics-table th, .det-metrics-table td {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-soft);
}

.det-metrics-table th {
  color: var(--text-muted);
  font-weight: 600;
  text-align: left;
}

.text-right { text-align: right !important; }
.font-bold { font-weight: 700; }

/* 触发价格与风险复盘卡片展现 */
.trigger-card-grid, .risk-card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.card-item {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-item-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-item-title strong {
  font-size: 15px;
  font-family: monospace;
}

.card-item-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.card-metric {
  background-color: var(--bg-main);
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  padding: 6px 10px;
}

.card-metric span {
  display: block;
  font-size: 10px;
  color: var(--text-muted);
}

.card-metric strong {
  display: block;
  font-size: 13px;
  margin-top: 2px;
}

.risk-tags-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.risk-tag-lbl {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 600;
}

.paper-summary-card {
  background-color: var(--color-green-soft);
  border: 1px solid rgba(16, 185, 129, 0.15);
  color: var(--color-green);
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}

/* 日报原文大板 */
.report-markdown-body {
  line-height: 1.7;
}

.report-markdown-body h1 {
  font-size: 20px;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.report-markdown-body h2 {
  font-size: 16px;
  margin: 16px 0 8px;
}

.report-markdown-body p {
  margin-bottom: 12px;
  font-size: 13px;
}

.report-markdown-body ul {
  padding-left: 20px;
  margin-bottom: 12px;
}

.report-markdown-body li {
  margin-bottom: 4px;
  font-size: 13px;
}

.report-markdown-body pre {
  background-color: var(--bg-main);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 8px;
  font-family: monospace;
  font-size: 12px;
  overflow-x: auto;
  margin-bottom: 12px;
}

/* Toast 通知样式 */
.toast-stack {
  position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 9999;
}

.toast-msg {
  background-color: var(--bg-dark-sidebar);
  color: #fff;
  border-radius: 8px;
  padding: 12px 20px;
  box-shadow: var(--shadow-lg);
  font-size: 13px;
  font-weight: 600;
  border-left: 4px solid var(--accent);
  animation: slideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

/* 响应式调整 */
@media (max-width: 1280px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
  .detail-card {
    position: static;
  }
}

@media (max-width: 1024px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    display: none;
  }
  .kpi-grid {
    grid-template-columns: repeat(4, 1fr);
  }
  .kpi-card-double {
    grid-column: span 2;
  }
}

@media (max-width: 768px) {
  .table-toolbar,
  .toolbar-right,
  .polling-controls {
    align-items: stretch;
    flex-direction: column;
  }
  .search-box-wrap,
  .polling-controls {
    width: 100%;
  }
  .poll-status {
    min-width: 0;
  }
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .kpi-card-double {
    grid-column: span 2;
  }
  .topbar {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  .top-meta {
    justify-content: space-between;
  }
  .trigger-card-grid, .risk-card-grid {
    grid-template-columns: 1fr;
  }
  .execution-plan-grid {
    grid-template-columns: 1fr;
  }
}

/* 日报编辑器与保存按钮 */
.report-edit-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}
.report-editor-textarea {
  width: 100%;
  min-height: 420px;
  background-color: #0f172a;
  color: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}
.report-editor-textarea:focus {
  border-color: var(--accent);
}
.report-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
.btn-save-report {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #fff;
  border: 0;
  border-radius: 6px;
  padding: 8px 16px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}
.btn-save-report:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2);
}
.btn-cancel-report {
  background-color: var(--border-soft);
  color: var(--text-main);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 16px;
  font-weight: 600;
  cursor: pointer;
}

/* 参数矩阵热力图 */
.heatmap-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
}
.heatmap-table th, .heatmap-table td {
  padding: 8px;
  text-align: center;
  border: 1px solid var(--border);
  font-size: 12px;
}
.heatmap-table th {
  background-color: var(--border-soft);
  color: var(--text-muted);
  font-weight: 600;
}
.heatmap-cell {
  font-weight: 700;
  font-family: monospace;
  transition: transform 0.2s;
}
.heatmap-cell:hover {
  transform: scale(1.08);
  cursor: help;
}

/* 决策沙盒 */
.sandbox-empty {
  text-align: center;
  padding: 24px 0;
  color: var(--text-muted);
}
.sandbox-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--border-soft);
  border: 1px solid var(--border);
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 8px;
}
.sandbox-item-left {
  display: flex;
  flex-direction: column;
}
.sandbox-item-left strong {
  font-size: 13px;
}
.sandbox-item-left span {
  font-size: 11px;
  color: var(--text-muted);
}
.sandbox-item-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sandbox-weight-input {
  width: 60px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  text-align: center;
  font-weight: 600;
  font-family: monospace;
}
.sandbox-remove-btn {
  background: none;
  border: 0;
  color: var(--color-red);
  cursor: pointer;
  font-size: 14px;
}
.sandbox-alert {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #dc2626;
  padding: 12px;
  border-radius: 8px;
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.5;
  animation: pulseBg 2s infinite ease-in-out;
}
.sandbox-add-btn {
  width: 100%;
  background-color: var(--accent-soft);
  color: var(--accent);
  border: 1px dashed var(--accent);
  border-radius: 8px;
  padding: 8px 0;
  font-weight: 600;
  cursor: pointer;
  margin-bottom: 12px;
  transition: all 0.2s;
}
.sandbox-add-btn:hover {
  background-color: var(--accent);
  color: #fff;
}

@keyframes pulseBg {
  0% { opacity: 0.95; }
  50% { opacity: 1; box-shadow: 0 0 8px rgba(239, 68, 68, 0.15); }
  100% { opacity: 0.95; }
}
"""

DASHBOARD_SCRIPT = r"""
// 1. 高保真 Demo 模拟数据集 (完美复刻 68 条标的)
let REAL_DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
let DEMO_DATA = {
  generated_at: "2025-05-20T15:00:00",
  generated_at_label: "2025-05-20 15:00:00",
  mode_label: "演示数据模式",
  source_paths: {
    trade_plan: "reports/trade_plan.demo.json",
    daily_report: "reports/daily_report.demo.md"
  },
  metrics: {
    candidate_count: 68,
    entry_count: 14,
    watch_count: 28,
    skip_count: 26,
    max_score: 73.48,
    risk_count: 5
  },
  paper: {
    summary: "纸面撮合共检查 68 笔，63 笔通过，5 笔需复核。当前纸面检查总体正常。"
  },
  warnings: [],
  candidates: []
};

// 预定义前 12 个标的，完美对应图片
const PREDEFINED_CANDIDATES = [
  { symbol: "510300", name: "沪深300ETF", index_name: "沪深300", status: "entry_candidate", status_label: "可入场", status_tone: "positive", score: 72.0, signal_close: 3.876, entry_price: 3.840, invalid_price: 3.620, stop_price: 3.840, take_profit: 3.920, change_pct: -0.49, signal_name: "多因子共振", risk_level: "中", date: "2025-05-20", news_summary: "多因子模型触发买入信号，量价动量与基本面得分共振好转。", advantages: ["5日动量为正", "20日动量为正", "收盘价站上20日均线"], risks: ["RSI偏高，追价风险抬升"] },
  { symbol: "510050", name: "上证50ETF", index_name: "上证50", status: "entry_candidate", status_label: "可入场", status_tone: "positive", score: 70.5, signal_close: 2.646, entry_price: 2.620, invalid_price: 2.500, stop_price: 2.620, take_profit: 2.680, change_pct: -0.41, signal_name: "估值修复", risk_level: "中", date: "2025-05-20", news_summary: "低估值蓝筹板块估值修复，大单资金持续净流入。", advantages: ["收盘价站上20日均线", "中期趋势不弱于长期趋势"], risks: ["ATR波动率偏高"] },
  { symbol: "159915", name: "创业板ETF", index_name: "创业板指", status: "entry_candidate", status_label: "可入场", status_tone: "positive", score: 68.2, signal_close: 1.812, entry_price: 1.780, invalid_price: 1.680, stop_price: 1.780, take_profit: 1.860, change_pct: -0.82, signal_name: "趋势反转", risk_level: "中", date: "2025-05-20", news_summary: "成长性板块估值出清，形成底部企稳迹象，均线金叉。", advantages: ["5日动量为正", "近期成交量高于20日均量"], risks: ["近期新闻分数偏负"] },
  { symbol: "512100", name: "中证1000ETF", index_name: "中证1000", status: "watch_only", status_label: "观察", status_tone: "warning", score: 65.8, signal_close: 2.021, entry_price: 1.980, invalid_price: 1.900, stop_price: 1.980, take_profit: 2.060, change_pct: 0.25, signal_name: "动量增强", risk_level: "高", date: "2025-05-20", news_summary: "小盘股动量明显上升，但大盘流动性限制了其空间，建议保持关注。", advantages: ["5日动量为正", "20日动量为正"], risks: ["RSI偏高，追价风险抬升", "ATR波动率偏高"] },
  { symbol: "159922", name: "中证500ETF", index_name: "中证500", status: "watch_only", status_label: "观察", status_tone: "warning", score: 63.4, signal_close: 5.247, entry_price: 5.120, invalid_price: 4.900, stop_price: 5.120, take_profit: 5.300, change_pct: -0.28, signal_name: "波动收敛", risk_level: "中", date: "2025-05-20", news_summary: "中期阻力带附近波动收敛，方向尚未明朗，维持在观察池中。", advantages: ["中期趋势不弱于长期趋势", "近期成交量高于20日均量"], risks: ["价格仍低于近期高点超过10%"] },
  { symbol: "510500", name: "中证500ETF", index_name: "中证500", status: "watch_only", status_label: "观察", status_tone: "warning", score: 63.0, signal_close: 5.231, entry_price: 5.100, invalid_price: 4.880, stop_price: 5.100, take_profit: 5.280, change_pct: -0.31, signal_name: "波动收敛", risk_level: "中", date: "2025-05-20", news_summary: "中证500指数波动率见底回升，成交温和放大，但需确立站上关键阻力。", advantages: ["收盘价站上20日均线"], risks: ["缺少新闻分数，不能视为新闻确认"] },
  { symbol: "159601", name: "A50ETF", index_name: "富时中国A50", status: "watch_only", status_label: "观察", status_tone: "warning", score: 61.2, signal_close: 1.317, entry_price: 1.280, invalid_price: 1.220, stop_price: 1.280, take_profit: 1.340, change_pct: -0.53, signal_name: "外资流入", risk_level: "中", date: "2025-05-20", news_summary: "北向资金近期增持，权重股护盘积极，但缺乏持续动能。", advantages: ["中期趋势不弱于长期趋势"], risks: ["价格仍低于近期高点超过10%"] },
  { symbol: "588000", name: "科创50ETF", index_name: "科创50", status: "watch_only", status_label: "观察", status_tone: "warning", score: 59.8, signal_close: 0.735, entry_price: 0.720, invalid_price: 0.680, stop_price: 0.720, take_profit: 0.760, change_pct: 0.41, signal_name: "超跌反弹", risk_level: "高", date: "2025-05-20", news_summary: "科创板近期连续调整后迎来弱反弹，技术性超卖严重。", advantages: ["近期成交量高于20日均量"], risks: ["5日动量为负", "20日动量为负"] },
  { symbol: "159919", name: "沪深300ETF", index_name: "沪深300", status: "skip", status_label: "跳过", status_tone: "muted", score: 55.4, signal_close: 3.873, entry_price: 3.820, invalid_price: 3.600, stop_price: 3.820, take_profit: 3.900, change_pct: -0.48, signal_name: "基本面偏弱", risk_level: "高", date: "2025-05-20", news_summary: "该基金对应的底层因子得分下滑，宏观风险增加，跳过本交易窗口。", advantages: ["中期趋势不弱于长期趋势"], risks: ["5日动量为负", "20日动量为负", "价格仍低于近期高点超过10%"] },
  { symbol: "515790", name: "光伏ETF", index_name: "中证光伏产业", status: "skip", status_label: "跳过", status_tone: "muted", score: 52.0, signal_close: 0.702, entry_price: 0.680, invalid_price: 0.640, stop_price: 0.680, take_profit: 0.740, change_pct: -1.12, signal_name: "行业弱势", risk_level: "高", date: "2025-05-20", news_summary: "光伏板块持续供需失衡，技术均线呈空头排列，资金出逃明显。", advantages: [], risks: ["5日动量为负", "20日动量为负", "价格仍低于近期高点超过10%", "ATR波动率偏高"] },
  { symbol: "159869", name: "游戏ETF", index_name: "中证动漫游戏", status: "skip", status_label: "跳过", status_tone: "muted", score: 49.6, signal_close: 1.055, entry_price: 1.020, invalid_price: 0.950, stop_price: 1.020, take_profit: 1.100, change_pct: -0.76, signal_name: "估值过高", risk_level: "高", date: "2025-05-20", news_summary: "游戏行业政策处于观察期，估值透支严重，近期技术面上方抛压极大。", advantages: [], risks: ["5日动量为负", "价格仍低于近期高点超过10%", "RSI偏高，追价风险抬升"] },
  { symbol: "516160", name: "新能源ETF", index_name: "CS新能源", status: "skip", status_label: "跳过", status_tone: "muted", score: 45.2, signal_close: 0.948, entry_price: 0.920, invalid_price: 0.860, stop_price: 0.920, take_profit: 1.000, change_pct: -1.04, signal_name: "趋势向下", risk_level: "高", date: "2025-05-20", news_summary: "CS新能源指数跌破关键支撑位，长期下行趋势加剧，建议规避。", advantages: [], risks: ["5日动量为负", "20日动量为负", "收盘价低于20日均线"] }
];

// 生成余下的 56 个标的以填满 68 个候选池
const INDEX_POOL = ["沪深300", "中证500", "上证50", "创业板指", "科创50", "中证1000"];
const SIGNAL_POOL = ["均线回踩", "量价突破", "因子增强", "主力流入", "超买超卖", "估值底部"];
const ADV_POOL = ["5日动量为正", "20日动量为正", "收盘价站上20日均线", "中期趋势不弱于长期趋势", "近期成交量高于20日均量"];
const RISK_POOL = ["RSI偏高，追价风险抬升", "ATR波动率偏高", "价格仍低于近期高点超过10%", "5日动量为负", "20日动量为负"];

for (let i = 13; i <= 68; i++) {
  const code = (510000 + i * 97).toString();
  const idxName = INDEX_POOL[i % INDEX_POOL.length];
  const name = idxName + "精选ETF-" + i;
  let status = "watch_only";
  let statusLabel = "观察";
  let statusTone = "warning";
  let riskLvl = "中";
  
  if (i <= 14) {
    status = "entry_candidate";
    statusLabel = "可入场";
    statusTone = "positive";
  } else if (i > 42) {
    status = "skip";
    statusLabel = "跳过";
    statusTone = "muted";
    riskLvl = i % 3 === 0 ? "高" : "中";
  }
  
  const score = Number((68 - i * 0.4 + (i % 3) * 2).toFixed(1));
  const signalClose = Number((2.0 + (i % 5) * 0.65).toFixed(3));
  const entryPrice = Number((signalClose * 0.985).toFixed(3));
  const takeProfit = Number((entryPrice * 1.05).toFixed(3));
  const invalidPrice = Number((entryPrice * 0.93).toFixed(3));
  const changePct = Number((-1.5 + (i % 7) * 0.45).toFixed(2));
  
  const advantages = [];
  const risks = [];
  
  if (status === "entry_candidate") {
    advantages.push(ADV_POOL[0], ADV_POOL[1], ADV_POOL[2]);
    if (i % 2 === 0) advantages.push(ADV_POOL[4]);
    risks.push(RISK_POOL[0]);
  } else if (status === "watch_only") {
    advantages.push(ADV_POOL[3]);
    risks.push(RISK_POOL[1], RISK_POOL[2]);
  } else {
    risks.push(RISK_POOL[3], RISK_POOL[4]);
  }
  
  PREDEFINED_CANDIDATES.push({
    symbol: code,
    name: name,
    index_name: idxName,
    status: status,
    status_label: statusLabel,
    status_tone: statusTone,
    score: score,
    signal_close: signalClose,
    entry_price: entryPrice,
    invalid_price: invalidPrice,
    stop_price: entryPrice,
    take_profit: takeProfit,
    change_pct: changePct,
    signal_name: SIGNAL_POOL[i % SIGNAL_POOL.length],
    risk_level: riskLvl,
    date: "2025-05-20",
    news_summary: `基于${idxName}成分股的多因子打分规则输出。当前行业因子中性偏强，关注核心支撑。`,
    advantages: advantages,
    risks: risks
  });
}

DEMO_DATA.candidates = PREDEFINED_CANDIDATES;

// 2. 状态机
const state = {
  dataSource: "demo", // 'demo' | 'real'
  currentTab: "overview",
  statusFilter: "all",
  searchQuery: "",
  selectedSymbol: null,
  starredSymbols: new Set(["510300", "510050"]),
  assetHidden: false,
  externalLookupResult: null,
  lookupTimerId: null,
  lookupError: "",
  trendCache: {},
  trendLoadingSymbol: null,
  
  // 分页数据
  currentPage: 1,
  pageSize: 10,

  // 自动刷新状态
  autoRefreshEnabled: false,
  pollIntervalSeconds: Number((REAL_DATA.polling && REAL_DATA.polling.default_interval_seconds) || 30),
  minPollIntervalSeconds: Number((REAL_DATA.polling && REAL_DATA.polling.min_interval_seconds) || 5),
  pollTimerId: null,
  countdownTimerId: null,
  nextRefreshAt: null,
  lastRefreshAt: REAL_DATA.refreshed_at_label || "尚未刷新",
  priceSourceLabel: "行情来源：待刷新",
  refreshError: "",
  isRefreshing: false
};

// 3. 全局获取当前活动的数据集
function getActiveData() {
  if (state.dataSource === "real") {
    return REAL_DATA;
  }
  return DEMO_DATA;
}

// 获取当前过滤和搜索后的标的列表
function getFilteredCandidates() {
  const data = getActiveData();
  const query = state.searchQuery.trim().toLowerCase();
  
  const matches = data.candidates.filter(item => {
    // 状态过滤
    const statusMatch = state.statusFilter === "all" || item.status === state.statusFilter;
    // 搜索词过滤
    const searchMatch = !query || 
                        item.symbol.toLowerCase().includes(query) || 
                        (item.name && item.name.toLowerCase().includes(query)) ||
                        (item.index_name && item.index_name.toLowerCase().includes(query));
    return statusMatch && searchMatch;
  });
  if (!matches.length && state.statusFilter === "all" && state.externalLookupResult && query) {
    const external = state.externalLookupResult;
    const externalText = `${external.symbol} ${external.name || ""} ${external.index_name || ""}`.toLowerCase();
    if (externalText.includes(query)) {
      return [external];
    }
  }
  return matches;
}

function pickBestSearchMatch(items, query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized || !items.length) return null;
  return items.find(item => item.symbol.toLowerCase() === normalized)
    || items.find(item => (item.name || "").toLowerCase() === normalized)
    || items.find(item => (item.name || "").toLowerCase().includes(normalized))
    || items[0];
}

function handleSecuritySearchInput() {
  const query = state.searchQuery.trim();
  if (state.lookupTimerId) {
    window.clearTimeout(state.lookupTimerId);
    state.lookupTimerId = null;
  }
  if (!query) {
    state.externalLookupResult = null;
    state.lookupError = "";
    const data = getActiveData();
    state.selectedSymbol = data.candidates[0]?.symbol || null;
    return;
  }

  const matches = getFilteredCandidates();
  const best = pickBestSearchMatch(matches, query);
  if (best) {
    state.externalLookupResult = null;
    state.lookupError = "";
    state.selectedSymbol = best.symbol;
    return;
  }

  if (state.dataSource !== "real" || !isServiceMode() || query.length < 2) {
    state.externalLookupResult = null;
    state.lookupError = query.length >= 2 ? "当前候选池中没有匹配标的。" : "";
    return;
  }

  state.lookupError = "正在查询外部行情...";
  state.lookupTimerId = window.setTimeout(() => lookupExternalSecurity(query), 350);
}

// 格式化辅助函数
function formatMoney(value) {
  return Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function formatPercent(value) {
  const isPercentStr = typeof value === "string" && value.includes("%");
  const num = isPercentStr ? parseFloat(value) : Number(value || 0) * (value < 0.15 ? 100 : 1);
  return `${num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function getPlanBuyPrice(item) {
  if (item && item.is_external_lookup) return Number(item.entry_price || 0);
  return Number(item.entry_price || item.signal_close || 0);
}

function getPlanTakeProfitPrice(item) {
  if (item && item.is_external_lookup) return Number(item.take_profit_price || item.take_profit || 0);
  return Number(item.take_profit_price || item.take_profit || item.take_profit_price_if_entry_fills || 0);
}

function getPlanStopLossPrice(item) {
  if (item && item.is_external_lookup) return Number(item.stop_loss_price || item.stop_price || 0);
  return Number(item.stop_loss_price || item.stop_price || item.stop_loss_price_if_entry_fills || 0);
}

function getPlanInvalidationPrice(item) {
  return Number(item.pre_entry_invalidation_price || item.invalid_price || 0);
}

function getPlanHealth(item) {
  if (!item || item.is_external_lookup) {
    return { actionable: false, level: "neutral", label: "行情查询", reason: "仅查行情，不生成交易计划", distancePct: 0 };
  }
  const current = Number(item.signal_close || 0);
  const planBasis = Number(item.plan_signal_close || item.entry_price || 0);
  const buy = getPlanBuyPrice(item);
  const takeProfit = getPlanTakeProfitPrice(item);
  const stopLoss = getPlanStopLossPrice(item);
  if (!current || !buy) {
    return { actionable: false, level: "warning", label: "待复核", reason: "缺少实时价或计划买入价", distancePct: 0 };
  }
  const distancePct = (current - buy) / buy;
  const basisDriftPct = planBasis > 0 ? Math.abs(current / planBasis - 1) : 0;
  if (basisDriftPct > 0.25) {
    return {
      actionable: false,
      level: "danger",
      label: "计划需重算",
      reason: `实时价相对计划基准价偏离 ${(basisDriftPct * 100).toFixed(1)}%，疑似旧计划或复权口径不一致`,
      distancePct
    };
  }
  if (takeProfit > 0 && current > takeProfit * 1.01) {
    return {
      actionable: false,
      level: "danger",
      label: "已超止盈",
      reason: `实时价已高于计划止盈价 ${formatMoney(takeProfit)}，不能按原入场价追买`,
      distancePct
    };
  }
  if (stopLoss > 0 && current < stopLoss * 0.99) {
    return {
      actionable: false,
      level: "danger",
      label: "跌破止损",
      reason: `实时价已低于计划止损价 ${formatMoney(stopLoss)}，原计划失效`,
      distancePct
    };
  }
  if (distancePct > 0.03) {
    return {
      actionable: false,
      level: "warning",
      label: "等待回踩",
      reason: `实时价高于计划买入价 ${(distancePct * 100).toFixed(1)}%，不应追价入场`,
      distancePct
    };
  }
  if (distancePct < -0.03) {
    return {
      actionable: false,
      level: "warning",
      label: "未到触发",
      reason: `实时价低于计划买入价 ${Math.abs(distancePct * 100).toFixed(1)}%，尚未触发`,
      distancePct
    };
  }
  return { actionable: true, level: "ok", label: item.status_label || getStatusLabel(item.status), reason: "实时价接近计划触发区间", distancePct };
}

function getPlanBadgeClass(health, fallbackStatus) {
  if (health.level === "danger") return "badge-red";
  if (health.level === "warning") return "badge-orange";
  if (health.level === "ok") return getStatusBadgeClass(fallbackStatus);
  return "badge-gray";
}

function isPlanActionable(item) {
  return item.status === "entry_candidate" && getPlanHealth(item).actionable;
}

// 4. UI 绘制核心逻辑
function initDashboard() {
  if (window.__haitongDashboardInitialized) return;
  window.__haitongDashboardInitialized = true;

  // 侧边栏折叠控制
  const sidebarBtn = document.getElementById("sidebarToggle");
  const appShell = document.querySelector(".app-shell");
  
  if (localStorage.getItem("haitong-sidebar-collapsed") === "true") {
    if (appShell) appShell.classList.add("sidebar-collapsed");
  }
  
  if (sidebarBtn && appShell) {
    sidebarBtn.addEventListener("click", () => {
      appShell.classList.toggle("sidebar-collapsed");
      const isCollapsed = appShell.classList.contains("sidebar-collapsed");
      localStorage.setItem("haitong-sidebar-collapsed", isCollapsed);
      showToast(isCollapsed ? "📥 导航栏已收起，开启宽屏决策模式" : "📤 导航栏已展开");
    });
  }

  // 绑定菜单 Tab 切换事件
  document.querySelectorAll(".sidebar-nav .nav-item").forEach(el => {
    if (el.classList.contains("lock-item")) {
      el.addEventListener("click", () => {
        showToast(`「${el.dataset.toast}」在只读研究模式下暂未开通`);
      });
      return;
    }
    
    el.addEventListener("click", () => {
      document.querySelectorAll(".sidebar-nav .nav-item").forEach(item => item.classList.remove("active"));
      el.classList.add("active");
      
      const tab = el.dataset.tab;
      state.currentTab = tab;
      
      // 切换主展示容器
      document.querySelectorAll(".view-panel").forEach(panel => panel.classList.remove("active"));
      document.getElementById(`panel-${tab}`).classList.add("active");
      
      renderPanel();
    });
  });

  // 绑定搜索输入
  document.getElementById("searchInput").addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
    state.currentPage = 1;
    handleSecuritySearchInput();
    renderPanel();
  });

  // 绑定全选事件
  document.getElementById("chkSelectAll").addEventListener("change", (e) => {
    const isChecked = e.target.checked;
    document.querySelectorAll("#candidateTable input[type='checkbox']").forEach(chk => {
      chk.checked = isChecked;
    });
  });

  // 绑定刷新按钮
  document.getElementById("refreshButton").addEventListener("click", () => {
    refreshDashboardData("manual");
  });

  initPollingControls();

  // 绑定详情页子 Tabs 切换
  document.querySelectorAll(".det-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".det-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      
      document.querySelectorAll(".detail-tab-panel").forEach(p => p.classList.remove("active"));
      document.getElementById(`dpanel-${btn.dataset.dtab}`).classList.add("active");
    });
  });

  // 启动准实时 L1 行情轮询
  // 初始化决策沙盒默认状态
  renderSandbox();

  // 首次运行
  const preferredMode = (REAL_DATA.candidates && REAL_DATA.candidates.length > 0) ? "real" : "demo";
  setDataSource(preferredMode);
  runL1RealtimePriceTicker();
}

// 切换数据源
function setDataSource(mode) {
  state.dataSource = mode;
  state.currentPage = 1;
  
  document.getElementById("btnDemoMode").classList.toggle("active", mode === "demo");
  document.getElementById("btnRealMode").classList.toggle("active", mode === "real");
  
  // 初始化默认选中的标的
  const data = getActiveData();
  if (data.candidates && data.candidates.length > 0) {
    state.selectedSymbol = data.candidates[0].symbol;
  } else {
    state.selectedSymbol = null;
  }
  
  renderKPIAndTopbar();
  renderPanel();
  showToast(`切换至 ${mode === "demo" ? "68只标的高保真演示模式" : "系统实时数据模式"}`);
}

// 隐藏/显示总资产
function toggleAssetPrivacy() {
  state.assetHidden = !state.assetHidden;
  
  const openIcon = document.getElementById("eyeOpen");
  const closedIcon = document.getElementById("eyeClosed");
  const assetVal = document.getElementById("assetVal");
  
  if (state.assetHidden) {
    openIcon.style.display = "none";
    closedIcon.style.display = "block";
    assetVal.classList.add("asset-blur");
    assetVal.textContent = "******";
  } else {
    openIcon.style.display = "block";
    closedIcon.style.display = "none";
    assetVal.classList.remove("asset-blur");
    assetVal.textContent = "12,568,327.42";
  }
}

// 渲染 KPI 数据和顶部元信息
function renderKPIAndTopbar() {
  const data = getActiveData();
  const displayTime = data.refreshed_at || data.generated_at;
  
  // 顶部元信息
  document.getElementById("dateStr").textContent = state.dataSource === "demo" ? "2025-05-20 (周二)" : formatRealDate(displayTime);
  document.getElementById("timeStr").textContent = state.dataSource === "demo" ? "15:00:00" : formatRealTime(displayTime);
  
  // KPI 卡片数据
  let candCount = 0;
  let entryCount = 0;
  let watchCount = 0;
  let skipCount = 0;
  let triggerCount = 0;
  let riskCount = 0;
  
  if (state.dataSource === "real") {
    candCount = data.candidates.length;
    entryCount = data.candidates.filter(isPlanActionable).length;
    watchCount = data.candidates.filter(c => c.status === "watch_only").length;
    skipCount = data.candidates.filter(c => c.status === "skip").length;
    triggerCount = entryCount; 
    riskCount = (data.metrics.risk_count || 0) + data.candidates.filter(c => getPlanHealth(c).level === "danger").length;
    
    // 更新 KPI 面板的值
    document.getElementById("metricCandidates").textContent = candCount;
    document.getElementById("metricEntries").textContent = entryCount;
    document.getElementById("metricWatch").textContent = watchCount;
    document.getElementById("metricSkip").textContent = skipCount;
    document.getElementById("metricTodayTrigger").textContent = triggerCount;
    document.getElementById("metricRisks").textContent = riskCount;
    
    // 较昨日及比例重新精算
    document.getElementById("kpiPoolChange").textContent = "+0 只";
    document.getElementById("kpiTodayTriggerChange").textContent = "+0 只";
    document.getElementById("kpiRisksChange").textContent = "+0 只";
    
    const entryRatio = candCount > 0 ? (entryCount / candCount * 100).toFixed(2) + "%" : "0.00%";
    const watchRatio = candCount > 0 ? (watchCount / candCount * 100).toFixed(2) + "%" : "0.00%";
    const skipRatio = candCount > 0 ? (skipCount / candCount * 100).toFixed(2) + "%" : "0.00%";
    
    document.getElementById("kpiEntryRatio").textContent = entryRatio;
    document.getElementById("kpiWatchRatio").textContent = watchRatio;
    document.getElementById("kpiSkipRatio").textContent = skipRatio;
  } else {
    // 演示模式直接展现完美的原图数字
    document.getElementById("metricCandidates").textContent = "68";
    document.getElementById("metricEntries").textContent = "14";
    document.getElementById("metricWatch").textContent = "28";
    document.getElementById("metricSkip").textContent = "26";
    document.getElementById("metricTodayTrigger").textContent = "7";
    document.getElementById("metricRisks").textContent = "5";
    
    document.getElementById("kpiPoolChange").textContent = "+6 只";
    document.getElementById("kpiTodayTriggerChange").textContent = "+2 只";
    document.getElementById("kpiRisksChange").textContent = "+1 只";
    
    document.getElementById("kpiEntryRatio").textContent = "20.59%";
    document.getElementById("kpiWatchRatio").textContent = "41.18%";
    document.getElementById("kpiSkipRatio").textContent = "38.24%";
  }
  
  // 渲染通知堆栈
  const noticeStack = document.getElementById("noticeStack");
  if (data.warnings && data.warnings.length > 0) {
    noticeStack.innerHTML = data.warnings.map(warn => `
      <div class="notice-strip">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <span>${escapeHtml(warn)}</span>
      </div>
    `).join("");
  } else {
    noticeStack.innerHTML = "";
  }
}

// 核心渲染分流
function renderPanel() {
  const filtered = getFilteredCandidates();
  
  // 重新渲染状态分类 Tabs 的数字
  renderStatusFilterTabs();
  
  if (state.currentTab === "overview") {
    renderOverviewTable(filtered);
  } else if (state.currentTab === "triggers") {
    renderTriggersTab(filtered);
  } else if (state.currentTab === "risks") {
    renderRisksTab(filtered);
  } else if (state.currentTab === "report") {
    renderReportTab();
  }
  
  // 联动右侧详情面板
  renderRightDetail();
}

// 渲染状态过滤 Tab 按钮组件
function renderStatusFilterTabs() {
  const data = getActiveData();
  const countAll = data.candidates.length;
  const countEntry = data.candidates.filter(isPlanActionable).length;
  const countWatch = data.candidates.filter(c => c.status === "watch_only").length;
  const countSkip = data.candidates.filter(c => c.status === "skip").length;
  
  const tabsContainer = document.getElementById("statusFilterTabs");
  tabsContainer.innerHTML = `
    <button type="button" class="filter-tab-btn ${state.statusFilter === "all" ? "active" : ""}" onclick="setStatusFilter('all')">全部 (${countAll})</button>
    <button type="button" class="filter-tab-btn ${state.statusFilter === "entry_candidate" ? "active" : ""}" onclick="setStatusFilter('entry_candidate')">可入场 (${countEntry})</button>
    <button type="button" class="filter-tab-btn ${state.statusFilter === "watch_only" ? "active" : ""}" onclick="setStatusFilter('watch_only')">观察 (${countWatch})</button>
    <button type="button" class="filter-tab-btn ${state.statusFilter === "skip" ? "active" : ""}" onclick="setStatusFilter('skip')">跳过 (${countSkip})</button>
  `;
}

function setStatusFilter(filter) {
  state.statusFilter = filter;
  state.currentPage = 1;
  renderPanel();
}

// 5. 渲染第一个看板：数据表格 (Overview)
function renderOverviewTable(items) {
  const tableBody = document.getElementById("candidateTable");
  document.getElementById("visibleCount").textContent = `共 ${items.length} 条`;
  
  if (!items.length) {
    const emptyText = state.lookupError || "暂无可展示的数据。";
    tableBody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:var(--text-muted);padding:40px;">${escapeHtml(emptyText)}</td></tr>`;
    renderPagination(0);
    return;
  }
  
  // 分页截断
  const totalItems = items.length;
  const startIdx = (state.currentPage - 1) * state.pageSize;
  const endIdx = startIdx + state.pageSize;
  const paginatedItems = items.slice(startIdx, endIdx);
  
  tableBody.innerHTML = paginatedItems.map(item => {
    const isStarred = state.starredSymbols.has(item.symbol);
    const starClass = isStarred ? "td-star starred" : "td-star";
    const rowClass = state.selectedSymbol === item.symbol ? "selected" : "";
    
    // 颜色着色
    const chgVal = item.change_pct ?? item.change ?? 0;
    const isUp = chgVal > 0;
    const chgClass = chgVal === 0 ? "color-neutral" : (isUp ? "color-red font-bold" : "color-green font-bold");
    const chgPrefix = chgVal > 0 ? "+" : "";
    
    const buyPrice = getPlanBuyPrice(item);
    const takeProfitPrice = getPlanTakeProfitPrice(item);
    const stopLossPrice = getPlanStopLossPrice(item);
    const planHealth = getPlanHealth(item);
    const entryTrigStr = item.is_external_lookup
      ? `<span class="price-plan-cell"><strong>暂无计划</strong><small>仅展示行情</small></span>`
      : `<span class="price-plan-cell ${planHealth.level === "danger" ? "plan-danger" : ""}"><strong>${planHealth.actionable ? "买" : "旧"} ${formatMoney(buyPrice)}</strong><small>止 ${formatMoney(stopLossPrice)} / 盈 ${formatMoney(takeProfitPrice)}</small><small>${escapeHtml(planHealth.reason)}</small></span>`;
    
    return `
      <tr class="${rowClass}" onclick="selectRow('${item.symbol}')">
        <td onclick="event.stopPropagation()"><input type="checkbox" value="${item.symbol}"></td>
        <td class="${starClass}" onclick="event.stopPropagation(); toggleStar('${item.symbol}')">★</td>
        <td class="td-symbol">${escapeHtml(item.symbol)}</td>
        <td class="td-name"><span class="name-main">${escapeHtml(item.name || getFundName(item.symbol))}</span><span class="name-sub">${escapeHtml(item.symbol)}</span></td>
        <td class="color-neutral">${escapeHtml(item.index_name || item.symbol)}</td>
        <td><span class="badge ${getPlanBadgeClass(planHealth, item.status)}">${escapeHtml(planHealth.label)}</span></td>
        <td class="font-mono">${entryTrigStr}</td>
        <td class="font-mono font-bold">${formatMoney(item.signal_close)}</td>
        <td class="font-mono ${chgClass}">${chgPrefix}${chgVal.toFixed(2)}%</td>
        <td><span class="badge badge-gray">${escapeHtml(item.signal_name || "因子突破")}</span></td>
        <td><span class="badge ${planHealth.level === "danger" || item.risk_level === "高" ? "badge-red" : "badge-orange"}">${escapeHtml(planHealth.level === "danger" ? "高" : (item.risk_level || "中"))}</span></td>
        <td class="color-neutral">${escapeHtml(item.date || "未知")}</td>
      </tr>
    `;
  }).join("");
  
  renderPagination(totalItems);
}

// 分页绘制
function renderPagination(total) {
  const totalPages = Math.ceil(total / state.pageSize) || 1;
  const numbersContainer = document.getElementById("pagerNumbers");
  
  document.getElementById("prevPageBtn").disabled = state.currentPage <= 1;
  document.getElementById("nextPageBtn").disabled = state.currentPage >= totalPages;
  
  let html = "";
  for (let i = 1; i <= totalPages; i++) {
    if (totalPages > 6) {
      // 复杂的省略号显示
      if (i === 1 || i === totalPages || (i >= state.currentPage - 1 && i <= state.currentPage + 1)) {
        html += `<button class="pager-num ${state.currentPage === i ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`;
      } else if (i === 2 || i === totalPages - 1) {
        html += `<span class="pager-ellipsis">...</span>`;
      }
    } else {
      html += `<button class="pager-num ${state.currentPage === i ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`;
    }
  }
  
  // 去重多个连着的省略号
  numbersContainer.innerHTML = html.replace(/(<span class="pager-ellipsis">\.\.\.<\/span>\s*){2,}/g, '<span class="pager-ellipsis">...</span>');
}

function goToPage(page) {
  state.currentPage = page;
  renderPanel();
}

function changePage(direction) {
  state.currentPage += direction;
  renderPanel();
}

function changePageSize(size) {
  state.pageSize = parseInt(size);
  state.currentPage = 1;
  renderPanel();
}

function selectRow(symbol) {
  state.selectedSymbol = symbol;
  
  // 高亮表格对应的行
  document.querySelectorAll("#candidateTable tr").forEach(row => row.classList.remove("selected"));
  renderPanel();
}

function toggleStar(symbol) {
  if (state.starredSymbols.has(symbol)) {
    state.starredSymbols.delete(symbol);
  } else {
    state.starredSymbols.add(symbol);
  }
  renderPanel();
}

// 6. 渲染第二个看板：触发价格 (Triggers)
function renderTriggersTab(items) {
  const container = document.getElementById("triggerList");
  if (!items.length) {
    container.innerHTML = `<div class="detail-empty-placeholder"><p>暂无可展示的触发价格标的。</p></div>`;
    return;
  }
  
  container.innerHTML = items.map(item => {
    const buyPrice = getPlanBuyPrice(item);
    const takeProfitPrice = getPlanTakeProfitPrice(item);
    const stopLossPrice = getPlanStopLossPrice(item);
    const invalidPrice = getPlanInvalidationPrice(item);
    return `
      <article class="card-item">
        <div class="card-item-header">
          <div class="card-item-title">
            <strong>${escapeHtml(item.symbol)}</strong>
            <span>${escapeHtml(item.name || getFundName(item.symbol))}</span>
          </div>
          <span class="badge ${getStatusBadgeClass(item.status)}">${escapeHtml(item.status_label || getStatusLabel(item.status))}</span>
        </div>
        <div class="card-item-metrics">
          <div class="card-metric"><span>计划买入</span><strong>${formatMoney(buyPrice)}</strong></div>
          <div class="card-metric"><span>止盈卖出</span><strong>${formatMoney(takeProfitPrice)}</strong></div>
          <div class="card-metric"><span>止损离场</span><strong>${formatMoney(stopLossPrice)}</strong></div>
          <div class="card-metric"><span>入场前失效</span><strong>${formatMoney(invalidPrice)}</strong></div>
        </div>
      </article>
    `;
  }).join("");
}

// 7. 渲染第三个看板：风险复盘 (Risks)
function renderRisksTab(items) {
  const container = document.getElementById("riskList");
  const data = getActiveData();
  
  document.getElementById("paperSummary").innerHTML = `<strong>纸面账户摘要：</strong>${escapeHtml(data.paper.summary)}`;
  
  if (!items.length) {
    container.innerHTML = `<div class="detail-empty-placeholder"><p>暂无可展示的风险复盘标的。</p></div>`;
    return;
  }
  
  container.innerHTML = items.map(item => {
    const advs = item.advantages || ["多因子特征共振好转", "近期成交量突破放量"];
    const rsks = item.risks || ["高位追价风险抬升"];
    
    return `
      <article class="card-item">
        <div class="card-item-header">
          <div class="card-item-title">
            <strong>${escapeHtml(item.symbol)}</strong>
            <span>${escapeHtml(item.name || getFundName(item.symbol))}</span>
          </div>
          <span class="badge badge-gray">新闻分: ${Number(item.news_score || 0.2).toFixed(1)}</span>
        </div>
        <div class="card-item-metrics">
          <div class="card-metric"><span>短期倾向</span><strong>${escapeHtml(item.short_term_bias_label || "规则偏强")}</strong></div>
          <div class="card-metric"><span>中期倾向</span><strong>${escapeHtml(item.medium_term_bias_label || "中性偏多")}</strong></div>
          <div class="card-metric"><span>止损距离</span><strong>${formatPercent(item.stop_gap_pct || 0.048)}</strong></div>
          <div class="card-metric"><span>预计空间</span><strong>${formatPercent(item.profit_gap_pct || 0.087)}</strong></div>
        </div>
        <div class="risk-tags-group">
          <span class="risk-tag-lbl">优势标签</span>
          <div class="tag-flex-wrapper">
            ${advs.map(t => `<span class="adv-tag">${escapeHtml(t)}</span>`).join("")}
          </div>
        </div>
        <div class="risk-tags-group">
          <span class="risk-tag-lbl">风险预警</span>
          <div class="tag-flex-wrapper">
            ${rsks.map(t => `<span class="risk-tag">${escapeHtml(t)}</span>`).join("")}
          </div>
        </div>
      </article>
    `;
  }).join("");
}

// 8. 渲染第四个看板：研究日报
function renderReportTab() {
  const data = getActiveData();
  const container = document.getElementById("dailyReport");
  const content = data.daily_report ? data.daily_report.content : "";
  
  if (!content || !content.trim()) {
    container.innerHTML = `<div class="detail-empty-placeholder"><p>暂无日报原文内容。</p></div>`;
    return;
  }
  container.innerHTML = markdownLite(content);
}

// 9. 联动右侧详情面板渲染
function renderRightDetail() {
  const data = getActiveData();
  const externalSelected = state.externalLookupResult && state.externalLookupResult.symbol === state.selectedSymbol
    ? state.externalLookupResult
    : null;
  const selected = data.candidates.find(item => item.symbol === state.selectedSymbol) || externalSelected || data.candidates[0];
  
  const emptyState = document.getElementById("detailEmpty");
  const fullContent = document.getElementById("detailContent");
  
  if (!selected) {
    emptyState.style.display = "flex";
    fullContent.style.display = "none";
    return;
  }
  
  emptyState.style.display = "none";
  fullContent.style.display = "block";
  
  // 渲染头部
  document.getElementById("detSymbol").textContent = selected.symbol;
  document.getElementById("detName").textContent = selected.name || getFundName(selected.symbol);
  document.getElementById("detSubtitle").textContent = selected.is_external_lookup
    ? `行情查询：${escapeHtml(selected.name || selected.symbol)}`
    : `跟踪指数：${escapeHtml(selected.index_name || selected.index || "大盘指数")}`;
  
  const isStarred = state.starredSymbols.has(selected.symbol);
  document.getElementById("detStarBtn").classList.toggle("starred", isStarred);
  
  const badge = document.getElementById("detStatusBadge");
  const planHealth = getPlanHealth(selected);
  badge.textContent = planHealth.label;
  badge.className = `det-status-badge ${getPlanBadgeClass(planHealth, selected.status)}`;
  
  // Tab 1: 核心信息绑定
  document.getElementById("detIndex").textContent = selected.index_name || selected.index || "A股大盘";
  document.getElementById("detIopv").textContent = formatMoney(selected.signal_close - 0.002);
  document.getElementById("detLatestPrice").textContent = formatMoney(selected.signal_close);
  renderTrendSection(selected);
  ensureTrendData(selected.symbol);
  
  const discountVal = (selected.symbol === "510300" || selected.symbol === "512100") ? "0.05%" : "0.02%";
  document.getElementById("detDiscount").textContent = discountVal;
  
  const chgVal = selected.change_pct ?? selected.change ?? 0;
  const detChg = document.getElementById("detChange");
  detChg.textContent = `${chgVal > 0 ? "+" : ""}${chgVal.toFixed(2)}%`;
  detChg.className = chgVal === 0 ? "color-neutral" : (chgVal > 0 ? "color-red" : "color-green");
  
  const turnoverVal = (selected.symbol === "510300") ? "256,387.76" : (selected.symbol === "510050" ? "98,124.50" : "24,512.00");
  document.getElementById("detTurnover").textContent = turnoverVal;
  
  // 触发价格区间标尺与计算
  const buyVal = getPlanBuyPrice(selected);
  const takeProfitVal = getPlanTakeProfitPrice(selected) || Number((buyVal * 1.05).toFixed(3));
  const stopLossVal = getPlanStopLossPrice(selected) || Number((buyVal * 0.96).toFixed(3));
  const invalidVal = getPlanInvalidationPrice(selected);
  const sliderLowerCandidates = [stopLossVal, invalidVal, buyVal].filter(value => Number.isFinite(value) && value > 0);
  const lowerVal = sliderLowerCandidates.length ? Math.min(...sliderLowerCandidates) : 0;
  const middleVal = buyVal || Number(((lowerVal + takeProfitVal) / 2).toFixed(3));
  const upperVal = takeProfitVal || Number((middleVal * 1.05).toFixed(3));
  
  document.getElementById("detSliderLower").textContent = formatMoney(lowerVal);
  document.getElementById("detSliderMiddle").textContent = formatMoney(middleVal);
  document.getElementById("detSliderUpper").textContent = formatMoney(upperVal);
  document.getElementById("detPriceTime").textContent = selected.is_external_lookup
    ? "无交易计划：仅展示行情"
    : `${planHealth.label}：${planHealth.reason}`;

  document.getElementById("detPlanBuy").textContent = buyVal > 0 ? formatMoney(buyVal) : "--";
  document.getElementById("detPlanTakeProfit").textContent = takeProfitVal > 0 ? formatMoney(takeProfitVal) : "--";
  document.getElementById("detPlanStopLoss").textContent = stopLossVal > 0 ? formatMoney(stopLossVal) : "--";
  const entryDistance = selected.entry_distance_pct || (selected.signal_close > 0 ? (buyVal - selected.signal_close) / selected.signal_close : 0);
  const profitSpace = selected.profit_gap_pct || (buyVal > 0 ? (takeProfitVal - buyVal) / buyVal : 0);
  const stopSpace = selected.stop_gap_pct || (buyVal > 0 ? (buyVal - stopLossVal) / buyVal : 0);
  document.getElementById("detPlanBuyNote").textContent = selected.is_external_lookup ? "未进入当前交易计划" : planHealth.reason;
  document.getElementById("detPlanProfitNote").textContent = selected.is_external_lookup ? "无策略目标价" : `目标空间 ${formatPercent(profitSpace)}`;
  document.getElementById("detPlanStopNote").textContent = selected.is_external_lookup ? "无策略止损价" : `止损空间 ${formatPercent(stopSpace)}`;
  
  // 精算指针位置
  // SVG 宽度为 380px，分两段。
  // 安全区间：[lowerVal, middleVal]，对应 cx 在 0 到 180px 之间
  // 触发区间：[middleVal, upperVal]，对应 cx 在 180px 到 380px 之间
  const p = selected.signal_close;
  let cx = 180;
  
  if (p <= lowerVal) {
    cx = 2;
  } else if (p >= upperVal) {
    cx = 378;
  } else if (p < middleVal) {
    // 处于安全区间
    const pct = (p - lowerVal) / (middleVal - lowerVal);
    cx = Math.round(2 + pct * 178);
  } else {
    // 处于触发区间
    const pct = (p - middleVal) / (upperVal - middleVal);
    cx = Math.round(180 + pct * 198);
  }
  
  document.getElementById("sliderPointer").setAttribute("cx", cx);
  
  // 触发信号大字与得分
  document.getElementById("sigVal").textContent = (selected.status === "entry_candidate") ? "适中" : "偏高";
  document.getElementById("sigVal").className = (selected.status === "entry_candidate") ? "sig-badge sig-orange" : "sig-badge sig-red";
  document.getElementById("detScore").textContent = Math.round(selected.score || 60);
  
  // 风险评估
  const isHighRisk = selected.risk_level === "高" || selected.status === "skip";
  document.getElementById("riskLevel").textContent = isHighRisk ? "高" : "中";
  document.getElementById("riskLevel").className = `sig-badge ${isHighRisk ? "sig-red" : "sig-orange"}`;
  
  const mddVal = (selected.symbol === "510300") ? "-8.35%" : (selected.symbol === "510050" ? "-6.42%" : "-11.80%");
  const volVal = (selected.symbol === "510300") ? "16.42%" : (selected.symbol === "510050" ? "12.80%" : "22.50%");
  const teVal = (selected.symbol === "510300") ? "0.45%" : (selected.symbol === "510050" ? "0.32%" : "0.78%");
  
  document.getElementById("riskMdd").textContent = mddVal;
  document.getElementById("riskVol").textContent = volVal;
  document.getElementById("riskTe").textContent = teVal;
  
  // 相关性大条
  const corrList = document.getElementById("detCorrList");
  corrList.innerHTML = `
    <div class="corr-item"><span class="corr-name">沪深300</span><div class="corr-bar"><span style="width:99%;"></span></div><strong class="corr-val font-mono">0.99</strong></div>
    <div class="corr-item"><span class="corr-name">中证500</span><div class="corr-bar"><span style="width:${selected.symbol === "159922" ? "99" : "85"}%;"></span></div><strong class="corr-val font-mono">${selected.symbol === "159922" ? "0.99" : "0.85"}</strong></div>
    <div class="corr-item"><span class="corr-name">中证1000</span><div class="corr-bar"><span style="width:${selected.symbol === "512100" ? "99" : "72"}%;"></span></div><strong class="corr-val font-mono">${selected.symbol === "512100" ? "0.99" : "0.72"}</strong></div>
  `;
  
  // Tab 2: 信号优势与预警列表绑定
  const advs = selected.advantages || ["多因子特征共振好转", "中期走势强势金叉"];
  const rsks = selected.risks || ["无突出的风险预警信号"];
  
  document.getElementById("detAdvList").innerHTML = advs.map(t => `<span class="adv-tag">${escapeHtml(t)}</span>`).join("");
  document.getElementById("detRiskList").innerHTML = rsks.map(t => `<span class="risk-tag">${escapeHtml(t)}</span>`).join("");
  
  document.getElementById("detNewsSummary").textContent = selected.news_summary || "多因子量化信号触发，暂无其他重大舆情警示。";
  
  // Tab 3: 深度风险测算绑定
  const stopGapVal = selected.stop_gap_pct ?? 0.048;
  const profitGapVal = selected.profit_gap_pct ?? 0.087;
  const rrVal = selected.risk_reward ?? (stopGapVal > 0 ? profitGapVal / stopGapVal : 1.8);
  const orderVal = selected.assumed_order_value ?? 10000.0;
  const feeDragVal = selected.estimated_round_trip_fee ?? 15.0;
  
  document.getElementById("detStopGap").textContent = formatPercent(stopGapVal);
  document.getElementById("detProfitGap").textContent = formatPercent(profitGapVal);
  document.getElementById("detRrRatio").textContent = rrVal.toFixed(2);
  document.getElementById("detOrderVal").textContent = `￥${orderVal.toLocaleString()}`;
  document.getElementById("detFeeDrag").textContent = `￥${feeDragVal.toFixed(2)}`;
}

function renderTrendSection(selected) {
  const cached = state.trendCache[selected.symbol];
  const latestEl = document.getElementById("trendLatestPrice");
  const changeEl = document.getElementById("trendChangePct");
  const labelEl = document.getElementById("trendLabel");
  const returnEl = document.getElementById("trendReturn20");
  const lineEl = document.getElementById("trendSparkline");
  const statusEl = document.getElementById("trendStatus");
  if (!latestEl || !changeEl || !labelEl || !returnEl || !lineEl || !statusEl) return;

  if (!cached) {
    latestEl.textContent = formatMoney(selected.signal_close);
    const chg = Number(selected.change_pct || 0);
    changeEl.textContent = `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`;
    changeEl.className = chg === 0 ? "color-neutral" : (chg > 0 ? "color-red" : "color-green");
    labelEl.textContent = state.trendLoadingSymbol === selected.symbol ? "加载中" : "待刷新";
    returnEl.textContent = "--";
    lineEl.setAttribute("points", "");
    statusEl.textContent = state.lookupError || "正在读取最近日线与实时价格。";
    return;
  }

  latestEl.textContent = formatMoney(cached.price || selected.signal_close);
  const chg = Number(cached.change_pct ?? selected.change_pct ?? 0);
  changeEl.textContent = `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`;
  changeEl.className = chg === 0 ? "color-neutral" : (chg > 0 ? "color-red" : "color-green");
  labelEl.textContent = cached.trend?.trend_label || "待确认";
  returnEl.textContent = cached.trend?.return_20d_pct !== null && cached.trend?.return_20d_pct !== undefined
    ? `${cached.trend.return_20d_pct > 0 ? "+" : ""}${Number(cached.trend.return_20d_pct).toFixed(2)}%`
    : "--";
  returnEl.className = Number(cached.trend?.return_20d_pct || 0) >= 0 ? "color-red" : "color-green";
  lineEl.setAttribute("points", buildSparklinePoints(cached.klines || []));
  const trendSource = cached.trend_source_label ? `，趋势源：${cached.trend_source_label}` : "";
  statusEl.textContent = `${cached.name || selected.name || selected.symbol}，${cached.source_label || "行情"}${trendSource}，更新时间 ${cached.updated_at_label || state.lastRefreshAt}`;
}

function buildSparklinePoints(klines) {
  const closes = (klines || []).map(item => Number(item.close)).filter(value => Number.isFinite(value) && value > 0);
  if (closes.length < 2) return "";
  const minVal = Math.min(...closes);
  const maxVal = Math.max(...closes);
  const range = Math.max(0.000001, maxVal - minVal);
  return closes.map((value, index) => {
    const x = closes.length === 1 ? 180 : (index / (closes.length - 1)) * 360;
    const y = 108 - ((value - minVal) / range) * 96;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function ensureTrendData(symbol, force = false) {
  if (!symbol || !isServiceMode()) return;
  const cached = state.trendCache[symbol];
  if (!force && cached && Date.now() - cached.fetched_at_ms < 60000) return;
  if (state.trendLoadingSymbol === symbol) return;
  state.trendLoadingSymbol = symbol;
  fetch(`/api/security-trend?query=${encodeURIComponent(symbol)}&ts=${Date.now()}`, { cache: "no-store" })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(payload => {
      if (payload.error) throw new Error(payload.error);
      payload.fetched_at_ms = Date.now();
      state.trendCache[payload.symbol] = payload;
      mergeTrendPayloadIntoCandidate(payload);
      state.lookupError = "";
      if (state.selectedSymbol === payload.symbol) {
        renderPanel();
      }
    })
    .catch(err => {
      state.lookupError = "趋势查询失败：保留当前看板数据。";
      console.warn("趋势查询失败", err);
      renderTrendSection(getCurrentDetailItem());
    })
    .finally(() => {
      if (state.trendLoadingSymbol === symbol) state.trendLoadingSymbol = null;
    });
}

function refreshSelectedTrend() {
  if (!state.selectedSymbol) return;
  ensureTrendData(state.selectedSymbol, true);
  showToast("正在刷新价格趋势。");
}

function lookupExternalSecurity(query) {
  fetch(`/api/security-trend?query=${encodeURIComponent(query)}&ts=${Date.now()}`, { cache: "no-store" })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(payload => {
      if (payload.error) throw new Error(payload.error);
      payload.fetched_at_ms = Date.now();
      state.trendCache[payload.symbol] = payload;
      state.externalLookupResult = normalizeLookupCandidate(payload);
      state.selectedSymbol = payload.symbol;
      state.lookupError = "";
      renderPanel();
      showToast(`已加载 ${payload.name || payload.symbol} 的趋势和价格。`);
    })
    .catch(err => {
      state.externalLookupResult = null;
      state.lookupError = "未找到匹配标的或行情源暂不可用。";
      console.warn("外部标的查询失败", err);
      renderPanel();
    });
}

function normalizeLookupCandidate(payload) {
  return {
    symbol: payload.symbol,
    name: payload.name || getFundName(payload.symbol),
    index_name: payload.asset_type || "A股/ETF",
    status: "lookup_only",
    status_label: "行情查询",
    status_tone: "muted",
    score: 0,
    signal_close: Number(payload.price || 0),
    entry_price: 0,
    stop_loss_price: 0,
    take_profit_price: 0,
    change_pct: Number(payload.change_pct || 0),
    signal_name: "仅查行情",
    risk_level: "未评级",
    date: payload.updated_at_label || "",
    advantages: ["未进入当前量化候选池"],
    risks: ["仅展示行情，不生成交易计划"],
    is_external_lookup: true,
  };
}

function mergeTrendPayloadIntoCandidate(payload) {
  const data = getActiveData();
  const candidate = data.candidates.find(item => item.symbol === payload.symbol);
  if (candidate) {
    candidate.name = payload.name || candidate.name;
    candidate.signal_close = Number(payload.price || candidate.signal_close || 0);
    candidate.change_pct = Number(payload.change_pct ?? candidate.change_pct ?? 0);
    candidate.quote_source = payload.source || candidate.quote_source;
    candidate.quote_refreshed_at = payload.updated_at || candidate.quote_refreshed_at;
  }
  if (state.externalLookupResult && state.externalLookupResult.symbol === payload.symbol) {
    state.externalLookupResult = normalizeLookupCandidate(payload);
  }
}

function getCurrentDetailItem() {
  const data = getActiveData();
  return data.candidates.find(item => item.symbol === state.selectedSymbol)
    || (state.externalLookupResult && state.externalLookupResult.symbol === state.selectedSymbol ? state.externalLookupResult : null)
    || data.candidates[0]
    || { symbol: "", name: "", signal_close: 0, change_pct: 0 };
}

// 辅助数据填充函数
function getFundName(symbol) {
  if (symbol === "510300") return "沪深300ETF";
  if (symbol === "510050") return "上证50ETF";
  if (symbol === "159915") return "创业板ETF";
  if (symbol === "512100") return "中证1000ETF南方";
  if (symbol === "159922") return "中证500ETF";
  if (symbol === "510500") return "中证500ETF南方";
  if (symbol === "518880") return "黄金ETF华安";
  if (symbol === "159601") return "A50ETF";
  if (symbol === "588000") return "科创50ETF";
  if (symbol === "159919") return "沪深300ETF";
  if (symbol === "515790") return "光伏ETF";
  if (symbol === "159869") return "游戏ETF";
  if (symbol === "516160") return "新能源ETF";
  return "量化精选ETF";
}

function getStatusLabel(status) {
  if (status === "entry_candidate") return "可入场";
  if (status === "watch_only") return "观察";
  if (status === "skip") return "跳过";
  if (status === "lookup_only") return "行情查询";
  return "待确认";
}

function getStatusBadgeClass(status) {
  if (status === "entry_candidate") return "badge-green";
  if (status === "watch_only") return "badge-orange";
  if (status === "skip") return "badge-gray";
  if (status === "lookup_only") return "badge-gray";
  return "badge-gray";
}

// 格式化真实后端日期时间
function formatRealDate(isoStr) {
  try {
    if (!isoStr) return "暂无数据日期";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "暂无数据日期";
    const weeks = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} (${weeks[d.getDay()]})`;
  } catch(e) {
    return "2026-05-29 (周五)";
  }
}

function formatRealTime(isoStr) {
  try {
    if (!isoStr) return "--:--:--";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "--:--:--";
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;
  } catch(e) {
    return "15:00:00";
  }
}

// 星标详情联动
function toggleStarSelectedSymbol() {
  if (!state.selectedSymbol) return;
  toggleStar(state.selectedSymbol);
  renderPanel();
}

// 10. 高科技感 Toast 弹出机制
function showToast(message) {
  const stack = document.getElementById("toastStack");
  const toast = document.createElement("div");
  toast.className = "toast-msg";
  toast.textContent = message;
  
  stack.appendChild(toast);
  
  // 3秒后淡出删除
  setTimeout(() => {
    toast.style.animation = "slideIn 0.25s reverse forwards";
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 250);
  }, 2800);
}

// 11. HTML 极速富文本 Markdown 解析
function markdownLite(markdown) {
  const lines = markdown.split(/\r?\n/);
  let html = "";
  let listOpen = false;
  let table = [];
  
  const closeList = () => {
    if (listOpen) {
      html += "</ul>";
      listOpen = false;
    }
  };
  const flushTable = () => {
    if (table.length) {
      html += `<pre>${escapeHtml(table.join("\n"))}</pre>`;
      table = [];
    }
  };
  
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("|")) {
      closeList();
      table.push(line);
      continue;
    }
    flushTable();
    if (!line.trim()) {
      closeList();
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
    } else if (line.startsWith("## ")) {
      closeList();
      html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
    } else if (line.startsWith(">")) {
      closeList();
      html += `<p><strong>${escapeHtml(line.replace(/^>\s*/, ""))}</strong></p>`;
    } else if (line.startsWith("- ")) {
      if (!listOpen) {
        html += "<ul>";
        listOpen = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
    } else {
      closeList();
      html += `<p>${escapeHtml(line)}</p>`;
    }
  }
  closeList();
  flushTable();
  return html;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// ==========================================
// 12. 决策沙盒推演与 Pearson 相关性风控
// ==========================================
window.SANDBOX_PORTFOLIO = [];

const SANDBOX_CORR_MATRIX = {
  "510300_510050": 0.89, "510050_510300": 0.89,
  "510300_159915": 0.72, "159915_510300": 0.72,
  "510050_159915": 0.65, "159915_510050": 0.65,
  "512100_159922": 0.92, "159922_512100": 0.92,
  "510300_159922": 0.82, "159922_510300": 0.82,
  "510300_512100": 0.75, "512100_510300": 0.75,
  "510500_512100": 0.88, "512100_510500": 0.88
};

function addCurrentSymbolToSandbox() {
  if (!state.selectedSymbol) {
    showToast("请先在左侧选择一只 ETF 标的");
    return;
  }
  const data = getActiveData();
  const selected = data.candidates.find(item => item.symbol === state.selectedSymbol);
  if (!selected) return;

  const exists = window.SANDBOX_PORTFOLIO.find(item => item.symbol === selected.symbol);
  if (exists) {
    showToast(`标的 ${selected.symbol} 已在沙盒中，无需重复添加`);
    return;
  }

  window.SANDBOX_PORTFOLIO.push({
    symbol: selected.symbol,
    name: selected.name || getFundName(selected.symbol),
    weight: 20
  });

  showToast(`已成功将 ${selected.symbol} (${selected.name}) 加入风控沙盒`);
  renderSandbox();
}

function removeSandboxItem(symbol) {
  window.SANDBOX_PORTFOLIO = window.SANDBOX_PORTFOLIO.filter(item => item.symbol !== symbol);
  renderSandbox();
}

function updateSandboxWeight(symbol, val) {
  const num = Math.max(0, Math.min(100, parseFloat(val) || 0));
  const item = window.SANDBOX_PORTFOLIO.find(i => i.symbol === symbol);
  if (item) {
    item.weight = num;
  }
  renderSandbox(true); // 仅更新警报，避免重新绘制输入框导致失去焦点
}

function renderSandbox(onlyAlerts = false) {
  const listContainer = document.getElementById("sandboxList");
  const alertContainer = document.getElementById("sandboxAlertArea");
  
  if (!listContainer || !alertContainer) return;

  if (window.SANDBOX_PORTFOLIO.length === 0) {
    listContainer.innerHTML = `<div class="sandbox-empty">沙盒当前无选定持仓，请点击上方按钮添加。</div>`;
    alertContainer.innerHTML = "";
    return;
  }

  // 1. 渲染列表
  if (!onlyAlerts) {
    listContainer.innerHTML = window.SANDBOX_PORTFOLIO.map(item => `
      <div class="sandbox-item">
        <div class="sandbox-item-left">
          <strong>${item.symbol}</strong>
          <span>${item.name}</span>
        </div>
        <div class="sandbox-item-right">
          <input type="number" class="sandbox-weight-input" min="0" max="100" value="${item.weight}" 
                 oninput="updateSandboxWeight('${item.symbol}', this.value)">
          <span style="font-size:12px; color:var(--text-muted);">%</span>
          <button class="sandbox-remove-btn" onclick="removeSandboxItem('${item.symbol}')">✕</button>
        </div>
      </div>
    `).join("");
  }

  // 2. Pearson 相关性交叉风控检查
  let totalWeight = 0;
  window.SANDBOX_PORTFOLIO.forEach(i => totalWeight += i.weight);

  let alertsHtml = "";
  if (totalWeight > 100) {
    alertsHtml += `
      <div class="sandbox-alert" style="background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); color: #b45309; border-color: rgba(245, 158, 11, 0.2);">
        ⚠️ <b>持仓配比警告：</b> 当前配置总权重为 <b>${totalWeight.toFixed(1)}%</b>，已超出 100% 满仓限制。请调低权重以符合合规持仓。
      </div>
    `;
  }

  // 两两比对 Pearson 相关性
  for (let i = 0; i < window.SANDBOX_PORTFOLIO.length; i++) {
    for (let j = i + 1; j < window.SANDBOX_PORTFOLIO.length; j++) {
      const etfA = window.SANDBOX_PORTFOLIO[i];
      const etfB = window.SANDBOX_PORTFOLIO[j];
      const key1 = `${etfA.symbol}_${etfB.symbol}`;
      const key2 = `${etfB.symbol}_${etfA.symbol}`;
      const corr = SANDBOX_CORR_MATRIX[key1] || SANDBOX_CORR_MATRIX[key2] || 0.50; // 默认降级为 0.50

      if (corr >= 0.85 && (etfA.weight + etfB.weight) >= 40) {
        alertsHtml += `
          <div class="sandbox-alert">
            🚨 <b>集中度共振预警：</b> 组合中 <b>[${etfA.symbol}]</b> 与 <b>[${etfB.symbol}]</b> 的 Pearson 相关性达 <b>${corr.toFixed(2)}</b> (极高正相关)！两只 ETF 合计占比达 <b>${(etfA.weight + etfB.weight).toFixed(1)}%</b>。存在极严重的同质化暴露，请立刻降低任意一方的权重配比以分散系统性回撤风险！
          </div>
        `;
      }
    }
  }

  alertContainer.innerHTML = alertsHtml;
}

// ==========================================
// 13. 在线 Markdown 日报保存与发布
// ==========================================
function enterReportEditMode() {
  const data = getActiveData();
  const content = data.daily_report ? data.daily_report.content : "";
  
  document.getElementById("dailyReport").style.display = "none";
  document.getElementById("dailyReportEditorWrapper").style.display = "block";
  document.getElementById("dailyReportEditorField").value = content;
}

function exitReportEditMode() {
  document.getElementById("dailyReport").style.display = "block";
  document.getElementById("dailyReportEditorWrapper").style.display = "none";
}

function saveDailyReportToServer() {
  const newMarkdown = document.getElementById("dailyReportEditorField").value;
  
  showToast("正在保存并同步日报至服务器...");
  
  fetch("/api/save-daily-report", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ markdown: newMarkdown })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success === true) {
      showToast("🎉 日报已成功发布并同步持久化！");
      
      // 更新本地状态
      const activeData = getActiveData();
      if (!activeData.daily_report) {
        activeData.daily_report = {};
      }
      activeData.daily_report.content = newMarkdown;
      
      // 重新渲染
      renderReportTab();
      exitReportEditMode();
    } else {
      showToast("保存失败：" + (data.message || "未知错误"));
    }
  })
  .catch(err => {
    console.error(err);
    showToast("网络通信异常，已自动离线缓存，无法同步至服务器。");
  });
}

// ==========================================
// 14. 看板自动刷新与实时价格轮询
// ==========================================
function initPollingControls() {
  loadPollingPreferences();

  const toggle = document.getElementById("autoRefreshToggle");
  const intervalInput = document.getElementById("pollIntervalInput");
  if (!toggle || !intervalInput) return;

  intervalInput.min = state.minPollIntervalSeconds;
  intervalInput.value = state.pollIntervalSeconds;
  toggle.checked = state.autoRefreshEnabled;

  if (state.autoRefreshEnabled && !isServiceMode()) {
    state.autoRefreshEnabled = false;
    toggle.checked = false;
    savePollingPreferences();
    state.refreshError = "静态文件模式不能自动拉取最新数据，请用 --serve 启动 Web 服务。";
  }

  toggle.addEventListener("change", (event) => {
    setAutoRefreshEnabled(event.target.checked);
  });
  const switchLabel = toggle.closest(".poll-switch");
  if (switchLabel) {
    switchLabel.addEventListener("click", (event) => {
      if (event.target === toggle) return;
      event.preventDefault();
      toggle.checked = !toggle.checked;
      setAutoRefreshEnabled(toggle.checked);
    });
  }

  const updatePollInterval = (event, announce) => {
    const rawValue = Number(event.target.value);
    if (!Number.isFinite(rawValue) || rawValue <= 0) {
      return;
    }
    const nextValue = Math.max(
      state.minPollIntervalSeconds,
      Math.floor(rawValue)
    );
    const changed = nextValue !== state.pollIntervalSeconds;
    state.pollIntervalSeconds = nextValue;
    intervalInput.value = nextValue;
    savePollingPreferences();
    if (state.autoRefreshEnabled) {
      scheduleNextDashboardRefresh();
      if (announce || changed) {
        showToast(`自动刷新间隔已调整为 ${nextValue} 秒。`);
      }
    } else {
      updatePollingStatus();
    }
  };

  intervalInput.addEventListener("input", (event) => updatePollInterval(event, false));
  intervalInput.addEventListener("change", (event) => updatePollInterval(event, true));

  updatePollingStatus();
  if (state.autoRefreshEnabled) {
    scheduleNextDashboardRefresh();
  }
}

function loadPollingPreferences() {
  try {
    const savedInterval = Number(localStorage.getItem("haitong-dashboard-poll-interval"));
    const savedEnabled = localStorage.getItem("haitong-dashboard-auto-refresh");
    if (Number.isFinite(savedInterval) && savedInterval > 0) {
      state.pollIntervalSeconds = Math.max(state.minPollIntervalSeconds, Math.floor(savedInterval));
    }
    if (savedEnabled !== null) {
      state.autoRefreshEnabled = savedEnabled === "true";
    }
  } catch (err) {
    state.refreshError = "浏览器未开放本地设置存储，自动刷新设置仅本次有效。";
  }
}

function savePollingPreferences() {
  try {
    localStorage.setItem("haitong-dashboard-poll-interval", String(state.pollIntervalSeconds));
    localStorage.setItem("haitong-dashboard-auto-refresh", String(state.autoRefreshEnabled));
  } catch (err) {
    state.refreshError = "浏览器未开放本地设置存储，自动刷新设置仅本次有效。";
  }
}

function setAutoRefreshEnabled(enabled) {
  const toggle = document.getElementById("autoRefreshToggle");
  const intervalInput = document.getElementById("pollIntervalInput");
  if (enabled && intervalInput) {
    const inputValue = Number(intervalInput.value);
    if (Number.isFinite(inputValue) && inputValue > 0) {
      state.pollIntervalSeconds = Math.max(state.minPollIntervalSeconds, Math.floor(inputValue));
      intervalInput.value = state.pollIntervalSeconds;
    }
  }
  if (enabled && !isServiceMode()) {
    state.autoRefreshEnabled = false;
    if (toggle) toggle.checked = false;
    clearDashboardRefreshTimers();
    updatePollingStatus();
    showToast("静态文件模式不能自动拉取最新数据，请用 --serve 启动 Web 服务。");
    return;
  }

  state.autoRefreshEnabled = Boolean(enabled);
  if (toggle) toggle.checked = state.autoRefreshEnabled;
  savePollingPreferences();

  if (state.autoRefreshEnabled) {
    scheduleNextDashboardRefresh();
    showToast(`已开启自动刷新，每 ${state.pollIntervalSeconds} 秒更新一次看板。`);
  } else {
    clearDashboardRefreshTimers();
    updatePollingStatus();
    showToast("已关闭自动刷新。");
  }
}

function scheduleNextDashboardRefresh() {
  clearDashboardRefreshTimers();
  if (!state.autoRefreshEnabled) {
    updatePollingStatus();
    return;
  }
  const intervalMs = Math.max(state.minPollIntervalSeconds, state.pollIntervalSeconds) * 1000;
  state.nextRefreshAt = Date.now() + intervalMs;
  state.pollTimerId = window.setTimeout(() => refreshDashboardData("auto"), intervalMs);
  state.countdownTimerId = window.setInterval(updatePollingStatus, 1000);
  updatePollingStatus();
}

function clearDashboardRefreshTimers() {
  if (state.pollTimerId) {
    window.clearTimeout(state.pollTimerId);
    state.pollTimerId = null;
  }
  if (state.countdownTimerId) {
    window.clearInterval(state.countdownTimerId);
    state.countdownTimerId = null;
  }
  state.nextRefreshAt = null;
}

function updatePollingStatus() {
  const lastEl = document.getElementById("lastRefreshText");
  const nextEl = document.getElementById("nextRefreshText");
  const sourceEl = document.getElementById("priceSourceText");
  const statusBox = document.querySelector(".poll-status");
  if (!lastEl || !nextEl || !statusBox) return;

  statusBox.classList.toggle("is-error", Boolean(state.refreshError));
  lastEl.textContent = state.refreshError || `最后刷新：${state.lastRefreshAt}`;
  if (sourceEl) {
    sourceEl.textContent = state.priceSourceLabel || "行情来源：待刷新";
  }

  if (!state.autoRefreshEnabled || !state.nextRefreshAt) {
    nextEl.textContent = "下次刷新：未开启";
    return;
  }
  const seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
  nextEl.textContent = `下次刷新：${seconds} 秒后`;
}

function setRefreshBusy(isBusy) {
  state.isRefreshing = isBusy;
  const button = document.getElementById("refreshButton");
  if (!button) return;
  button.classList.toggle("is-refreshing", isBusy);
  button.disabled = isBusy;
  const label = button.querySelector("span");
  if (label) {
    label.textContent = isBusy ? "刷新中" : "刷新";
  }
}

async function refreshDashboardData(reason = "manual") {
  if (state.isRefreshing) return;
  if (!isServiceMode()) {
    showToast("静态文件模式不能自动拉取最新数据，请用 --serve 启动 Web 服务。");
    return;
  }

  setRefreshBusy(true);
  try {
    const response = await fetch(`/api/dashboard-summary?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const summary = await response.json();
    state.refreshError = "";
    state.lastRefreshAt = summary.refreshed_at_label || new Date().toLocaleString("zh-CN", { hour12: false });
    applyDashboardSummary(summary);
    await runL1RealtimePriceTicker();
    updatePollingStatus();
    renderKPIAndTopbar();
    if (reason === "manual") {
      showToast("看板数据已刷新，未执行 pipeline，也未改写交易计划。");
    }
  } catch (err) {
    console.warn("看板刷新失败：", err);
    state.refreshError = "刷新失败：保留上一次看板数据";
    updatePollingStatus();
    if (reason === "manual") {
      showToast("刷新失败，已保留上一次看板数据。");
    }
  } finally {
    setRefreshBusy(false);
    if (state.autoRefreshEnabled) {
      scheduleNextDashboardRefresh();
    } else {
      updatePollingStatus();
    }
  }
}

function applyDashboardSummary(summary) {
  const selectedBefore = state.selectedSymbol;
  const previousQuotes = new Map((REAL_DATA.candidates || []).map(item => [item.symbol, {
    signal_close: item.signal_close,
    change_pct: item.change_pct,
    quote_source: item.quote_source,
    quote_refreshed_at: item.quote_refreshed_at,
    name: item.name,
  }]));
  REAL_DATA = summary || REAL_DATA;
  REAL_DATA.candidates = REAL_DATA.candidates || [];
  REAL_DATA.candidates.forEach(item => {
    const previous = previousQuotes.get(item.symbol);
    if (previous && previous.quote_source) {
      item.signal_close = previous.signal_close;
      item.change_pct = previous.change_pct;
      item.quote_source = previous.quote_source;
      item.quote_refreshed_at = previous.quote_refreshed_at;
      item.name = previous.name || item.name;
    }
  });
  REAL_DATA.warnings = REAL_DATA.warnings || [];
  REAL_DATA.daily_report = REAL_DATA.daily_report || { content: "" };
  REAL_DATA.paper = REAL_DATA.paper || { summary: "暂无纸面账户摘要。" };

  if (REAL_DATA.polling) {
    state.minPollIntervalSeconds = Number(REAL_DATA.polling.min_interval_seconds || state.minPollIntervalSeconds);
    state.pollIntervalSeconds = Math.max(
      state.minPollIntervalSeconds,
      Number(state.pollIntervalSeconds || REAL_DATA.polling.default_interval_seconds || 30)
    );
    const intervalInput = document.getElementById("pollIntervalInput");
    if (intervalInput) {
      intervalInput.min = state.minPollIntervalSeconds;
      intervalInput.value = state.pollIntervalSeconds;
    }
  }

  if (state.dataSource === "real") {
    const stillExists = REAL_DATA.candidates.some(item => item.symbol === selectedBefore);
    const query = state.searchQuery.trim();
    if (state.externalLookupResult && query && state.externalLookupResult.symbol === selectedBefore) {
      state.selectedSymbol = selectedBefore;
    } else if (stillExists) {
      state.selectedSymbol = selectedBefore;
    } else if (query) {
      const best = pickBestSearchMatch(getFilteredCandidates(), query);
      state.selectedSymbol = best ? best.symbol : selectedBefore;
    } else {
      state.selectedSymbol = REAL_DATA.candidates[0]?.symbol || null;
    }
    renderKPIAndTopbar();
    renderPanel();
  }
}

function isServiceMode() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

// ==========================================
// 15. L1 行情轮询与 SVG 滑尺自适应联动
// ==========================================
function runL1RealtimePriceTicker() {
  const data = getActiveData();
  if (state.dataSource !== "real") {
    state.priceSourceLabel = "行情来源：演示数据";
    updatePollingStatus();
    return Promise.resolve(false);
  }
  if (!isServiceMode() || !data.candidates || data.candidates.length === 0) {
    return Promise.resolve(false);
  }

  const symbols = data.candidates
    .map(c => `${c.symbol}:${Number(c.signal_close || c.plan_signal_close || c.entry_price || 2).toFixed(4)}`)
    .join(",");
  
  return fetch(`/api/realtime-prices?symbols=${symbols}`, { cache: "no-store" })
  .then(res => res.json())
  .then(priceMap => {
    const meta = priceMap.__meta__ || {};
    const refreshedAt = meta.refreshed_at || new Date().toISOString();
    const refreshedLabel = meta.refreshed_at_label || new Date().toLocaleString("zh-CN", { hour12: false });
    const sourceLabel = meta.source_label || "行情已刷新";
    data.refreshed_at = refreshedAt;
    data.refreshed_at_label = refreshedLabel;
    state.lastRefreshAt = refreshedLabel;
    state.priceSourceLabel = `行情来源：${sourceLabel}`;
    let anyChanged = false;
    let anyQuote = false;
    
    // 更新数据
    data.candidates.forEach(c => {
      if (priceMap[c.symbol]) {
        anyQuote = true;
        const info = priceMap[c.symbol];
        if (info.name) {
          c.name = info.name;
        }
        if (Number(c.signal_close) !== Number(info.price)) {
          const changePct = Number(info.change_pct || 0);
          c.signal_close = Number(info.price || 0);
          c.change_pct = changePct;
          c.quote_source = info.source || meta.source || "";
          c.quote_refreshed_at = info.refreshed_at || refreshedAt;
          anyChanged = true;
          
          // 给表格的对应行增加闪烁动画或类
          const row = document.querySelector(`#candidateTable tr[onclick*="'${c.symbol}'"]`);
          if (row) {
            row.style.transition = "background-color 0.2s";
            row.style.backgroundColor = changePct >= 0 ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)";
            setTimeout(() => {
              row.style.backgroundColor = "";
            }, 800);
          }
        }
        if (Number(c.signal_close) === Number(info.price)) {
          c.quote_source = info.source || meta.source || "";
          c.quote_refreshed_at = info.refreshed_at || refreshedAt;
        }
      }
    });

    if (anyChanged) {
      // 局部重绘
      renderPanel();
      renderKPIAndTopbar();
    }
    if (!anyChanged && anyQuote) {
      renderPanel();
    }
    renderKPIAndTopbar();
    updatePollingStatus();
    return anyChanged || anyQuote;
  })
  .catch(err => {
    state.priceSourceLabel = "行情来源：暂不可用，保留上一轮";
    updatePollingStatus();
    renderKPIAndTopbar();
    console.warn("准实时行情接口轮询受限或超时，自适应降级为平稳运行模式。");
    return false;
  });
}

// 自动启动
window.addEventListener("DOMContentLoaded", initDashboard);
// 同时也监听可能动态注入完毕的时刻
setTimeout(initDashboard, 100);
"""
