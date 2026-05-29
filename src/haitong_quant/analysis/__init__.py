from haitong_quant.analysis.daily_report import generate_daily_report, write_daily_report
from haitong_quant.analysis.correlation import (
    calculate_correlation_matrix,
    get_or_calculate_correlation_matrix,
)
from haitong_quant.analysis.industry import (
    AKShareIndustryMapSource,
    CSVIndustryMapSource,
    load_industry_map,
)
from haitong_quant.analysis.journal import JournalSummary, SignalRecord, TradeJournal
from haitong_quant.analysis.news import (
    AKShareStockNewsSource,
    KeywordNewsScorer,
    NewsCSVSource,
    NewsScore,
    RawNewsCSVSource,
    RawNewsItem,
    write_news_scores,
)
from haitong_quant.analysis.report import render_research_report, write_research_report
from haitong_quant.analysis.screener import CandidateScore, KlineNewsScreener, TradingRuleSuggestion
from haitong_quant.analysis.trade_plan import (
    TradePlanItem,
    build_trade_plan,
    write_trade_plan_csv,
    write_trade_plan_json,
)
from haitong_quant.analysis.universe import (
    AKShareUniverseSource,
    CSVUniverseSource,
    UniverseFilter,
    UniverseMember,
    UniverseSelector,
    write_config_with_universe,
    write_universe_csv,
)

__all__ = [
    "CandidateScore",
    "AKShareIndustryMapSource",
    "CSVIndustryMapSource",
    "KlineNewsScreener",
    "AKShareStockNewsSource",
    "KeywordNewsScorer",
    "NewsCSVSource",
    "NewsScore",
    "RawNewsCSVSource",
    "RawNewsItem",
    "TradingRuleSuggestion",
    "TradePlanItem",
    "AKShareUniverseSource",
    "CSVUniverseSource",
    "UniverseFilter",
    "UniverseMember",
    "UniverseSelector",
    "JournalSummary",
    "SignalRecord",
    "TradeJournal",
    "build_trade_plan",
    "calculate_correlation_matrix",
    "generate_daily_report",
    "get_or_calculate_correlation_matrix",
    "load_industry_map",
    "render_research_report",
    "write_config_with_universe",
    "write_daily_report",
    "write_research_report",
    "write_news_scores",
    "write_trade_plan_csv",
    "write_trade_plan_json",
    "write_universe_csv",
]
