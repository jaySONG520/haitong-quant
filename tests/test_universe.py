import json
import tempfile
import unittest
from pathlib import Path

from haitong_quant.analysis import (
    CSVUniverseSource,
    UniverseFilter,
    UniverseSelector,
    write_config_with_universe,
    write_universe_csv,
)


class UniverseTests(unittest.TestCase):
    def test_universe_selector_filters_and_ranks_rows(self):
        rows = CSVUniverseSource("data/sample_universe_rows.csv").fetch_rows()
        selector = UniverseSelector(
            UniverseFilter(
                asset_type="stock",
                top_n=3,
                min_amount=800_000_000,
                min_price=2,
                max_price=500,
                max_abs_pct_change=9.5,
                min_turnover=0.2,
            )
        )

        members = selector.select(rows)

        self.assertEqual([member.symbol for member in members], ["300750", "600036", "000858"])
        self.assertNotIn("688001", [member.symbol for member in members])
        self.assertNotIn("430001", [member.symbol for member in members])
        self.assertNotIn("600000", [member.symbol for member in members])

    def test_universe_outputs_csv_and_config(self):
        rows = CSVUniverseSource("data/sample_universe_rows.csv").fetch_rows()
        members = UniverseSelector(UniverseFilter(top_n=2)).select(rows)

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "universe.csv"
            config_path = Path(tmp) / "generated.json"
            write_universe_csv(csv_path, members)
            write_config_with_universe(
                base_config_path="configs/stock_screen.json",
                output_path=config_path,
                members=members,
                asset_type="stock",
            )
            generated = json.loads(config_path.read_text(encoding="utf-8-sig"))
            self.assertTrue(csv_path.exists())

        self.assertEqual(generated["strategy"]["symbols"], [member.symbol for member in members])
        self.assertEqual(generated["risk"]["allowed_symbols"], [member.symbol for member in members])
