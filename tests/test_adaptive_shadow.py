from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.shadow_adaptive import AdaptiveShadowEvaluator
from app.strategy.adaptive_engine import AdaptiveSignalResult
from app.strategy.fusion import SignalDirection
from app.strategy.selector import StrategySelection
from app.strategy.signal_engine import SignalInsight


class FakeStaticEngine:
    def __init__(self, insight: SignalInsight) -> None:
        self.insight = insight

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return self.insight


class FakeAdaptiveEngine:
    def __init__(self, result: AdaptiveSignalResult) -> None:
        self.result = result

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return self.result


class AdaptiveShadowTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=20, freq="D"),
                "open": [100.0] * 20,
                "high": [101.0] * 20,
                "low": [99.0] * 20,
                "close": [100.0] * 20,
                "volume": [1_000_000.0] * 20,
            }
        )

    @staticmethod
    def insight(action: str, score: float) -> SignalInsight:
        direction = SignalDirection.LONG if action == "BUY" else SignalDirection.NEUTRAL
        return SignalInsight(
            action=action,
            direction=direction,
            score=score,
            confidence=75.0,
            quality=80.0,
            expected_pct=None,
            horizon="5-20D",
            regime=MarketRegime.SIDEWAYS,
            regime_confidence=80.0,
            entry=100.0,
            alphas=(),
            contributions=(),
            reasons=("test",),
        )

    def test_shadow_records_static_vs_adaptive_difference(self) -> None:
        static = self.insight("BUY", 70.0)
        adaptive_insight = self.insight("HOLD", 54.0)
        selection = StrategySelection(
            regime=MarketRegime.SIDEWAYS,
            active=(),
            research=(),
            excluded=(),
        )
        adaptive = AdaptiveSignalResult(
            insight=adaptive_insight,
            selection=selection,
            selected_model_names=("WEMA5_BASELINE_v1", "VolumeAlpha"),
            research_models_included=False,
        )
        evaluator = AdaptiveShadowEvaluator(
            static_engine=FakeStaticEngine(static),
            adaptive_engine=FakeAdaptiveEngine(adaptive),
        )

        result = evaluator.compare("aaa", self.frame())

        self.assertEqual(result.symbol, "AAA")
        self.assertEqual(result.static_action, "BUY")
        self.assertEqual(result.adaptive_action, "HOLD")
        self.assertEqual(result.score_delta, -16.0)
        self.assertTrue(result.decision_changed)
        self.assertEqual(
            result.selected_models,
            ("WEMA5_BASELINE_v1", "VolumeAlpha"),
        )


if __name__ == "__main__":
    unittest.main()
