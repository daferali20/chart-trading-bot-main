from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.analysis.regime import MarketRegime
from app.strategy.fusion import SignalDirection
from app.strategy.signal_engine import SignalEngine


class SignalEngineTests(unittest.TestCase):
    @staticmethod
    def frame(rows: int = 300, slope: float = 0.40) -> pd.DataFrame:
        index = np.arange(rows, dtype=float)
        close = 50.0 + (index * slope) + (np.sin(index / 3.0) * 1.5)
        volume = np.full(rows, 1_000_000.0)
        volume[-1] = 3_000_000.0
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=rows, freq="D"),
                "open": close - 0.10,
                "high": close + 0.30,
                "low": close - 0.30,
                "close": close,
                "volume": volume,
            }
        )

    def test_signal_engine_produces_structured_insight(self) -> None:
        engine = SignalEngine(buy_score_threshold=50.0)
        result = engine.analyze(
            self.frame(),
            market_df=self.frame(slope=0.25),
        )
        self.assertEqual(result.regime, MarketRegime.BULL)
        self.assertEqual(result.direction, SignalDirection.LONG)
        self.assertEqual(result.action, "BUY")
        self.assertGreaterEqual(result.score, 50.0)
        self.assertGreater(result.confidence, 0.0)
        self.assertEqual(len(result.alphas), 5)
        self.assertEqual(len(result.contributions), 5)

    def test_missing_market_benchmark_is_explicit(self) -> None:
        engine = SignalEngine(buy_score_threshold=0.0)
        result = engine.analyze(self.frame(), market_df=None)
        self.assertEqual(result.regime, MarketRegime.UNKNOWN)
        self.assertTrue(any("benchmark" in reason.lower() for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
