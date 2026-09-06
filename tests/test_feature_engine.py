from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.analysis.indicators import add_indicators


class FeatureEngineTests(unittest.TestCase):
    @staticmethod
    def sample(rows: int = 300) -> pd.DataFrame:
        index = np.arange(rows, dtype=float)
        close = 20.0 + (index * 0.08) + np.sin(index / 5.0)
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=rows, freq="D"),
                "open": close - 0.10,
                "high": close + 0.50,
                "low": close - 0.50,
                "close": close,
                "volume": 1_000_000 + (index * 1_000),
            }
        )

    def test_canonical_feature_set_is_available(self) -> None:
        out = DEFAULT_FEATURE_ENGINE.build(self.sample())
        expected = {
            "williams_r",
            "williams_slope",
            "momentum5",
            "momentum10",
            "momentum14",
            "momentum20",
            "ema10",
            "ema20",
            "ema50",
            "ma35",
            "ma50",
            "ma200",
            "rvol20",
            "dollar_volume",
            "atr14",
            "volatility20",
            "breakout_high",
            "breakout_low",
            "breakout_distance_pct",
            "ath252",
            "distance_from_ath_pct",
        }
        self.assertTrue(expected.issubset(set(out.columns)))

    def test_breakout_reference_uses_completed_previous_bars(self) -> None:
        data = self.sample(40)
        # Make the current bar an extreme high. It must not contaminate the
        # breakout reference used on this same bar.
        data.loc[25, "high"] = 999.0
        out = DEFAULT_FEATURE_ENGINE.build(data)
        expected_previous_high = data.loc[5:24, "high"].max()
        self.assertAlmostEqual(out.loc[25, "breakout_high"], expected_previous_high)
        self.assertNotEqual(out.loc[25, "breakout_high"], 999.0)

    def test_williams_stays_in_standard_range_after_warmup(self) -> None:
        out = DEFAULT_FEATURE_ENGINE.build(self.sample(80))
        values = out["williams_r"].dropna()
        self.assertTrue((values <= 0.0).all())
        self.assertTrue((values >= -100.0).all())

    def test_legacy_indicator_entry_point_keeps_compatibility_columns(self) -> None:
        out = add_indicators(self.sample(80))
        for column in (
            "ema20",
            "ema50",
            "atr14",
            "volume20",
            "breakout_high",
            "breakout_low",
        ):
            self.assertIn(column, out.columns)


if __name__ == "__main__":
    unittest.main()
