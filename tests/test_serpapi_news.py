from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.analysis.regime import MarketRegime
from app.events.models import EventType, NewsEvent
from app.events.serpapi_provider import SerpApiNewsProvider
from app.events.service import NewsIntelligenceService
from app.events.sentiment import FinancialHeadlineSentiment


class SerpApiNewsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_normalizes_google_news_results(self) -> None:
        provider = SerpApiNewsProvider("test-key", max_results=10)
        payload = {
            "news_results": [
                {
                    "title": "AAPL earnings beat estimates as revenue hits record",
                    "link": "https://example.com/aapl-earnings",
                    "iso_date": "2026-09-06T20:00:00Z",
                    "source": {"name": "Reuters"},
                    "snippet": "Apple reports stronger quarterly results.",
                },
                {
                    "title": "Old AAPL article",
                    "link": "https://example.com/old",
                    "iso_date": "2026-08-01T20:00:00Z",
                    "source": {"name": "Example"},
                },
            ]
        }

        with patch.object(provider, "_request_json", return_value=payload):
            events = await provider.events(
                "AAPL",
                start=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.symbol, "AAPL")
        self.assertEqual(event.source, "Reuters")
        self.assertEqual(event.url, "https://example.com/aapl-earnings")
        self.assertEqual(event.provider, "serpapi_google_news")
        self.assertEqual(event.event_type, EventType.EARNINGS)
        self.assertGreater(event.sentiment, 0.0)
        self.assertIsNotNone(event.published_at.tzinfo)

    async def test_provider_deduplicates_grouped_story(self) -> None:
        provider = SerpApiNewsProvider("test-key")
        article = {
            "title": "AAPL wins contract award",
            "link": "https://example.com/deal",
            "iso_date": "2026-09-06T18:00:00+00:00",
            "source": {"name": "Example"},
        }
        payload = {
            "news_results": [
                {**article, "stories": [dict(article)]},
            ]
        }

        with patch.object(provider, "_request_json", return_value=payload):
            events = await provider.events("AAPL")

        self.assertEqual(len(events), 1)

    async def test_missing_api_key_fails_explicitly(self) -> None:
        provider = SerpApiNewsProvider("")
        with self.assertRaisesRegex(RuntimeError, "SERPAPI_API_KEY"):
            await provider.events("AAPL")


class FinancialHeadlineSentimentTests(unittest.TestCase):
    def test_positive_and_negative_financial_headlines_separate(self) -> None:
        model = FinancialHeadlineSentiment()
        positive = model.score("Company beats estimates and raises guidance")
        negative = model.score("Company misses estimates and cuts guidance")
        self.assertGreater(positive, 0.5)
        self.assertLess(negative, -0.5)


class FakeProvider:
    async def events(self, symbol, *, start=None, end=None):
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        return (
            NewsEvent(
                symbol=symbol,
                headline="Earnings beat and guidance raised",
                published_at=now,
                event_type=EventType.EARNINGS,
                sentiment=0.85,
                relevance=1.0,
                novelty=1.0,
            ),
            NewsEvent(
                symbol=symbol,
                headline="Minor product mention",
                published_at=now,
                event_type=EventType.PRODUCT,
                sentiment=0.15,
                relevance=0.5,
                novelty=0.5,
            ),
        )


class NewsIntelligenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_ranks_strongest_event_forecast_first(self) -> None:
        service = NewsIntelligenceService(FakeProvider())
        result = await service.analyze(
            "AAPL",
            market_regime=MarketRegime.BULL,
            momentum20=6.0,
            rvol=1.8,
        )

        self.assertEqual(len(result.events), 2)
        self.assertEqual(len(result.forecasts), 2)
        self.assertIsNotNone(result.strongest)
        self.assertEqual(result.strongest.event_type, EventType.EARNINGS)
        self.assertEqual(result.strongest.direction, "UP")


if __name__ == "__main__":
    unittest.main()
