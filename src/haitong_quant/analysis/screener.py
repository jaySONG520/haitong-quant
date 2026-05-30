from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from haitong_quant.analysis.factors import (
    atr_pct,
    moving_average,
    period_return,
    rsi,
    scale,
    sentiment_points,
    volume_ratio as factor_volume_ratio,
)
from haitong_quant.analysis.news import NewsScore
from haitong_quant.models import Bar


@dataclass(frozen=True)
class TradingRuleSuggestion:
    entry_trigger_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    round_trip_fee_pct: float
    minimum_order_value_for_30bps_fee_drag: float
    rule_text: str


@dataclass(frozen=True)
class CandidateScore:
    symbol: str
    close: float
    total_score: float
    short_term_bias: str
    medium_term_bias: str
    advantages: tuple[str, ...]
    risks: tuple[str, ...]
    metrics: dict[str, float]
    news_score: float
    news_summary: str
    news_url: str
    trading_rules: TradingRuleSuggestion


class KlineNewsScreener:
    def __init__(
        self,
        min_trade_fee: float = 5.0,
        stock_sell_tax_bps: float = 5.0,
        default_order_value: float = 10000.0,
        min_score: float = 55.0,
    ) -> None:
        self.min_trade_fee = min_trade_fee
        self.stock_sell_tax_bps = stock_sell_tax_bps
        self.default_order_value = default_order_value
        self.min_score = min_score

    def screen(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        news_by_symbol: dict[str, NewsScore] | None = None,
        top_n: int = 5,
    ) -> list[CandidateScore]:
        news_by_symbol = news_by_symbol or {}
        candidates: list[CandidateScore] = []
        for symbol, bars in bars_by_symbol.items():
            ordered = sorted(bars, key=lambda item: item.date)
            if len(ordered) < 21:
                continue
            candidate = self._score_symbol(symbol, ordered, news_by_symbol.get(symbol))
            if candidate.total_score >= self.min_score:
                candidates.append(candidate)
        candidates.sort(key=lambda item: item.total_score, reverse=True)
        return candidates[:top_n]

    def _score_symbol(
        self,
        symbol: str,
        bars: list[Bar],
        news: NewsScore | None,
    ) -> CandidateScore:
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        close = closes[-1]
        ret5 = period_return(closes, 5)
        ret20 = period_return(closes, 20)
        ma5 = moving_average(closes, 5)
        ma20 = moving_average(closes, 20)
        ma60 = moving_average(closes, 60)
        rsi14 = rsi(closes, 14)
        atr14_pct = atr_pct(bars, 14)
        volume_ratio = factor_volume_ratio(volumes, 5, 20)
        drawdown20 = close / max(closes[-20:]) - 1.0
        news_score = news.score if news else 0.0

        trend_points = 0.0
        if close > ma20:
            trend_points += 35.0
        if ma20 >= ma60:
            trend_points += 30.0
        if ma5 >= ma20:
            trend_points += 20.0
        if drawdown20 > -0.08:
            trend_points += 15.0

        short_points = scale(ret5, low=-0.05, high=0.08)
        medium_points = scale(ret20, low=-0.08, high=0.20)
        rsi_points = 100.0 if 45.0 <= rsi14 <= 70.0 else 70.0 if 35.0 <= rsi14 <= 80.0 else 30.0
        volume_points = scale(volume_ratio, low=0.6, high=1.8)
        news_points = sentiment_points(news)
        total_score = (
            short_points * 0.25
            + medium_points * 0.25
            + trend_points * 0.20
            + rsi_points * 0.10
            + volume_points * 0.10
            + news_points * 0.10
        )

        advantages = _advantages(
            close=close,
            ma20=ma20,
            ma60=ma60,
            ret5=ret5,
            ret20=ret20,
            rsi14=rsi14,
            volume_ratio=volume_ratio,
            news_score=news_score,
            has_news=bool(news),
        )
        risks = _risks(
            close=close,
            ma20=ma20,
            ret5=ret5,
            ret20=ret20,
            rsi14=rsi14,
            atr14_pct=atr14_pct,
            drawdown20=drawdown20,
            news_score=news_score,
            has_news=bool(news),
        )
        rules = self._rules(close, atr14_pct)
        short_bias = _bias(total_score, ret5, close > ma20, news_score)
        medium_bias = _bias(total_score, ret20, ma20 >= ma60, news_score)

        return CandidateScore(
            symbol=symbol,
            close=round(close, 4),
            total_score=round(total_score, 2),
            short_term_bias=short_bias,
            medium_term_bias=medium_bias,
            advantages=tuple(advantages),
            risks=tuple(risks),
            metrics={
                "ret5": round(ret5, 6),
                "ret20": round(ret20, 6),
                "ma5": round(ma5, 4),
                "ma20": round(ma20, 4),
                "ma60": round(ma60, 4),
                "rsi14": round(rsi14, 2),
                "atr14_pct": round(atr14_pct, 6),
                "volume_ratio_5_20": round(volume_ratio, 4),
                "drawdown20": round(drawdown20, 6),
            },
            news_score=round(news_score, 3),
            news_summary=news.summary if news else "no reviewed recent-news score supplied",
            news_url=news.url if news else "",
            trading_rules=rules,
        )

    def _rules(self, close: float, atr14_pct: float) -> TradingRuleSuggestion:
        round_trip_fee_pct = (
            2 * self.min_trade_fee / self.default_order_value
            + self.stock_sell_tax_bps / 10000.0
        )
        entry_trigger_pct = max(0.01, min(0.035, atr14_pct * 0.5 + round_trip_fee_pct))
        stop_loss_pct = max(0.04, min(0.12, atr14_pct * 2.0 + round_trip_fee_pct))
        take_profit_pct = max(stop_loss_pct * 1.8, round_trip_fee_pct + 0.04)
        trailing_stop_pct = max(0.03, min(0.10, atr14_pct * 1.5))
        min_order = 2 * self.min_trade_fee / 0.003
        rule_text = (
            "Research rule: consider entry only if the candidate still passes "
            f"the score threshold and price breaks {entry_trigger_pct:.2%} above "
            f"the signal close; stop loss at {stop_loss_pct:.2%} below fill; "
            f"take profit around {take_profit_pct:.2%} or use a "
            f"{trailing_stop_pct:.2%} trailing stop after profit; skip trades "
            "below the minimum-fee-friendly order value."
        )
        return TradingRuleSuggestion(
            entry_trigger_pct=round(entry_trigger_pct, 6),
            stop_loss_pct=round(stop_loss_pct, 6),
            take_profit_pct=round(take_profit_pct, 6),
            trailing_stop_pct=round(trailing_stop_pct, 6),
            round_trip_fee_pct=round(round_trip_fee_pct, 6),
            minimum_order_value_for_30bps_fee_drag=round(min_order, 2),
            rule_text=rule_text,
        )


