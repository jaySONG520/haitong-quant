from __future__ import annotations

from haitong_quant.config import StrategyConfig
from haitong_quant.strategy.base import Strategy
from haitong_quant.strategy.etf_rotation import EtfRotationStrategy


def build_strategy(config: StrategyConfig) -> Strategy:
    if config.type == "etf_rotation":
        return EtfRotationStrategy(
            strategy_id=config.id,
            whitelist=config.symbols,
            lookback_days=config.lookback_days,
            top_n=config.top_n,
            min_momentum=config.min_momentum,
        )
    raise ValueError(f"Unsupported strategy.type: {config.type}")
