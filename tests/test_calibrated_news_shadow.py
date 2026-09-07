from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.events.models import EventType, ImpactForecast
from app.research.calibration import CalibrationSnapshot
from app.shadow_news_calibrated import CalibratedNewsShadowEvaluator
from app.strategy.fusion import AlphaSignal, SignalDirection
from app.strategy.signal_engine import SignalInsight


class CalibratedNewsShadowTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=5, freq="D"),
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1_000_000.0] * 5,
            }
        )

    @staticmethod
    def technical() -> SignalInsight:
        alpha = AlphaSignal(
            name="MomentumAlpha",
            direction=SignalDirection.LONG,
            confidence=0.70,
            quality=0.80,
            weight=1.0,
        )
        return SignalInsight(
            action="HOLD",
            direction=SignalDirection.LONG,
            score=60.0,
            confidence=70.0,
            quality=80.0,
            expected_pct=None,
            horizon="2-10D",
            regime=MarketRegime.BULL,
            regime_confidence=80.0,
            entry=100.0,
            alphas=(alpha,),
            contributions=(),
            reasons=("test",),
        )

    @staticmethod
    def forecast() -> ImpactForecast:
        return ImpactForecast(
            symbol="AAA",
            event_type=EventType.EARNINGS,
            direction="UP",
            probability_up=0.80,
            probability_down=0.10,
            probability_neutral=0.10,
            impact_score=70.0,
            expected_move_low_pct=3.0,
            expected_move_high_pct=8.0,
            horizon="1-5D",
            risk_level="HIGH",
            confidence=80.0,
            reasons=("test",),
        )

    def test_calibrated_news_shadow_records_probability_change(self) -> None:
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={},
            event_probability_offsets={"EARNINGS": -0.15},
            engine_weights={},
        )
        evaluator = CalibratedNewsShadowEvaluator(snapshot)
        result = evaluator.compare(
            "aaa",
            self.frame(),
            forecasts=(self.forecast(),),
            technical=self.technical(),
        )

        self.assertTrue(result.probability_calibration_applied)
        self.assertEqual(result.event_type, "EARNINGS")
        self.assertAlmostEqual(result.raw_direction_probability, 0.80)
        self.assertAlmostEqual(result.calibrated_direction_probability, 0.65)
        self.assertLessEqual(result.calibrated_combined_score, result.raw_combined_score)


if __name__ == "__main__":
    unittest.main()
