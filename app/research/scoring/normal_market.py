from __future__ import annotations

from dataclasses import dataclass
from math import prod
from collections.abc import Iterable, Mapping


@dataclass(frozen=True)
class ClassifiedTradeReturn:
    return_pct: float
    classification: str = "NORMAL"

    @property
    def is_event_related(self) -> bool:
        return str(self.classification).upper() == "EVENT_RELATED"


@dataclass(frozen=True)
class NormalMarketPerformance:
    total_trade_count: int
    normal_trade_count: int
    event_trade_count: int
    normal_return: float
    event_return: float
    normal_profit_factor: float
    event_profit_factor: float
    event_profit_share: float
    normal_win_rate: float

    def to_metrics(self) -> dict[str, float]:
        return {
            "normal_trade_count": float(self.normal_trade_count),
            "event_trade_count": float(self.event_trade_count),
            "normal_return": float(self.normal_return),
            "event_return": float(self.event_return),
            "normal_profit_factor": float(self.normal_profit_factor),
            "event_profit_factor": float(self.event_profit_factor),
            "event_profit_share": float(self.event_profit_share),
            "normal_win_rate": float(self.normal_win_rate),
        }


class NormalMarketPerformanceAnalyzer:
    """Separate repeatable normal-market expectancy from event-driven P/L.

    Returns are expressed in percentage points (e.g. +2.5 means +2.5%). The
    compounded returns use those percentages exactly. Profit factor uses gross
    positive/negative trade returns and is capped to keep research aggregation
    finite when a sample contains no losing trades.
    """

    @staticmethod
    def _compounded_return(values: list[float]) -> float:
        if not values:
            return 0.0
        growth = prod(1.0 + (float(value) / 100.0) for value in values)
        return (growth - 1.0) * 100.0

    @staticmethod
    def _profit_factor(values: list[float]) -> float:
        gains = sum(value for value in values if value > 0)
        losses = abs(sum(value for value in values if value < 0))
        if losses <= 1e-12:
            return 99.0 if gains > 0 else 0.0
        return min(99.0, gains / losses)

    @staticmethod
    def _coerce(item) -> ClassifiedTradeReturn:
        if isinstance(item, ClassifiedTradeReturn):
            return item
        if isinstance(item, Mapping):
            return ClassifiedTradeReturn(
                return_pct=float(item.get("return_pct", item.get("pnl_pct", 0.0))),
                classification=str(item.get("classification", "NORMAL")),
            )
        raise TypeError("trade must be ClassifiedTradeReturn or a mapping")

    def analyze(
        self,
        trades: Iterable[ClassifiedTradeReturn | Mapping],
    ) -> NormalMarketPerformance:
        items = tuple(self._coerce(item) for item in trades)
        normal = [item.return_pct for item in items if not item.is_event_related]
        event = [item.return_pct for item in items if item.is_event_related]

        normal_positive = sum(value for value in normal if value > 0)
        event_positive = sum(value for value in event if value > 0)
        all_positive = normal_positive + event_positive
        event_profit_share = (
            0.0 if all_positive <= 1e-12 else event_positive / all_positive
        )
        normal_wins = sum(value > 0 for value in normal)

        return NormalMarketPerformance(
            total_trade_count=len(items),
            normal_trade_count=len(normal),
            event_trade_count=len(event),
            normal_return=round(self._compounded_return(normal), 6),
            event_return=round(self._compounded_return(event), 6),
            normal_profit_factor=round(self._profit_factor(normal), 6),
            event_profit_factor=round(self._profit_factor(event), 6),
            event_profit_share=round(event_profit_share, 6),
            normal_win_rate=(0.0 if not normal else round(normal_wins / len(normal), 6)),
        )


DEFAULT_NORMAL_MARKET_ANALYZER = NormalMarketPerformanceAnalyzer()
