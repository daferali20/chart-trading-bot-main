from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.analysis.regime import MarketRegime
from app.events.impact import DEFAULT_EVENT_IMPACT_ENGINE, EventImpactEngine
from app.events.models import ImpactForecast, NewsEvent
from app.events.provider import NewsEventProvider


@dataclass(frozen=True)
class NewsIntelligenceResult:
    symbol: str
    events: tuple[NewsEvent, ...]
    forecasts: tuple[ImpactForecast, ...]

    @property
    def strongest(self) -> ImpactForecast | None:
        return self.forecasts[0] if self.forecasts else None


class NewsIntelligenceService:
    """Fetch normalized news and convert it into ranked impact forecasts."""

    def __init__(
        self,
        provider: NewsEventProvider,
        *,
        impact_engine: EventImpactEngine | None = None,
    ) -> None:
        self.provider = provider
        self.impact_engine = impact_engine or DEFAULT_EVENT_IMPACT_ENGINE

    async def analyze(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        market_regime: MarketRegime = MarketRegime.UNKNOWN,
        momentum20: float | None = None,
        rvol: float | None = None,
        gap_pct: float | None = None,
    ) -> NewsIntelligenceResult:
        events = tuple(
            await self.provider.events(
                symbol,
                start=start,
                end=end,
            )
        )

        forecasts = [
            self.impact_engine.forecast(
                event,
                market_regime=market_regime,
                momentum20=momentum20,
                rvol=rvol,
                gap_pct=gap_pct,
            )
            for event in events
        ]

        forecasts.sort(
            key=lambda item: (item.impact_score * item.confidence),
            reverse=True,
        )

        return NewsIntelligenceResult(
            symbol=symbol.upper(),
            events=events,
            forecasts=tuple(forecasts),
        )
