from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.research.calibration import CalibrationSnapshot
from app.strategy.adaptive_engine import AdaptiveSignalResult
from app.strategy.calibrated_engine import CalibratedAdaptiveSignalEngine
from app.strategy.fusion import AlphaSignal, SignalDirection
from app.strategy.selector import StrategySelection
from app.strategy.signal_engine import SignalInsight


class FakeAdaptiveEngine:
    def __init__(self, result: AdaptiveSignalResult) -> None:
        self.result = result

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return self.result


class CalibratedAdaptiveEngineTests(unittest.TestCase):
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
    def base_result() -> AdaptiveSignalResult:
        alpha = AlphaSignal(
            name="MomentumAlpha",
            direction=SignalDirection.LONG,
            confidence=0.80,
            quality=0.80,
            weight=1.0,
            horizon="2-10D",
            reason="test momentum",
        )
        insight = SignalInsight(
            action="BUY",
            direction=SignalDirection.LONG,
            score=80.0,
            confidence=80.0,
            quality=80.0,
            expected_pct=None,
            horizon="2-10D",
            regime=MarketRegime.BULL,
            regime_confidence=90.0,
            entry=100.0,
            alphas=(alpha,),
            contributions=(),
            reasons=("base",),
        )
        selection = StrategySelection(
            regime=MarketRegime.BULL,
            active=(),
            research=(),
            excluded=(),
        )
        return AdaptiveSignalResult(
            insight=insight,
            selection=selection,
            selected_model_names=("MomentumAlpha",),
            research_models_included=False,
        )

    def test_snapshot_multiplier_changes_only_alpha_weight(self) -> None:
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={"MomentumAlpha|BULL": 1.25},
            event_probability_offsets={},
            engine_weights={},
        )
        engine = CalibratedAdaptiveSignalEngine(
            snapshot,
            base_engine=FakeAdaptiveEngine(self.base_result()),
        )
        result = engine.analyze(self.frame())

        self.assertTrue(result.calibration_applied)
        self.assertAlmostEqual(result.insight.alphas[0].weight, 1.25)
        self.assertEqual(result.insight.alphas[0].direction, SignalDirection.LONG)
        self.assertEqual(result.insight.alphas[0].confidence, 0.80)
        self.assertEqual(result.base.research_models_included, False)

    def test_empty_snapshot_is_behaviorally_neutral(self) -> None:
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={},
            event_probability_offsets={},
            engine_weights={},
        )
        engine = CalibratedAdaptiveSignalEngine(
            snapshot,
            base_engine=FakeAdaptiveEngine(self.base_result()),
        )
        result = engine.analyze(self.frame())

        self.assertFalse(result.calibration_applied)
        self.assertAlmostEqual(result.insight.alphas[0].weight, 1.0)


if __name__ == "__main__":
    unittest.main()
