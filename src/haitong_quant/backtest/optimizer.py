from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from haitong_quant.backtest.walk_forward import WalkForwardEngine
from haitong_quant.config import QuantConfig
from haitong_quant.models import Bar
from haitong_quant.strategy import EtfRotationStrategy


@dataclass(frozen=True)
class OptimizationResult:
    lookback_days: int
    top_n: int
    min_momentum: float
    avg_train_return: float
    avg_test_return: float
    avg_test_drawdown: float
    avg_train_sharpe: float
    avg_test_sharpe: float
    overfit_ratio: float
    parameter_stability: float
    window_count: float


def run_parameter_grid(
    config: QuantConfig,
    bars_by_symbol: dict[str, list[Bar]],
    *,
    lookback_days: list[int],
    top_n: list[int],
    min_momentum: list[float],
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 63,
) -> list[OptimizationResult]:
    results: list[OptimizationResult] = []
    for lookback in lookback_days:
        for top in top_n:
            for momentum in min_momentum:
                strategy = EtfRotationStrategy(
                    strategy_id=config.strategy.id,
                    whitelist=config.strategy.symbols,
                    lookback_days=lookback,
                    top_n=top,
                    min_momentum=momentum,
                )
                engine = WalkForwardEngine(
                    strategy=strategy,
                    train_days=train_days,
                    test_days=test_days,
                    step_days=step_days,
                    starting_cash=config.backtest.starting_cash,
                    commission_bps=config.backtest.commission_bps,
                    slippage_bps=config.backtest.slippage_bps,
                    rebalance_days=config.strategy.rebalance_days,
                    lot_size=config.execution.lot_size,
                )
                wf = engine.run(bars_by_symbol)
                train_sharpes = [
                    window.train_metrics.get("sharpe", 0.0) for window in wf.windows
                ]
                test_sharpes = [
                    window.test_metrics.get("sharpe", 0.0) for window in wf.windows
                ]
                avg_train_sharpe = _avg(train_sharpes)
                avg_test_sharpe = _avg(test_sharpes)
                overfit_ratio = (
                    abs(avg_train_sharpe) / max(abs(avg_test_sharpe), 0.001)
                    if avg_test_sharpe != 0
                    else abs(avg_train_sharpe) / 0.001
                )
                results.append(
                    OptimizationResult(
                        lookback_days=lookback,
                        top_n=top,
                        min_momentum=momentum,
                        avg_train_return=wf.aggregate_metrics.get("avg_train_return", 0.0),
                        avg_test_return=wf.aggregate_metrics.get("avg_test_return", 0.0),
                        avg_test_drawdown=wf.aggregate_metrics.get("avg_test_drawdown", 0.0),
                        avg_train_sharpe=round(avg_train_sharpe, 6),
                        avg_test_sharpe=round(avg_test_sharpe, 6),
                        overfit_ratio=round(overfit_ratio, 4),
                        parameter_stability=wf.aggregate_metrics.get("parameter_stability", 0.0),
                        window_count=wf.aggregate_metrics.get("window_count", 0.0),
                    )
                )
    results.sort(key=lambda item: (item.avg_test_sharpe, item.avg_test_return), reverse=True)
    return results


def write_optimization_csv(path: str | Path, results: list[OptimizationResult]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(results[0]).keys()) if results else [
        "lookback_days",
        "top_n",
        "min_momentum",
        "avg_train_return",
        "avg_test_return",
        "avg_test_drawdown",
        "avg_train_sharpe",
        "avg_test_sharpe",
        "overfit_ratio",
        "parameter_stability",
        "window_count",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
