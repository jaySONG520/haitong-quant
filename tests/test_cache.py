"""数据缓存层测试。"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from haitong_quant.data.cache import DataCache
from haitong_quant.models import Bar


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_cache.db"
        self.cache = DataCache(self.db_path)

    def tearDown(self):
        self.cache.close()
        self.tmp.cleanup()

    def test_bars_round_trip(self):
        """写入 K 线后可以读取回来。"""
        bars = [
            Bar(date=date(2025, 1, 2), symbol="510300", open=4.0, high=4.1, low=3.9, close=4.05, volume=1000),
            Bar(date=date(2025, 1, 3), symbol="510300", open=4.05, high=4.2, low=4.0, close=4.15, volume=1200),
        ]
        self.cache.put_bars("510300", bars)
        loaded = self.cache.get_bars("510300")

        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].close, 4.05)
        self.assertEqual(loaded[1].date, date(2025, 1, 3))

    def test_bars_cache_miss_returns_none(self):
        """没有缓存数据时返回 None。"""
        result = self.cache.get_bars("999999")
        self.assertIsNone(result)

    def test_get_or_fetch_bars_uses_fetcher_then_caches(self):
        """get_or_fetch_bars 调用 fetcher 并缓存结果。"""
        fetch_count = [0]

        def fetcher(symbol):
            fetch_count[0] += 1
            return [Bar(date=date(2025, 1, 2), symbol=symbol, open=4.0, high=4.1, low=3.9, close=4.05, volume=0)]

        result = self.cache.get_or_fetch_bars("510300", fetcher)
        self.assertEqual(len(result), 1)
        self.assertEqual(fetch_count[0], 1)

        # 缓存已有数据，但 get_or_fetch 每次仍调 fetcher（优先新数据）
        result2 = self.cache.get_or_fetch_bars("510300", fetcher)
        self.assertEqual(len(result2), 1)
        self.assertEqual(fetch_count[0], 2)

    def test_get_or_fetch_bars_falls_back_to_cache_on_error(self):
        """fetcher 失败时回退到缓存。"""
        bars = [Bar(date=date(2025, 1, 2), symbol="510300", open=4.0, high=4.1, low=3.9, close=4.05, volume=0)]
        self.cache.put_bars("510300", bars)

        def failing_fetcher(symbol):
            raise ConnectionError("网络断开")

        result = self.cache.get_or_fetch_bars("510300", failing_fetcher)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].close, 4.05)

    def test_get_or_fetch_bars_raises_when_no_cache_and_fetch_fails(self):
        """无缓存且 fetcher 失败时抛出异常。"""
        def failing_fetcher(symbol):
            raise ConnectionError("网络断开")

        with self.assertRaises(ConnectionError):
            self.cache.get_or_fetch_bars("999999", failing_fetcher)

    def test_universe_round_trip(self):
        """候选池缓存写入和读取。"""
        rows = [
            {"代码": "600036", "名称": "招商银行", "最新价": "35.0"},
            {"代码": "000858", "名称": "五粮液", "最新价": "165.0"},
        ]
        self.cache.put_universe("stock", rows)
        loaded = self.cache.get_universe("stock")

        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), 2)

    def test_invalidate_all_clears_data(self):
        """invalidate_all 清空全部缓存。"""
        bars = [Bar(date=date(2025, 1, 2), symbol="510300", open=4.0, high=4.1, low=3.9, close=4.05, volume=0)]
        self.cache.put_bars("510300", bars)
        self.cache.invalidate_all()

        self.assertIsNone(self.cache.get_bars("510300"))

    def test_news_scores_round_trip(self):
        """新闻评分缓存写入和读取。"""
        scores = {
            "600036": {"symbol": "600036", "score": 0.5, "summary": "利好", "url": "", "as_of": "2025-01-02"},
        }
        self.cache.put_news_scores(scores)
        loaded = self.cache.get_news_scores()

        self.assertIsNotNone(loaded)
        self.assertIn("600036", loaded)
        self.assertAlmostEqual(loaded["600036"]["score"], 0.5)
