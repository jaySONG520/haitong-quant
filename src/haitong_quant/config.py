from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DataConfig:
    source: str
    csv_path: str
    adjust: str = "qfq"
    asset_type: str = "etf"


@dataclass(frozen=True)
class StrategyConfig:
    id: str
    lookback_days: int
    rebalance_days: int
    top_n: int
    min_momentum: float
    symbols: tuple[str, ...]
    type: str = "etf_rotation"


@dataclass(frozen=True)
class ExecutionConfig:
    account_mode: str
    enable_live_orders: bool
    lot_size: int
    default_limit_slippage_bps: float
    min_trade_fee: float = 5.0
    stock_sell_tax_bps: float = 5.0


@dataclass(frozen=True)
class PortfolioRiskSettings:
    max_total_exposure: float = 0.8
    max_industry_weight: float = 0.3
    max_daily_entries: int = 3
    max_correlation: float = 0.85
    max_single_symbol_weight: float = 1.0
    industry_map_path: str = "data/industry_map.csv"
    correlation_window: int = 60


@dataclass(frozen=True)
class RiskConfig:
    allowed_symbols: tuple[str, ...]
    live_allowed_symbols: tuple[str, ...]
    max_single_order_value: float
    max_daily_trade_value: float
    max_symbol_weight: float
    trading_start: str
    trading_end: str
    manual_kill_switch_path: str
    max_consecutive_rejections: int
    max_intraday_drawdown_pct: float = 0.03
    max_total_drawdown_pct: float = 0.08
    portfolio: PortfolioRiskSettings = field(default_factory=PortfolioRiskSettings)


@dataclass(frozen=True)
class BrokerConfig:
    kind: str
    starting_cash: float
    qmt_proxy_base_url: str


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    db_path: str = "data/cache.db"
    max_age_days: int = 30


@dataclass(frozen=True)
class NotifierConfig:
    type: str = "console"


@dataclass(frozen=True)
class OpsConfig:
    notifier: NotifierConfig = field(default_factory=NotifierConfig)
    pipeline_output_dir: str = "runs"
    alerts_path: str = "reports/monitor_alerts.jsonl"
    dashboard_path: str = "reports/dashboard.html"
    dashboard_poll_interval_seconds: int = 30
    dashboard_min_poll_interval_seconds: int = 5


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float
    commission_bps: float
    slippage_bps: float


@dataclass(frozen=True)
class QuantConfig:
    data: DataConfig
    strategy: StrategyConfig
    execution: ExecutionConfig
    risk: RiskConfig
    broker: BrokerConfig
    backtest: BacktestConfig
    cache: CacheConfig = CacheConfig()
    ops: OpsConfig = field(default_factory=OpsConfig)


def load_config(path: str | Path) -> QuantConfig:
    config_path = Path(path)
    data = _load_mapping(config_path)
    cache_data = data.get("cache", {})
    strategy_data = dict(data["strategy"])
    risk_data = dict(data["risk"])
    portfolio_data = risk_data.pop("portfolio", {})
    ops_data = data.get("ops", {})
    notifier_data = ops_data.get("notifier", {}) if isinstance(ops_data, dict) else {}
    ops_fields = (
        {k: v for k, v in ops_data.items() if k != "notifier"}
        if isinstance(ops_data, dict)
        else {}
    )
    return QuantConfig(
        data=DataConfig(**data["data"]),
        strategy=StrategyConfig(
            **{
                **strategy_data,
                "symbols": tuple(strategy_data.get("symbols", ())),
                "type": strategy_data.get("type", "etf_rotation"),
            }
        ),
        execution=ExecutionConfig(**data["execution"]),
        risk=RiskConfig(
            **{
                **risk_data,
                "allowed_symbols": tuple(risk_data.get("allowed_symbols", ())),
                "live_allowed_symbols": tuple(
                    risk_data.get("live_allowed_symbols", ())
                ),
                "portfolio": PortfolioRiskSettings(**portfolio_data)
                if portfolio_data
                else PortfolioRiskSettings(),
            }
        ),
        broker=BrokerConfig(**data["broker"]),
        backtest=BacktestConfig(**data["backtest"]),
        cache=CacheConfig(**cache_data) if cache_data else CacheConfig(),
        ops=OpsConfig(
            **{
                **ops_fields,
                "notifier": NotifierConfig(**notifier_data)
                if notifier_data
                else NotifierConfig(),
            }
        ),
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "YAML config requires pyyaml. Use JSON or install .[research]."
            ) from exc
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return loaded
