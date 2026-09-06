from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.data.normalizer import DataNormalizer
from app.data.providers import CSVDataProvider, IBKRDataProvider


class FakeIBKRClient:
    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": ["2026-01-02", "2026-01-01"],
                "open": [11.0, 10.0],
                "high": [12.0, 11.0],
                "low": [10.0, 9.0],
                "close": [11.5, 10.5],
                "volume": [2000, 1000],
            }
        )


class DataNormalizerTests(unittest.TestCase):
    def test_timestamp_is_promoted_to_date_and_sorted(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp": ["2026-01-03", "2026-01-01", "2026-01-02"],
                "open": [3, 1, 2],
                "high": [4, 2, 3],
                "low": [2, 0, 1],
                "close": [3.5, 1.5, 2.5],
                "volume": [300, 100, 200],
            }
        )
        out = DataNormalizer().normalize(frame, require_open=True, require_volume=True)
        self.assertIn("date", out.columns)
        self.assertEqual(list(out["close"]), [1.5, 2.5, 3.5])
        self.assertTrue(out["date"].is_monotonic_increasing)

    def test_duplicate_dates_keep_latest_source_row(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-01"],
                "high": [11, 12],
                "low": [9, 9],
                "close": [10, 11],
            }
        )
        out = DataNormalizer().normalize(frame)
        self.assertEqual(len(out), 1)
        self.assertEqual(float(out.iloc[0]["close"]), 11.0)

    def test_feature_engine_accepts_ibkr_timestamp_contract(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=60, freq="h")[::-1],
                "open": range(60),
                "high": [value + 2 for value in range(60)],
                "low": [value for value in range(60)],
                "close": [value + 1 for value in range(60)],
                "volume": [1000] * 60,
            }
        )
        out = DEFAULT_FEATURE_ENGINE.build(frame)
        self.assertIn("date", out.columns)
        self.assertTrue(out["date"].is_monotonic_increasing)
        self.assertIn("williams_r", out.columns)
        self.assertIn("ema10", out.columns)


class DataProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_ibkr_adapter_is_read_only_and_normalized(self) -> None:
        provider = IBKRDataProvider(FakeIBKRClient())
        out = await provider.historical_bars("AAA")
        self.assertEqual(list(out.columns), ["date", "open", "high", "low", "close", "volume"])
        self.assertEqual(list(out["close"]), [10.5, 11.5])

    async def test_csv_provider_reads_symbol_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "AAA.csv"
            pd.DataFrame(
                {
                    "Date": ["2026-01-02", "2026-01-01"],
                    "Open": [11, 10],
                    "High": [12, 11],
                    "Low": [10, 9],
                    "Close": [11.5, 10.5],
                    "Volume": [2000, 1000],
                }
            ).to_csv(path, index=False)

            provider = CSVDataProvider(temp_dir)
            out = await provider.historical_bars("aaa")
            self.assertEqual(list(out["close"]), [10.5, 11.5])
            self.assertEqual(list(out.columns), ["date", "open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    unittest.main()
