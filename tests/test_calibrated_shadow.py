from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.research.calibration import CalibrationSnapshot
from app.shadow_calibrated import CalibratedShadowEvaluator
from app.strategy.adaptive_engine import AdaptiveSignalResult
from app.strategy.fusion import AlphaSignal, SignalDirection
from app.strategy.selector import StrategySelection
from app.strategy.signal_engine import SignalInsight


class FakeAdaptiveEngine:
    def __init__(self, result: AdaptiveSignalResult) -> None:
        self.result = result

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return self.result


class CalibratedShadowTests(unittest.TestCase):
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
    def adaptive_result() -> AdaptiveSignalResult:
        alpha = AlphaSignal(
            name="MomentumAlpha",
            direction=SignalDirection.LONG,
            confidence=0.80,
            quality=0.80,
            weight=1.0,
            horizon="2-10D",
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
            reasons=("test",),
        )
        return AdaptiveSignalResult(
            insight=insight,
            selection=StrategySelection(
                regime=MarketRegime.BULL,
                active=(),
                research=(),
                excluded=(),
            ),
            selected_model_names=("MomentumAlpha",),
            research_models_included=False,
        )

    def test_comparison_records_applied_multiplier(self) -> None:
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={"MomentumAlpha|BULL": 1.20},
            event_probability_offsets={},
            engine_weights={},
        )
        evaluator = CalibratedShadowEvaluator(
            snapshot,
            adaptive_engine=FakeAdaptiveEngine(self.adaptive_result()),
        )
        result = evaluator.compare("aaa", self.frame())

        self.assertEqual(result.symbol, "AAA")
        self.assertTrue(result.calibration_applied)
        self.assertEqual(result.market_regime, "BULL")
        self.assertAlmostEqual(result.applied_multipliers[0]["multiplier"], 1.20)


if __name__ == "__main__":
    unittest.main()
