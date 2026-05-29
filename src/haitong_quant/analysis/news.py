from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from statistics import mean


class EventType(str, Enum):
    EARNINGS = "earnings"
    BUYBACK = "buyback"
    INSIDER_SELL = "insider_sell"
    REGULATORY = "regulatory"
    INDUSTRY_POLICY = "industry_policy"
    DIVIDEND = "dividend"
    CONTRACT = "contract"
    UPGRADE = "upgrade"
    OTHER = "other"


@dataclass(frozen=True)
class NewsScore:
    symbol: str
    score: float
    summary: str = ""
    url: str = ""
    as_of: str = ""
    event_type: str = "other"
    confidence: float = 0.0
    source_name: str = ""


@dataclass(frozen=True)
class RawNewsItem:
    symbol: str
    title: str
    content: str = ""
    url: str = ""
    published_at: str = ""
    source: str = ""


class NewsCSVSource:
    """Loads reviewed news scores.

    Score convention: -1.0 strongly negative, 0 neutral/missing, +1.0 strongly
    positive. This avoids treating noisy headlines as trading instructions.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, NewsScore]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        scores: dict[str, NewsScore] = {}
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = row["symbol"].strip()
                scores[symbol] = NewsScore(
                    symbol=symbol,
                    score=max(-1.0, min(1.0, float(row.get("score") or 0.0))),
                    summary=(row.get("summary") or "").strip(),
                    url=(row.get("url") or "").strip(),
                    as_of=(row.get("as_of") or "").strip(),
                    event_type=(row.get("event_type") or "other").strip(),
                    confidence=max(0.0, min(1.0, float(row.get("confidence") or 0.0))),
                    source_name=(row.get("source_name") or "").strip(),
                )
        return scores


class RawNewsCSVSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[RawNewsItem]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        items: list[RawNewsItem] = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                items.append(
                    RawNewsItem(
                        symbol=row["symbol"].strip(),
                        title=(row.get("title") or "").strip(),
                        content=(row.get("content") or row.get("summary") or "").strip(),
                        url=(row.get("url") or "").strip(),
                        published_at=(row.get("published_at") or row.get("as_of") or "").strip(),
                        source=(row.get("source") or "").strip(),
                    )
                )
        return items


class AKShareStockNewsSource:
    def __init__(self, max_items_per_symbol: int = 20) -> None:
        self.max_items_per_symbol = max_items_per_symbol

    def load(self, symbols: list[str] | tuple[str, ...]) -> list[RawNewsItem]:
        try:
            import akshare as ak  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed. Install .[research].") from exc

        items: list[RawNewsItem] = []
        for symbol in symbols:
            try:
                frame = ak.stock_news_em(symbol=symbol)
            except TypeError:
                frame = ak.stock_news_em(stock=symbol)
            for _, row in frame.head(self.max_items_per_symbol).iterrows():
                items.append(
                    RawNewsItem(
                        symbol=symbol,
                        title=str(row.get("新闻标题", row.get("title", "")) or ""),
                        content=str(row.get("新闻内容", row.get("content", "")) or ""),
                        url=str(row.get("新闻链接", row.get("url", "")) or ""),
                        published_at=str(row.get("发布时间", row.get("published_at", "")) or ""),
                        source=str(row.get("文章来源", row.get("source", "")) or ""),
                    )
                )
        return items


_KEYWORD_EVENT_MAP: dict[str, tuple[float, EventType]] = {
    "业绩预增": (+1.0, EventType.EARNINGS),
    "净利润增长": (+1.0, EventType.EARNINGS),
    "增长": (+0.5, EventType.EARNINGS),
    "超预期": (+1.0, EventType.EARNINGS),
    "positive": (+0.5, EventType.EARNINGS),
    "beat": (+1.0, EventType.EARNINGS),
    "growth": (+0.5, EventType.EARNINGS),
    "回购": (+0.8, EventType.BUYBACK),
    "buyback": (+0.8, EventType.BUYBACK),
    "增持": (+0.6, EventType.BUYBACK),
    "中标": (+0.8, EventType.CONTRACT),
    "订单": (+0.7, EventType.CONTRACT),
    "合作": (+0.5, EventType.CONTRACT),
    "contract": (+0.7, EventType.CONTRACT),
    "资金净流入": (+0.7, EventType.OTHER),
    "成交活跃": (+0.5, EventType.OTHER),
    "流动性改善": (+0.5, EventType.OTHER),
    "突破": (+0.5, EventType.OTHER),
    "创新高": (+0.6, EventType.OTHER),
    "扩产": (+0.6, EventType.OTHER),
    "获批": (+0.7, EventType.OTHER),
    "上调评级": (+0.8, EventType.UPGRADE),
    "upgrade": (+0.8, EventType.UPGRADE),
    "分红": (+0.5, EventType.DIVIDEND),
    "亏损": (-1.0, EventType.EARNINGS),
    "下滑": (-0.7, EventType.EARNINGS),
    "下降": (-0.5, EventType.EARNINGS),
    "negative": (-0.5, EventType.EARNINGS),
    "miss": (-1.0, EventType.EARNINGS),
    "loss": (-0.8, EventType.EARNINGS),
    "减持": (-0.8, EventType.INSIDER_SELL),
    "处罚": (-1.0, EventType.REGULATORY),
    "立案": (-1.0, EventType.REGULATORY),
    "调查": (-0.8, EventType.REGULATORY),
    "诉讼": (-0.7, EventType.REGULATORY),
    "lawsuit": (-0.7, EventType.REGULATORY),
    "风险": (-0.3, EventType.OTHER),
    "暴跌": (-0.9, EventType.OTHER),
    "终止": (-0.6, EventType.OTHER),
    "违约": (-0.9, EventType.OTHER),
    "default": (-0.9, EventType.OTHER),
    "下调评级": (-0.8, EventType.UPGRADE),
    "downgrade": (-0.8, EventType.UPGRADE),
}


class KeywordNewsScorer:
    positive_terms = tuple(k for k, (score, _) in _KEYWORD_EVENT_MAP.items() if score > 0)
    negative_terms = tuple(k for k, (score, _) in _KEYWORD_EVENT_MAP.items() if score < 0)

    def score_items(self, items: list[RawNewsItem]) -> dict[str, NewsScore]:
        grouped: dict[str, list[tuple[RawNewsItem, float, EventType, float]]] = {}
        for item in items:
            score, event_type, confidence = self._classify_text(f"{item.title} {item.content}")
            grouped.setdefault(item.symbol, []).append((item, score, event_type, confidence))

        output: dict[str, NewsScore] = {}
        for symbol, scored in grouped.items():
            scores = [score for _, score, _, _ in scored]
            aggregate = max(-1.0, min(1.0, mean(scores))) if scores else 0.0
            ranked = sorted(scored, key=lambda item: abs(item[1]), reverse=True)
            summary = "; ".join(
                f"{item.title} ({score:+.2f})"
                for item, score, _, _ in ranked[:3]
                if item.title
            )
            first_item = ranked[0][0] if ranked else None
            top_event = ranked[0][2] if ranked else EventType.OTHER
            top_confidence = ranked[0][3] if ranked else 0.0
            output[symbol] = NewsScore(
                symbol=symbol,
                score=aggregate,
                summary=summary or f"{len(scored)} recent news items; no keyword signal",
                url=first_item.url if first_item else "",
                as_of=first_item.published_at if first_item else "",
                event_type=top_event.value,
                confidence=round(top_confidence, 3),
                source_name=first_item.source if first_item else "",
            )
        return output

    def _classify_text(self, text: str) -> tuple[float, EventType, float]:
        lowered = text.lower()
        matched: list[tuple[float, EventType]] = []
        for keyword, (weight, event_type) in _KEYWORD_EVENT_MAP.items():
            if keyword.lower() in lowered:
                matched.append((weight, event_type))

        if not matched:
            return 0.0, EventType.OTHER, 0.0

        positive = sum(weight for weight, _ in matched if weight > 0)
        negative = sum(abs(weight) for weight, _ in matched if weight < 0)
        total_weight = positive + negative
        score = (positive - negative) / max(3.0, total_weight)
        score = max(-1.0, min(1.0, score))
        event_type = max(matched, key=lambda item: abs(item[0]))[1]
        confidence = min(1.0, len(matched) / 3.0)
        return score, event_type, confidence

    def _score_text(self, text: str) -> float:
        score, _, _ = self._classify_text(text)
        return score


def write_news_scores(path: str | Path, scores: dict[str, NewsScore]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "score",
                "summary",
                "url",
                "as_of",
                "event_type",
                "confidence",
                "source_name",
            ],
        )
        writer.writeheader()
        for symbol in sorted(scores):
            score = scores[symbol]
            writer.writerow(
                {
                    "symbol": score.symbol,
                    "score": f"{score.score:.6f}",
                    "summary": score.summary,
                    "url": score.url,
                    "as_of": score.as_of,
                    "event_type": score.event_type,
                    "confidence": f"{score.confidence:.6f}",
                    "source_name": score.source_name,
                }
            )
