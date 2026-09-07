from __future__ import annotations

import unittest

import pandas as pd

from app.strategy.fusion import SignalDirection
from app.strategy.mean_reversion.alpha import MeanReversionAlpha
from app.strategy.volatility.alpha import VolatilityExpansionAlpha


class ResearchAlphaTests(unittest.TestCase):
    def test_mean_reversion_detects_oversold_stretch(self) -> None:
        frame = pd.DataFrame(
            {
                "close": [100.0],
                "ma35": [110.0],
                "atr14": [5.0],
                "rsi14": [31.0],
                "williams_r": [-91.0],
            }
        )
        signal = MeanReversionAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)
        self.assertGreater(signal.confidence, 0.60)

    def test_mean_reversion_stays_neutral_without_stretch(self) -> None:
        frame = pd.DataFrame(
            {
                "close": [105.0],
                "ma35": [104.0],
                "atr14": [4.0],
                "rsi14": [53.0],
                "williams_r": [-45.0],
            }
        )
        signal = MeanReversionAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.NEUTRAL)

    def test_volatility_expansion_requires_breakout_and_volume(self) -> None:
        rows = 40
        frame = pd.DataFrame(
            {
                "close": [100.0] * (rows - 1) + [112.0],
                "volatility20": [1.0] * (rows - 1) + [1.8],
                "rvol20": [1.0] * (rows - 1) + [1.9],
                "breakout_high": [110.0] * rows,
                "breakout_low": [90.0] * rows,
                "atr14": [3.0] * rows,
            }
        )
        signal = VolatilityExpansionAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)
        self.assertGreater(signal.confidence, 0.65)


if __name__ == "__main__":
    unittest.main()
