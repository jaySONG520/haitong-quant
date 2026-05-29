"""接券商前的模拟撮合引擎。

借鉴 Freqtrade / vn.py 思想：所有实盘命令先走 paper trading，
确认无重复单、错单、滑点异常后，再接真实接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from haitong_quant.broker.mock import MockBroker
from haitong_quant.models import AccountSnapshot, OrderIntent, OrderRecord, Position


@dataclass(frozen=True)
class PaperCheckResult:
    """单笔订单的模拟检查结果。"""
    order: OrderIntent
    passed: bool
    reason: str
    mock_record: OrderRecord | None = None


@dataclass(frozen=True)
class PaperTradeReport:
    """模拟撮合报告。"""
    all_passed: bool
    results: list[PaperCheckResult]
    summary: str


class PaperTradingEngine:
    """模拟撮合引擎。

    接收订单列表，在内存 MockBroker 中模拟执行前检查：
    1. 重复单检测（idempotency_key）
    2. 滑点异常检测（limit_price vs last_price 偏差 > 阈值）
    3. 卖出数量 ≤ 持仓
    4. 资金充足
    5. MockBroker 实际撮合验证
    """

    def __init__(
        self,
        starting_cash: float = 100000.0,
        max_slippage_pct: float = 0.02,
        fee_bps: float = 2.0,
    ) -> None:
        self.starting_cash = starting_cash
        self.max_slippage_pct = max_slippage_pct
        self.fee_bps = fee_bps

    def validate(
        self,
        orders: list[OrderIntent],
        last_prices: dict[str, float],
        existing_positions: dict[str, Position] | None = None,
    ) -> PaperTradeReport:
        """验证全部订单，返回模拟撮合报告。

        只有全部通过后 all_passed=True。
        """
        broker = MockBroker(starting_cash=self.starting_cash, fee_bps=self.fee_bps)
        broker.connect()

        # 导入现有持仓
        if existing_positions:
            for symbol, pos in existing_positions.items():
                broker.positions[symbol] = pos

        seen_keys: set[str] = set()
        results: list[PaperCheckResult] = []

        for order in orders:
            # 检查 1：重复单
            if order.idempotency_key in seen_keys:
                results.append(PaperCheckResult(
                    order=order, passed=False,
                    reason=f"重复单: idempotency_key={order.idempotency_key}",
                ))
                continue
            seen_keys.add(order.idempotency_key)

            # 检查 2：滑点异常
            last_price = last_prices.get(order.symbol)
            if last_price and last_price > 0:
                slippage = abs(order.limit_price - last_price) / last_price
                if slippage > self.max_slippage_pct:
                    results.append(PaperCheckResult(
                        order=order, passed=False,
                        reason=f"滑点异常: limit_price={order.limit_price:.4f} vs "
                               f"last_price={last_price:.4f}, 偏差={slippage:.2%} > {self.max_slippage_pct:.2%}",
                    ))
                    continue

            # 检查 3：MockBroker 撮合
            try:
                record = broker.submit_order(order)
                if record.status == "rejected":
                    results.append(PaperCheckResult(
                        order=order, passed=False,
                        reason=f"MockBroker 拒绝: {record.message}",
                        mock_record=record,
                    ))
                else:
                    results.append(PaperCheckResult(
                        order=order, passed=True,
                        reason="模拟撮合通过",
                        mock_record=record,
                    ))
            except Exception as exc:
                results.append(PaperCheckResult(
                    order=order, passed=False,
                    reason=f"模拟撮合异常: {exc}",
                ))

        all_passed = all(r.passed for r in results)
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        summary = (
            f"共 {len(results)} 笔订单, {passed_count} 通过, {failed_count} 拒绝. "
            f"{'全部通过，可接入真实接口。' if all_passed else '存在问题订单，请检查后重试。'}"
        )

        return PaperTradeReport(
            all_passed=all_passed,
            results=results,
            summary=summary,
        )