def _return(closes: list[float], days: int) -> float:
    if len(closes) <= days or closes[-1 - days] <= 0:
        return 0.0
    return closes[-1] / closes[-1 - days] - 1.0


def _ma(values: list[float], days: int) -> float:
    window = values[-min(days, len(values)) :]
    return mean(window)


def _rsi(closes: list[float], days: int) -> float:
    if len(closes) <= days:
        return 50.0
    gains = []
    losses = []
    for prev, current in zip(closes[-days - 1 : -1], closes[-days:]):
        change = current - prev
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _atr_pct(bars: list[Bar], days: int) -> float:
    if len(bars) <= 1:
        return 0.0
    window = bars[-min(days, len(bars) - 1) :]
    true_ranges = []
    previous_close = bars[-len(window) - 1].close
    for bar in window:
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
        previous_close = bar.close
    close = bars[-1].close
    return mean(true_ranges) / close if close > 0 else 0.0


def _volume_ratio(volumes: list[float], short_days: int, long_days: int) -> float:
    if not volumes or all(volume == 0 for volume in volumes):
        return 1.0
    short = mean(volumes[-min(short_days, len(volumes)) :])
    long = mean(volumes[-min(long_days, len(volumes)) :])
    return short / long if long else 1.0


def _scale(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return (value - low) / (high - low) * 100.0


def _bias(score: float, momentum: float, trend_ok: bool, news_score: float) -> str:
    if score >= 70 and momentum > 0 and trend_ok and news_score >= 0:
        return "rule_constructive"
    if score >= 55 and momentum > 0:
        return "rule_watchlist"
    if momentum < 0 or score < 45:
        return "rule_weak"
    return "rule_neutral"


def _advantages(**kwargs: float | bool) -> list[str]:
    advantages: list[str] = []
    if kwargs["ret5"] > 0:
        advantages.append("5-day momentum is positive")
    if kwargs["ret20"] > 0:
        advantages.append("20-day momentum is positive")
    if kwargs["close"] > kwargs["ma20"]:
        advantages.append("latest close is above MA20")
    if kwargs["ma20"] >= kwargs["ma60"]:
        advantages.append("medium trend is not below long trend")
    if 45 <= kwargs["rsi14"] <= 70:
        advantages.append("RSI is in a constructive, not extreme, zone")
    if kwargs["volume_ratio"] >= 1.0:
        advantages.append("recent volume is above 20-day average")
    if kwargs["has_news"] and kwargs["news_score"] > 0:
        advantages.append("reviewed recent-news score is positive")
    if not kwargs["has_news"]:
        advantages.append("news input missing; K-line-only candidate")
    return advantages


def _risks(**kwargs: float | bool) -> list[str]:
    risks: list[str] = []
    if kwargs["ret5"] < 0:
        risks.append("5-day momentum is negative")
    if kwargs["ret20"] < 0:
        risks.append("20-day momentum is negative")
    if kwargs["close"] < kwargs["ma20"]:
        risks.append("latest close is below MA20")
    if kwargs["rsi14"] > 75:
        risks.append("RSI is high; chasing risk is elevated")
    if kwargs["atr14_pct"] > 0.06:
        risks.append("ATR volatility is high")
    if kwargs["drawdown20"] < -0.10:
        risks.append("price is still more than 10% below recent high")
    if kwargs["has_news"] and kwargs["news_score"] < 0:
        risks.append("reviewed recent-news score is negative")
    if not kwargs["has_news"]:
        risks.append("recent-news score is missing; do not treat as news-confirmed")
    return risks
