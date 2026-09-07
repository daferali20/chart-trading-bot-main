from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.research.datasets.yahoo import YahooDatasetBuilder


class FakeYahooProvider:
    period = "5y"
    interval = "1d"

    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        if symbol.upper() == "BAD":
            raise RuntimeError("simulated download failure")
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "open": [10.0, 11.0],
                "high": [11.0, 12.0],
                "low": [9.0, 10.0],
                "close": [10.5, 11.5],
                "volume": [1000.0, 2000.0],
            }
        )


class YahooDatasetBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_builder_saves_canonical_csv_and_records_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = YahooDatasetBuilder(
                FakeYahooProvider(),
                output_dir=temp_dir,
                retries=0,
            )
            report = await builder.build(["aaa", "AAA", "bad"])

            self.assertEqual(len(report.entries), 1)
            self.assertEqual(report.entries[0].symbol, "AAA")
            self.assertIn("BAD", report.errors)

            csv_path = Path(report.entries[0].path)
            self.assertTrue(csv_path.exists())
            frame = pd.read_csv(csv_path)
            self.assertEqual(
                list(frame.columns),
                ["date", "open", "high", "low", "close", "volume"],
            )

            manifest = report.save(Path(temp_dir) / "manifest.json")
            self.assertTrue(manifest.exists())

    async def test_builder_rejects_empty_symbol_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = YahooDatasetBuilder(
                FakeYahooProvider(),
                output_dir=temp_dir,
                retries=0,
            )
            with self.assertRaises(ValueError):
                await builder.build(["", "# comment"])


if __name__ == "__main__":
    unittest.main()
