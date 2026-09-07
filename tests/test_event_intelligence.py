from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.analysis.regime import MarketRegime
from app.events.classifier import EventClassifier
from app.events.impact import EventImpactEngine
from app.events.models import EventType, NewsEvent


class EventIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = EventClassifier()
        self.engine = EventImpactEngine()
        self.now = datetime(2026, 9, 7, tzinfo=timezone.utc)

    def test_classifier_detects_common_event_types(self) -> None:
        self.assertEqual(
            self.classifier.classify("Company raises guidance after quarterly results"),
            EventType.EARNINGS,
        )
        self.assertEqual(
            self.classifier.classify("Company prices secondary offering"),
            EventType.OFFERING,
        )

    def test_strong_positive_earnings_event_has_upside_bias(self) -> None:
        event = NewsEvent(
            symbol="AAA",
            headline="Earnings beat and guidance raised",
            published_at=self.now,
            event_type=EventType.EARNINGS,
            sentiment=0.85,
            relevance=1.0,
            novelty=0.95,
            surprise_pct=12.0,
        )
        result = self.engine.forecast(
            event,
            market_regime=MarketRegime.BULL,
            momentum20=8.0,
            rvol=2.0,
        )
        self.assertEqual(result.direction, "UP")
        self.assertGreater(result.probability_up, result.probability_down)
        self.assertGreater(result.impact_score, 50.0)
        self.assertAlmostEqual(
            result.probability_up + result.probability_down + result.probability_neutral,
            1.0,
            places=6,
        )

    def test_negative_offering_event_has_downside_bias(self) -> None:
        event = NewsEvent(
            symbol="BBB",
            headline="Company announces dilutive secondary offering",
            published_at=self.now,
            event_type=EventType.OFFERING,
            sentiment=-0.90,
            relevance=1.0,
            novelty=1.0,
        )
        result = self.engine.forecast(event, market_regime=MarketRegime.BEAR)
        self.assertEqual(result.direction, "DOWN")
        self.assertGreater(result.probability_down, result.probability_up)
        self.assertEqual(result.risk_level, "HIGH")

    def test_low_relevance_news_is_not_overconfident(self) -> None:
        event = NewsEvent(
            symbol="CCC",
            headline="Minor mention in industry article",
            published_at=self.now,
            event_type=EventType.OTHER,
            sentiment=0.80,
            relevance=0.15,
            novelty=0.20,
        )
        result = self.engine.forecast(event)
        self.assertLess(result.impact_score, 20.0)
        self.assertLess(result.confidence, 60.0)


if __name__ == "__main__":
    unittest.main()
