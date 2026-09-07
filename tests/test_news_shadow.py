from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.events.models import EventType, ImpactForecast
from app.shadow_news import NewsShadowEvaluator
from app.strategy.fusion import AlphaSignal, SignalDirection
from app.strategy.signal_engine import SignalInsight


class FakeSignalEngine:
    def __init__(self, insight: SignalInsight) -> None:
        self.insight = insight

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return self.insight


class NewsShadowEvaluatorTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=30, freq="D"),
                "open": [100.0] * 30,
                "high": [101.0] * 30,
                "low": [99.0] * 30,
                "close": [100.0] * 30,
                "volume": [1_000_000] * 30,
            }
        )

    @staticmethod
    def technical_buy() -> SignalInsight:
        alpha = AlphaSignal(
            name="TechnicalAlpha",
            direction=SignalDirection.LONG,
            confidence=0.55,
            quality=0.75,
            weight=1.0,
            horizon="5-20D",
            reason="technical long",
        )
        return SignalInsight(
            action="BUY",
            direction=SignalDirection.LONG,
            score=80.0,
            confidence=80.0,
            quality=80.0,
            expected_pct=None,
            horizon="5-20D",
            regime=MarketRegime.BULL,
            regime_confidence=90.0,
            entry=100.0,
            alphas=(alpha,),
            contributions=(),
            reasons=("technical long",),
        )

    @staticmethod
    def negative_offering() -> ImpactForecast:
        return ImpactForecast(
            symbol="AAA",
            event_type=EventType.OFFERING,
            direction="DOWN",
            probability_up=0.03,
            probability_down=0.95,
            probability_neutral=0.02,
            impact_score=95.0,
            expected_move_low_pct=5.0,
            expected_move_high_pct=12.0,
            horizon="1-7D",
            risk_level="HIGH",
            confidence=95.0,
            reasons=("dilutive offering",),
        )

    def test_no_news_leaves_technical_decision_unchanged(self) -> None:
        evaluator = NewsShadowEvaluator(
            signal_engine=FakeSignalEngine(self.technical_buy())
        )
        result = evaluator.compare("AAA", self.frame(), forecasts=())

        self.assertEqual(result.technical_action, "BUY")
        self.assertEqual(result.combined_action, "BUY")
        self.assertEqual(result.score_delta, 0.0)
        self.assertFalse(result.decision_changed)
        self.assertIsNone(result.event_type)

    def test_strong_negative_news_can_cancel_technical_buy_in_shadow(self) -> None:
        evaluator = NewsShadowEvaluator(
            signal_engine=FakeSignalEngine(self.technical_buy())
        )
        result = evaluator.compare(
            "AAA",
            self.frame(),
            forecasts=(self.negative_offering(),),
        )

        self.assertEqual(result.technical_action, "BUY")
        self.assertEqual(result.event_type, EventType.OFFERING.value)
        self.assertEqual(result.event_direction, "DOWN")
        self.assertEqual(result.combined_action, "HOLD")
        self.assertTrue(result.decision_changed)
        self.assertLess(result.combined_score, result.technical_score)

    def test_only_strongest_event_is_added_to_fusion(self) -> None:
        evaluator = NewsShadowEvaluator(
            signal_engine=FakeSignalEngine(self.technical_buy())
        )
        weaker = ImpactForecast(
            symbol="AAA",
            event_type=EventType.ANALYST_RATING,
            direction="UP",
            probability_up=0.60,
            probability_down=0.20,
            probability_neutral=0.20,
            impact_score=20.0,
            expected_move_low_pct=1.0,
            expected_move_high_pct=3.0,
            horizon="1-10D",
            risk_level="LOW",
            confidence=50.0,
            reasons=("upgrade",),
        )
        result = evaluator.compare(
            "AAA",
            self.frame(),
            forecasts=(weaker, self.negative_offering()),
        )

        self.assertEqual(result.event_type, EventType.OFFERING.value)
        self.assertEqual(result.event_direction, "DOWN")


if __name__ == "__main__":
    unittest.main()
