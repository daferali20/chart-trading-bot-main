from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from collections.abc import Iterable, Mapping

from app.events.attribution import EventAttributionEngine
from app.events.models import NewsEvent
from app.research.scoring.normal_market import NormalMarketPerformanceAnalyzer


@dataclass(frozen=True)
class EventAwareTrade:
    symbol: str
    entry_time: str
    exit_time: str
    return_pct: float
    classification: str
    event_count: int
    dominant_event_type: str | None
    dominant_headline: str | None
    max_impact_score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EventAwarePerformanceReport:
    trades: tuple[EventAwareTrade, ...]
    metrics: dict[str, float]


class EventAwareBacktestAnalyzer:
    """Annotate historical trades and compute normal-vs-event performance.

    This helper is research-only. It consumes already-produced trade results and
    historical NewsEvent records; it does not fetch news and cannot place orders.
    """

    def __init__(
        self,
        *,
        attribution_engine: EventAttributionEngine | None = None,
        performance_analyzer: NormalMarketPerformanceAnalyzer | None = None,
    ) -> None:
        self.attribution_engine = attribution_engine or EventAttributionEngine()
        self.performance_analyzer = (
            performance_analyzer or NormalMarketPerformanceAnalyzer()
        )

    @staticmethod
    def _datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _get(item: Mapping, *keys: str):
        for key in keys:
            if key in item:
                return item[key]
        raise KeyError(f"Missing required trade field; expected one of: {keys}")

    def analyze(
        self,
        trades: Iterable[Mapping],
        events: Iterable[NewsEvent],
        *,
        pre_days: int = 1,
        post_days: int = 1,
    ) -> EventAwarePerformanceReport:
        event_items = tuple(events)
        annotated: list[EventAwareTrade] = []

        for raw in trades:
            symbol = str(self._get(raw, "symbol")).upper()
            entry = self._datetime(self._get(raw, "entry_time", "entry_date"))
            exit_ = self._datetime(self._get(raw, "exit_time", "exit_date"))
            return_pct = float(self._get(raw, "return_pct", "pnl_pct"))
            if exit_ < entry:
                raise ValueError("Trade exit_time must not be before entry_time")

            attribution = self.attribution_engine.attribute(
                symbol=symbol,
                entry_time=entry,
                exit_time=exit_,
                events=event_items,
                pre_days=pre_days,
                post_days=post_days,
            )
            annotated.append(
                EventAwareTrade(
                    symbol=symbol,
                    entry_time=entry.isoformat(),
                    exit_time=exit_.isoformat(),
                    return_pct=return_pct,
                    classification=attribution.classification,
                    event_count=attribution.event_count,
                    dominant_event_type=(
                        None
                        if attribution.dominant_event_type is None
                        else attribution.dominant_event_type.value
                    ),
                    dominant_headline=attribution.dominant_headline,
                    max_impact_score=attribution.max_impact_score,
                )
            )

        performance = self.performance_analyzer.analyze(
            {
                "return_pct": trade.return_pct,
                "classification": trade.classification,
            }
            for trade in annotated
        )
        metrics = performance.to_metrics()
        metrics["event_attributed_trade_count"] = float(
            sum(trade.classification == "EVENT_RELATED" for trade in annotated)
        )
        metrics["normal_attributed_trade_count"] = float(
            sum(trade.classification == "NORMAL" for trade in annotated)
        )

        return EventAwarePerformanceReport(
            trades=tuple(annotated),
            metrics=metrics,
        )


DEFAULT_EVENT_AWARE_BACKTEST_ANALYZER = EventAwareBacktestAnalyzer()
