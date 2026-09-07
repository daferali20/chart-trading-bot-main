from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    EARNINGS = "EARNINGS"
    GUIDANCE = "GUIDANCE"
    M_AND_A = "M_AND_A"
    FDA = "FDA"
    CONTRACT = "CONTRACT"
    OFFERING = "OFFERING"
    REGULATORY = "REGULATORY"
    ANALYST_RATING = "ANALYST_RATING"
    MACRO = "MACRO"
    MANAGEMENT = "MANAGEMENT"
    PRODUCT = "PRODUCT"
    LEGAL = "LEGAL"
    OTHER = "OTHER"


@dataclass(frozen=True)
class NewsEvent:
    symbol: str
    headline: str
    published_at: datetime
    source: str = ""
    body: str = ""
    url: str = ""
    provider: str = ""
    event_type: EventType = EventType.OTHER
    sentiment: float = 0.0
    relevance: float = 1.0
    novelty: float = 1.0
    surprise_pct: float | None = None

    def __post_init__(self) -> None:
        if not -1.0 <= self.sentiment <= 1.0:
            raise ValueError("sentiment must be between -1 and 1")
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("relevance must be between 0 and 1")
        if not 0.0 <= self.novelty <= 1.0:
            raise ValueError("novelty must be between 0 and 1")


@dataclass(frozen=True)
class ImpactForecast:
    symbol: str
    event_type: EventType
    direction: str
    probability_up: float
    probability_down: float
    probability_neutral: float
    impact_score: float
    expected_move_low_pct: float
    expected_move_high_pct: float
    horizon: str
    risk_level: str
    confidence: float
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        total = self.probability_up + self.probability_down + self.probability_neutral
        if abs(total - 1.0) > 1e-6:
            raise ValueError("forecast probabilities must sum to 1")
