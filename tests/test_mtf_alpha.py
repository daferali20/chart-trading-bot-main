from __future__ import annotations

import unittest

import pandas as pd

from app.strategy.fusion import SignalDirection
from app.strategy.mtf.alpha import MultiTimeframeAlpha


class MultiTimeframeAlphaTests(unittest.TestCase):
    @staticmethod
    def frame(close: float, ema10: float, ma35: float, momentum10: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "close": [close],
                "ema10": [ema10],
                "ma35": [ma35],
                "momentum10": [momentum10],
            }
        )

    def test_bullish_alignment_generates_long(self) -> None:
        alpha = MultiTimeframeAlpha(minimum_agreement=0.60)
        result = alpha.generate_alpha(
            {
                "5m": self.frame(110, 108, 105, 2.0),
                "10m": self.frame(111, 109, 106, 2.5),
                "15m": self.frame(112, 110, 107, 3.0),
                "30m": self.frame(108, 109, 110, -1.0),
            }
        )
        self.assertEqual(result.direction, SignalDirection.LONG)
        self.assertGreater(result.confidence, 0.70)

    def test_mixed_timeframes_generate_neutral(self) -> None:
        alpha = MultiTimeframeAlpha(minimum_agreement=0.75)
        result = alpha.generate_alpha(
            {
                "5m": self.frame(110, 108, 105, 2.0),
                "10m": self.frame(100, 102, 104, -2.0),
                "15m": self.frame(111, 109, 106, 1.5),
                "30m": self.frame(99, 101, 103, -1.5),
            }
        )
        self.assertEqual(result.direction, SignalDirection.NEUTRAL)


if __name__ == "__main__":
    unittest.main()
