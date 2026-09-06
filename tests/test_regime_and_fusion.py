from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.analysis.regime import MarketRegime, MarketRegimeEngine
from app.strategy.fusion import AlphaSignal, SignalDirection, SignalFusionEngine


class RegimeAndFusionTests(unittest.TestCase):
    @staticmethod
    def trend_frame(direction: int, rows: int = 260) -> pd.DataFrame:
        index = np.arange(rows, dtype=float)
        if direction > 0:
            close = 100.0 + (index * 0.20) + (np.sin(index / 8.0) * 0.20)
        else:
            close = 180.0 - (index * 0.20) + (np.sin(index / 8.0) * 0.20)
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=rows, freq="D"),
                "open": close - 0.10,
                "high": close + 0.40,
                "low": close - 0.40,
                "close": close,
                "volume": np.full(rows, 1_000_000.0),
            }
        )

    def test_regime_detects_bull_trend(self) -> None:
        result = MarketRegimeEngine().classify(self.trend_frame(1))
        self.assertEqual(result.regime, MarketRegime.BULL)
        self.assertGreaterEqual(result.confidence, 80.0)

    def test_regime_detects_bear_trend(self) -> None:
        result = MarketRegimeEngine().classify(self.trend_frame(-1))
        self.assertEqual(result.regime, MarketRegime.BEAR)
        self.assertGreaterEqual(result.confidence, 80.0)

    def test_fusion_combines_multiple_long_alphas(self) -> None:
        engine = SignalFusionEngine()
        result = engine.fuse(
            [
                AlphaSignal(
                    name="Williams",
                    direction=SignalDirection.LONG,
                    confidence=0.80,
                    quality=0.90,
                    weight=1.0,
                    magnitude_pct=4.0,
                    horizon="10-20D",
                ),
                AlphaSignal(
                    name="Momentum",
                    direction=SignalDirection.LONG,
                    confidence=0.75,
                    quality=0.85,
                    weight=1.0,
                    magnitude_pct=5.0,
                    horizon="10-20D",
                ),
                AlphaSignal(
                    name="Trend",
                    direction=SignalDirection.LONG,
                    confidence=0.90,
                    quality=0.95,
                    weight=1.2,
                    magnitude_pct=4.5,
                    horizon="10-20D",
                ),
            ],
            regime=MarketRegime.BULL,
        )
        self.assertEqual(result.direction, SignalDirection.LONG)
        self.assertGreater(result.score, 70.0)
        self.assertGreater(result.confidence, 75.0)
        self.assertEqual(result.horizon, "10-20D")

    def test_risk_off_reduces_long_signal_strength(self) -> None:
        engine = SignalFusionEngine()
        signals = [
            AlphaSignal(
                name="Trend",
                direction=SignalDirection.LONG,
                confidence=0.85,
                quality=0.90,
            ),
            AlphaSignal(
                name="Momentum",
                direction=SignalDirection.LONG,
                confidence=0.80,
                quality=0.85,
            ),
        ]
        bull = engine.fuse(signals, regime=MarketRegime.BULL)
        risk_off = engine.fuse(signals, regime=MarketRegime.RISK_OFF)
        self.assertLess(risk_off.direction_strength, bull.direction_strength)
        self.assertLess(risk_off.score, bull.score)

    def test_conflicting_alphas_can_collapse_to_neutral(self) -> None:
        engine = SignalFusionEngine(minimum_direction_strength=0.20)
        result = engine.fuse(
            [
                AlphaSignal(
                    name="Trend",
                    direction=SignalDirection.LONG,
                    confidence=0.80,
                    quality=0.90,
                ),
                AlphaSignal(
                    name="BreakoutFailure",
                    direction=SignalDirection.SHORT,
                    confidence=0.80,
                    quality=0.90,
                ),
            ],
            regime=MarketRegime.SIDEWAYS,
        )
        self.assertEqual(result.direction, SignalDirection.NEUTRAL)
        self.assertAlmostEqual(result.direction_strength, 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
