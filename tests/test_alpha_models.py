from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.strategy.breakout.alpha import BreakoutAlpha
from app.strategy.fusion import SignalDirection, SignalFusionEngine
from app.strategy.momentum.alpha import MomentumAlpha
from app.strategy.trend.alpha import TrendAlpha
from app.strategy.volume.alpha import VolumeAlpha
from app.strategy.wema5.alpha import WilliamsAlpha


class AlphaModelTests(unittest.TestCase):
    def test_williams_recovery_generates_long_alpha(self) -> None:
        frame = pd.DataFrame(
            {
                "williams_r": [-62.0, -50.0],
                "williams_slope": [1.0, 4.0],
            }
        )
        signal = WilliamsAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)
        self.assertGreater(signal.confidence, 0.70)

    def test_momentum_generates_long_alpha(self) -> None:
        frame = pd.DataFrame(
            {
                "momentum5": [2.0],
                "momentum10": [3.0],
                "momentum14": [4.0],
                "momentum20": [5.0],
                "rsi14": [62.0],
            }
        )
        signal = MomentumAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)

    def test_trend_generates_long_alpha(self) -> None:
        frame = pd.DataFrame(
            {
                "close": [120.0],
                "ema10": [116.0],
                "ma35": [112.0],
                "ma50": [108.0],
                "ma200": [95.0],
            }
        )
        signal = TrendAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)

    def test_breakout_generates_long_alpha(self) -> None:
        frame = pd.DataFrame(
            {
                "close": [105.0],
                "breakout_high": [100.0],
                "breakout_low": [90.0],
                "atr14": [4.0],
            }
        )
        signal = BreakoutAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)

    def test_volume_generates_long_alpha(self) -> None:
        frame = pd.DataFrame(
            {
                "rvol20": [1.8],
                "dollar_volume": [30_000_000.0],
                "momentum20": [6.0],
            }
        )
        signal = VolumeAlpha().generate_alpha(frame)
        self.assertEqual(signal.direction, SignalDirection.LONG)

    def test_alpha_models_can_be_fused_together(self) -> None:
        signals = [
            WilliamsAlpha().generate_alpha(
                pd.DataFrame({"williams_r": [-62.0, -50.0], "williams_slope": [1.0, 4.0]})
            ),
            MomentumAlpha().generate_alpha(
                pd.DataFrame(
                    {
                        "momentum5": [2.0],
                        "momentum10": [3.0],
                        "momentum14": [4.0],
                        "momentum20": [5.0],
                        "rsi14": [62.0],
                    }
                )
            ),
            TrendAlpha().generate_alpha(
                pd.DataFrame(
                    {
                        "close": [120.0],
                        "ema10": [116.0],
                        "ma35": [112.0],
                        "ma50": [108.0],
                        "ma200": [95.0],
                    }
                )
            ),
            BreakoutAlpha().generate_alpha(
                pd.DataFrame(
                    {
                        "close": [105.0],
                        "breakout_high": [100.0],
                        "breakout_low": [90.0],
                        "atr14": [4.0],
                    }
                )
            ),
            VolumeAlpha().generate_alpha(
                pd.DataFrame(
                    {
                        "rvol20": [1.8],
                        "dollar_volume": [30_000_000.0],
                        "momentum20": [6.0],
                    }
                )
            ),
        ]
        result = SignalFusionEngine().fuse(signals, regime=MarketRegime.BULL)
        self.assertEqual(result.direction, SignalDirection.LONG)
        self.assertGreater(result.score, 70.0)
        self.assertEqual(len(result.contributions), 5)


if __name__ == "__main__":
    unittest.main()
