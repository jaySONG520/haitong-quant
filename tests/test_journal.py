"""交易复盘日志测试。"""

import tempfile
import unittest
from pathlib import Path

from haitong_quant.analysis.journal import TradeJournal


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_journal.db"
        self.journal = TradeJournal(self.db_path)

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def test_record_signal_and_query(self):
        """记录信号后可以查询到。"""
        self.journal.record_signal(
            signal_id="SIG-001",
            signal_date="2025-06-01",
            symbol="510300",
            direction="buy",
            entry_price=4.10,
            stop_loss_price=3.90,
            take_profit_price=4.50,
            score=72.5,
        )
        sig = self.journal.get_signal("SIG-001")

        self.assertIsNotNone(sig)
        self.assertEqual(sig.symbol, "510300")
        self.assertEqual(sig.status, "pending")
        self.assertAlmostEqual(sig.entry_price, 4.10)

    def test_full_lifecycle_signal_to_exit(self):
        """信号 → 触发 → 成交 → 退出的完整生命周期。"""
        self.journal.record_signal(
            signal_id="SIG-002",
            signal_date="2025-06-01",
            symbol="510300",
            direction="buy",
            entry_price=4.10,
        )
        self.journal.record_trigger("SIG-002")
        sig = self.journal.get_signal("SIG-002")
        self.assertEqual(sig.status, "triggered")

        self.journal.record_fill("SIG-002", fill_price=4.12)
        sig = self.journal.get_signal("SIG-002")
        self.assertEqual(sig.status, "filled")
        self.assertAlmostEqual(sig.fill_price, 4.12)

        self.journal.record_exit("SIG-002", exit_price=4.30)
        sig = self.journal.get_signal("SIG-002")
        self.assertEqual(sig.status, "exited")
        self.assertGreater(sig.pnl, 0)
        self.assertGreater(sig.pnl_pct, 0)

    def test_exit_without_fill_raises(self):
        """未成交就退出应抛异常。"""
        self.journal.record_signal(
            signal_id="SIG-003",
            signal_date="2025-06-01",
            symbol="510300",
            direction="buy",
            entry_price=4.10,
        )
        with self.assertRaises(ValueError):
            self.journal.record_exit("SIG-003", exit_price=4.30)

    def test_summary_statistics(self):
        """复盘统计计算正确性。"""
        # 两笔盈利、一笔亏损
        for i, (fill, exit_p) in enumerate([(4.10, 4.30), (4.20, 4.40), (4.50, 4.20)]):
            sid = f"SIG-{i:03d}"
            self.journal.record_signal(
                signal_id=sid, signal_date="2025-06-01",
                symbol="510300", direction="buy", entry_price=fill,
            )
            self.journal.record_fill(sid, fill_price=fill)
            self.journal.record_exit(sid, exit_price=exit_p)

        summary = self.journal.summary()
        self.assertEqual(summary.total_signals, 3)
        self.assertEqual(summary.exited, 3)
        self.assertEqual(summary.wins, 2)
        self.assertEqual(summary.losses, 1)
        self.assertAlmostEqual(summary.win_rate, 2 / 3, places=3)
        self.assertEqual(summary.max_consecutive_losses, 1)
        self.assertGreater(summary.profit_factor, 1.0)

    def test_expired_signal(self):
        """信号过期标记。"""
        self.journal.record_signal(
            signal_id="SIG-EXP",
            signal_date="2025-06-01",
            symbol="510300",
            direction="buy",
            entry_price=4.10,
        )
        self.journal.record_expired("SIG-EXP", notes="价格未突破入场价")
        sig = self.journal.get_signal("SIG-EXP")
        self.assertEqual(sig.status, "expired")

    def test_get_all_signals(self):
        """查询全部信号。"""
        for i in range(3):
            self.journal.record_signal(
                signal_id=f"SIG-ALL-{i}",
                signal_date="2025-06-01",
                symbol="510300" if i < 2 else "510500",
                direction="buy",
                entry_price=4.10,
            )
        all_sigs = self.journal.get_all_signals()
        self.assertEqual(len(all_sigs), 3)

        filtered = self.journal.get_all_signals(symbol="510500")
        self.assertEqual(len(filtered), 1)
