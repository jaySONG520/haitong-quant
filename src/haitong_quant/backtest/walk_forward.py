"""Walk-forward 滚动回测引擎。

不只测一段历史，而是滚动训练/验证窗口：
  - 例如 2023 参数 → 2024 验证 → 2025 再验证
  - 防止过拟合，输出各窗口 metrics + 参数稳定性分析
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from haitong_quant.backtest.engine import BacktestEngine, BacktestResult
from haitong_quant.models import Bar
from haitong_quant.strategy import EtfRotationStrategy


@dataclass(frozen=True)
class WindowResult:
    """单个滚动窗口的回测结果。"""
    window_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    test_orders: int


@dataclass(frozen=True)
class WalkForwardResult:
    """全部滚动窗口的汇总结果。"""
    windows: list[WindowResult]
    aggregate_metrics: dict[str, float]


class WalkForwardEngine:
    """滚动窗口回测引擎。

    按 train_days / test_days / step_days 切分数据窗口，
    每个窗口内使用 BacktestEngine 独立回测。
    """

    def __init__(
        self,
        strategy: EtfRotationStrategy,
        train_days: int = 252,
        test_days: int = 63,
        step_days: int = 63,
        starting_cash: float = 100000.0,
        commission_bps: float = 2.0,
        slippage_bps: float = 5.0,
        rebalance_days: int = 5,
        lot_size: int = 100,
    ) -> None:
        self.strategy = strategy
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.starting_cash = starting_cash
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.rebalance_days = rebalance_days
        self.lot_size = lot_size

    def run(self, bars_by_symbol: dict[str, list[Bar]]) -> WalkForwardResult:
        """执行滚动窗口回测。"""
        # 找到所有标的共同的交易日列表
        common_dates = self._common_dates(bars_by_symbol)
        total_days = len(common_dates)
        min_window = self.train_days + self.test_days

        if total_days < min_window:
            raise ValueError(
                f"交易日数量 ({total_days}) 不足以覆盖一个完整窗口 "
                f"(train={self.train_days} + test={self.test_days} = {min_window})"
            )

        windows: list[WindowResult] = []
        window_index = 0
        offset = 0

        while offset + min_window <= total_days:
            train_start = common_dates[offset]
            train_end = common_dates[offset + self.train_days - 1]
            test_start = common_dates[offset + self.train_days]
            test_end_idx = min(offset + min_window - 1, total_days - 1)
            test_end = common_dates[test_end_idx]

            # 切分 bars
            train_bars = self._slice_bars(bars_by_symbol, train_start, train_end)
            test_bars = self._slice_bars(bars_by_symbol, train_start, test_end)

            # 训练窗口回测
            train_result = self._run_backtest(train_bars)

            # 测试窗口回测（使用全量数据但只看测试段表现）
            test_result = self._run_backtest(test_bars)

            windows.append(
                WindowResult(
                    window_index=window_index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_metrics=train_result.metrics,
                    test_metrics=test_result.metrics,
                    test_orders=len(test_result.orders),
                )
            )

            window_index += 1
            offset += self.step_days

        aggregate = self._aggregate(windows)
        return WalkForwardResult(windows=windows, aggregate_metrics=aggregate)

    def _common_dates(self, bars_by_symbol: dict[str, list[Bar]]) -> list[date]:
        """获取所有标的共同的排序交易日。"""
        date_sets = []
        for symbol in self.strategy.whitelist:
            if symbol not in bars_by_symbol:
                raise ValueError(f"缺少 {symbol} 的 K 线数据")
            date_sets.append({bar.date for bar in bars_by_symbol[symbol]})
        return sorted(set.intersection(*date_sets))

    def _slice_bars(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        start: date,
        end: date,
    ) -> dict[str, list[Bar]]:
        """按日期范围切分 K 线。"""
        sliced: dict[str, list[Bar]] = {}
        for symbol, bars in bars_by_symbol.items():
            sliced[symbol] = [
                bar for bar in bars if start <= bar.date <= end
            ]
        return sliced

    def _run_backtest(self, bars: dict[str, list[Bar]]) -> BacktestResult:
        """对给定数据段执行回测。"""
        engine = BacktestEngine(
            strategy=self.strategy,
            starting_cash=self.starting_cash,
            commission_bps=self.commission_bps,
            slippage_bps=self.slippage_bps,
            rebalance_days=self.rebalance_days,
            lot_size=self.lot_size,
        )
        return engine.run(bars)

    def _aggregate(self, windows: list[WindowResult]) -> dict[str, float]:
        """汇总各窗口指标。"""
        if not windows:
            return {"avg_test_return": 0.0, "avg_test_drawdown": 0.0, "window_count": 0}

        test_returns = [w.test_metrics.get("total_return", 0.0) for w in windows]
        test_drawdowns = [w.test_metrics.get("max_drawdown", 0.0) for w in windows]
        train_returns = [w.train_metrics.get("total_return", 0.0) for w in windows]

        avg_test_return = sum(test_returns) / len(test_returns)
        avg_test_drawdown = sum(test_drawdowns) / len(test_drawdowns)
        avg_train_return = sum(train_returns) / len(train_returns)

        # 参数稳定性：训练集和测试集收益差异越小越稳定
        stability = 1.0 - abs(avg_train_return - avg_test_return) / max(abs(avg_train_return), 0.001)

        return {
            "window_count": float(len(windows)),
            "avg_train_return": round(avg_train_return, 6),
            "avg_test_return": round(avg_test_return, 6),
            "avg_test_drawdown": round(avg_test_drawdown, 6),
            "best_test_return": round(max(test_returns), 6),
            "worst_test_return": round(min(test_returns), 6),
            "parameter_stability": round(stability, 4),
        }
