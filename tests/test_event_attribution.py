from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.events.alpha import EventAlphaAdapter
from app.events.attribution import EventAttributionEngine
from app.events.impact import EventImpactEngine
from app.events.models import EventType, NewsEvent
from app.strategy.fusion import SignalDirection


class EventAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def test_trade_without_nearby_event_is_normal(self) -> None:
        engine = EventAttributionEngine()
        result = engine.attribute(
            symbol="AAA",
            entry_time=self.t0,
            exit_time=self.t0 + timedelta(days=3),
            events=[],
        )
        self.assertEqual(result.classification, "NORMAL")
        self.assertEqual(result.event_count, 0)

    def test_material_earnings_event_marks_trade_event_related(self) -> None:
        event = NewsEvent(
            symbol="AAA",
            headline="Company beats earnings and raises outlook",
            published_at=self.t0 + timedelta(days=1),
            event_type=EventType.EARNINGS,
            sentiment=0.9,
            relevance=1.0,
            novelty=1.0,
            surprise_pct=15.0,
        )
        result = EventAttributionEngine().attribute(
            symbol="AAA",
            entry_time=self.t0,
            exit_time=self.t0 + timedelta(days=3),
            events=[event],
        )
        self.assertEqual(result.classification, "EVENT_RELATED")
        self.assertEqual(result.dominant_event_type, EventType.EARNINGS)
        self.assertGreater(result.max_impact_score, 35.0)

    def test_naive_trade_times_are_normalized_against_utc_news(self) -> None:
        event = NewsEvent(
            symbol="AAA",
            headline="Company beats earnings and raises outlook",
            published_at=self.t0 + timedelta(hours=12),
            event_type=EventType.EARNINGS,
            sentiment=0.9,
            relevance=1.0,
            novelty=1.0,
        )
        result = EventAttributionEngine().attribute(
            symbol="AAA",
            entry_time=datetime(2026, 9, 1),
            exit_time=datetime(2026, 9, 2),
            events=[event],
            pre_days=0,
            post_days=0,
        )
        self.assertEqual(result.classification, "EVENT_RELATED")

    def test_invalid_trade_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EventAttributionEngine().attribute(
                symbol="AAA",
                entry_time=self.t0 + timedelta(days=2),
                exit_time=self.t0,
                events=[],
            )

    def test_event_forecast_can_be_adapted_to_optional_alpha(self) -> None:
        event = NewsEvent(
            symbol="BBB",
            headline="Company announces dilutive offering",
            published_at=self.t0,
            event_type=EventType.OFFERING,
            sentiment=-0.9,
            relevance=1.0,
            novelty=1.0,
        )
        forecast = EventImpactEngine().forecast(event)
        alpha = EventAlphaAdapter().to_alpha(forecast)
        self.assertEqual(alpha.direction, SignalDirection.SHORT)
        self.assertGreater(alpha.confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
