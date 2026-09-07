from __future__ import annotations

from collections.abc import Mapping

from app.config import settings
from app.events.serpapi_provider import SerpApiNewsProvider
from app.events.service import NewsIntelligenceService


def build_serpapi_news_service(
    *,
    aliases: Mapping[str, str] | None = None,
) -> NewsIntelligenceService:
    """Build the configured SerpAPI news service from application settings."""

    provider = SerpApiNewsProvider(
        settings.serpapi_api_key,
        gl=settings.serpapi_gl,
        hl=settings.serpapi_hl,
        max_results=settings.serpapi_news_limit,
        timeout_seconds=settings.serpapi_timeout_seconds,
        aliases=dict(aliases or {}),
    )
    return NewsIntelligenceService(provider)
