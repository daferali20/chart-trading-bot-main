from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from collections.abc import Iterable

from app.events.impact import DEFAULT_EVENT_IMPACT_ENGINE
from app.events.models import EventType, NewsEvent


@dataclass(frozen=True)
class TradeEventAttribution:
    symbol: str
    classification: str
    event_count: int
    dominant_event_type: EventType | None
    dominant_headline: str | None
    max_impact_score: float
    reasons: tuple[str, ...]


class EventAttributionEngine:
    """Separate normal-market trades from event-related trades.

    Events are matched to the trade window with a small configurable buffer.
    A trade is EVENT_RELATED only when at least one nearby event carries a
    sufficiently large modeled impact score; otherwise it remains NORMAL.
    """

    def __init__(self, impact_threshold: float = 35.0) -> None:
        self.impact_threshold = float(impact_threshold)

    def attribute(
        self,
        *,
        symbol: str,
        entry_time: datetime,
        exit_time: datetime,
        events: Iterable[NewsEvent],
        pre_days: int = 1,
        post_days: int = 1,
    ) -> TradeEventAttribution:
        symbol = symbol.upper()
        start = entry_time - timedelta(days=max(0, pre_days))
        end = exit_time + timedelta(days=max(0, post_days))

        matched: list[tuple[NewsEvent, float]] = []
        for event in events:
            if event.symbol.upper() != symbol:
                continue
            if start <= event.published_at <= end:
                forecast = DEFAULT_EVENT_IMPACT_ENGINE.forecast(event)
                matched.append((event, forecast.impact_score))

        if not matched:
            return TradeEventAttribution(
                symbol=symbol,
                classification="NORMAL",
                event_count=0,
                dominant_event_type=None,
                dominant_headline=None,
                max_impact_score=0.0,
                reasons=("No material event matched the trade window",),
            )

        matched.sort(key=lambda item: item[1], reverse=True)
        dominant_event, max_score = matched[0]
        classification = "EVENT_RELATED" if max_score >= self.impact_threshold else "NORMAL"

        reasons = [
            f"{len(matched)} event(s) matched trade window",
            f"dominant={dominant_event.event_type.value}",
            f"max_impact={max_score:.1f}",
        ]
        if classification == "NORMAL":
            reasons.append("Nearby events were below material-impact threshold")

        return TradeEventAttribution(
            symbol=symbol,
            classification=classification,
            event_count=len(matched),
            dominant_event_type=dominant_event.event_type,
            dominant_headline=dominant_event.headline,
            max_impact_score=max_score,
            reasons=tuple(reasons),
        )


DEFAULT_EVENT_ATTRIBUTION_ENGINE = EventAttributionEngine()
