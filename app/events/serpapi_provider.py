from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.events.classifier import DEFAULT_EVENT_CLASSIFIER, EventClassifier
from app.events.models import NewsEvent
from app.events.provider import NewsEventProvider
from app.events.sentiment import DEFAULT_FINANCIAL_SENTIMENT, FinancialHeadlineSentiment


class SerpApiNewsProvider(NewsEventProvider):
    """SerpAPI Google News adapter.

    The provider only fetches and normalizes news. It never imports broker,
    portfolio, risk, or execution code.
    """

    ENDPOINT = "https://serpapi.com/search.json"

    def __init__(
        self,
        api_key: str,
        *,
        gl: str = "us",
        hl: str = "en",
        max_results: int = 20,
        timeout_seconds: float = 12.0,
        aliases: dict[str, str] | None = None,
        classifier: EventClassifier | None = None,
        sentiment: FinancialHeadlineSentiment | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.gl = gl
        self.hl = hl
        self.max_results = max(1, int(max_results))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.aliases = {key.upper(): value for key, value in (aliases or {}).items()}
        self.classifier = classifier or DEFAULT_EVENT_CLASSIFIER
        self.sentiment = sentiment or DEFAULT_FINANCIAL_SENTIMENT

    def _query(self, symbol: str) -> str:
        symbol = symbol.upper().strip()
        alias = self.aliases.get(symbol)
        if alias:
            return f'"{symbol}" OR "{alias}" stock'
        return f'"{symbol}" stock OR shares'

    def _request_json(self, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.ENDPOINT}?{urlencode(params)}"
        request = Request(
            url,
            headers={"User-Agent": "chart-trading-bot/1.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpAPI returned a non-object JSON payload")
        if payload.get("error"):
            raise RuntimeError(f"SerpAPI error: {payload['error']}")
        return payload

    @staticmethod
    def _iter_articles(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        def walk(value: Any) -> Iterable[dict[str, Any]]:
            if isinstance(value, dict):
                if value.get("title") and (
                    value.get("link")
                    or value.get("source")
                    or value.get("iso_date")
                    or value.get("published_at")
                ):
                    yield value
                for key in ("stories", "news_results", "highlight"):
                    nested = value.get(key)
                    if nested is not None:
                        yield from walk(nested)
            elif isinstance(value, list):
                for item in value:
                    yield from walk(item)

        yield from walk(payload.get("news_results", []))
        if payload.get("highlight") is not None:
            yield from walk(payload["highlight"])

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _source_name(raw: Any) -> str:
        if isinstance(raw, dict):
            return str(raw.get("name") or "").strip()
        return str(raw or "").strip()

    def _normalize_article(self, symbol: str, item: dict[str, Any]) -> NewsEvent | None:
        headline = str(item.get("title") or "").strip()
        if not headline:
            return None

        published_at = self._parse_datetime(
            item.get("iso_date") or item.get("published_at")
        )
        # Accurate timestamps matter for event attribution. Relative strings
        # such as "2 hours ago" are intentionally not guessed here.
        if published_at is None:
            return None

        body = str(item.get("snippet") or "").strip()
        source = self._source_name(item.get("source"))
        url = str(item.get("link") or "").strip()
        event_type = self.classifier.classify(headline, body)
        sentiment = self.sentiment.score(headline, body)

        text = f"{headline} {body}".upper()
        symbol_upper = symbol.upper()
        relevance = 1.0 if symbol_upper in text else 0.82

        return NewsEvent(
            symbol=symbol_upper,
            headline=headline,
            published_at=published_at,
            source=source,
            body=body,
            url=url,
            provider="serpapi_google_news",
            event_type=event_type,
            sentiment=sentiment,
            relevance=relevance,
            novelty=1.0,
        )

    async def events(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Sequence[NewsEvent]:
        if not self.api_key:
            raise RuntimeError("SERPAPI_API_KEY is not configured")

        params = {
            "engine": "google_news",
            "q": self._query(symbol),
            "gl": self.gl,
            "hl": self.hl,
            "api_key": self.api_key,
        }
        payload = await asyncio.to_thread(self._request_json, params)

        start_utc = self._as_utc(start)
        end_utc = self._as_utc(end)
        dedup: set[str] = set()
        normalized: list[NewsEvent] = []

        for item in self._iter_articles(payload):
            event = self._normalize_article(symbol, item)
            if event is None:
                continue
            if start_utc is not None and event.published_at < start_utc:
                continue
            if end_utc is not None and event.published_at > end_utc:
                continue

            key = event.url or f"{event.source}|{event.headline}".lower()
            if key in dedup:
                continue
            dedup.add(key)
            normalized.append(event)
            if len(normalized) >= self.max_results:
                break

        normalized.sort(key=lambda item: item.published_at, reverse=True)
        return tuple(normalized)
