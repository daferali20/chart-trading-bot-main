from __future__ import annotations

from app.events.models import EventType


class EventClassifier:
    """Lightweight event taxonomy used before a richer NLP provider is attached."""

    KEYWORDS: tuple[tuple[EventType, tuple[str, ...]], ...] = (
        (EventType.EARNINGS, ("earnings", "quarterly results", "eps", "revenue")),
        (EventType.GUIDANCE, ("guidance", "outlook", "forecast", "raises outlook", "cuts outlook")),
        (EventType.M_AND_A, ("acquire", "acquisition", "merger", "buyout", "takeover")),
        (EventType.FDA, ("fda", "clinical trial", "phase 3", "approval", "drug")),
        (EventType.CONTRACT, ("contract", "award", "partnership", "deal", "order")),
        (EventType.OFFERING, ("offering", "secondary offering", "share sale", "dilution", "convertible notes")),
        (EventType.REGULATORY, ("regulator", "sec", "antitrust", "investigation", "probe")),
        (EventType.ANALYST_RATING, ("upgrade", "downgrade", "price target", "initiates coverage")),
        (EventType.MACRO, ("federal reserve", "fed", "cpi", "inflation", "jobs report", "interest rate")),
        (EventType.MANAGEMENT, ("ceo", "cfo", "resigns", "appointed", "management change")),
        (EventType.PRODUCT, ("launch", "new product", "release", "shipment", "production")),
        (EventType.LEGAL, ("lawsuit", "court", "settlement", "patent", "legal")),
    )

    def classify(self, headline: str, body: str = "") -> EventType:
        text = f"{headline} {body}".lower()
        for event_type, keywords in self.KEYWORDS:
            if any(keyword in text for keyword in keywords):
                return event_type
        return EventType.OTHER


DEFAULT_EVENT_CLASSIFIER = EventClassifier()
