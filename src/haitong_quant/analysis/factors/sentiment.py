from __future__ import annotations

from haitong_quant.analysis.news import NewsScore


def sentiment_points(news: NewsScore | None) -> float:
    score = news.score if news else 0.0
    return (score + 1.0) * 50.0
