"""News/event intelligence for research and decision context.

This package is analysis-only. It does not import broker or execution modules.
"""

from app.events.models import EventType, NewsEvent, ImpactForecast
from app.events.classifier import EventClassifier
from app.events.impact import EventImpactEngine
from app.events.alpha import EventAlphaAdapter
from app.events.attribution import EventAttributionEngine, TradeEventAttribution
from app.events.provider import NewsEventProvider
from app.events.sentiment import FinancialHeadlineSentiment
from app.events.serpapi_provider import SerpApiNewsProvider

__all__ = [
    "EventType",
    "NewsEvent",
    "ImpactForecast",
    "EventClassifier",
    "EventImpactEngine",
    "EventAlphaAdapter",
    "EventAttributionEngine",
    "TradeEventAttribution",
    "NewsEventProvider",
    "FinancialHeadlineSentiment",
    "SerpApiNewsProvider",
]
