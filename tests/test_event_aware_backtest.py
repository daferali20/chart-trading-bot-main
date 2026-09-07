from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.events.models import EventType, NewsEvent
from app.research.scoring.event_aware import EventAwareBacktestAnalyzer


class EventAwareBacktestTests(unittest.TestCase):
    def test_trade_annotation_feeds_normal_market_metrics(self) -> None:
        analyzer = EventAwareBacktestAnalyzer()
        events = (
            NewsEvent(
                symbol="AAA",
                headline="Company announces dilutive secondary offering",
                published_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
                event_type=EventType.OFFERING,
                sentiment=-0.90,
                relevance=1.0,
                novelty=1.0,
            ),
        )
        trades = (
            {
                "symbol": "AAA",
                "entry_time": "2026-01-01T00:00:00+00:00",
                "exit_time": "2026-01-03T00:00:00+00:00",
                "return_pct": 2.0,
            },
            {
                "symbol": "AAA",
                "entry_time": "2026-01-09T00:00:00+00:00",
                "exit_time": "2026-01-11T00:00:00+00:00",
                "return_pct": -5.0,
            },
        )

        report = analyzer.analyze(trades, events, pre_days=0, post_days=0)
        self.assertEqual(report.trades[0].classification, "NORMAL")
        self.assertEqual(report.trades[1].classification, "EVENT_RELATED")
        self.assertEqual(report.trades[1].dominant_event_type, "OFFERING")
        self.assertEqual(report.metrics["normal_trade_count"], 1.0)
        self.assertEqual(report.metrics["event_trade_count"], 1.0)
        self.assertGreater(report.metrics["normal_return"], 0.0)

    def test_invalid_trade_window_is_rejected(self) -> None:
        analyzer = EventAwareBacktestAnalyzer()
        with self.assertRaises(ValueError):
            analyzer.analyze(
                (
                    {
                        "symbol": "AAA",
                        "entry_time": "2026-01-05T00:00:00+00:00",
                        "exit_time": "2026-01-04T00:00:00+00:00",
                        "return_pct": 1.0,
                    },
                ),
                (),
            )


if __name__ == "__main__":
    unittest.main()
