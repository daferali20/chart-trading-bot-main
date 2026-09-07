from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Mapping, Sequence

import pandas as pd

from app.events.alpha import EventAlphaAdapter
from app.events.models import ImpactForecast
from app.strategy.fusion import DEFAULT_FUSION_ENGINE, SignalDirection
from app.strategy.signal_engine import SignalEngine, SignalInsight


@dataclass(frozen=True)
class NewsShadowComparison:
    symbol: str
    observed_at: str
    technical_action: str
    technical_score: float
    technical_confidence: float
    market_regime: str
    event_type: str | None
    event_direction: str | None
    event_impact_score: float | None
    event_confidence: float | None
    probability_up: float | None
    probability_down: float | None
    combined_action: str
    combined_score: float
    combined_confidence: float
    combined_quality: float
    score_delta: float
    decision_changed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class NewsShadowEvaluator:
    """Research-only comparison of technical Signal Engine v2 vs news-aware fusion.

    Only the single strongest recent event is added to fusion. This prevents
    syndicated copies of one story from multiplying the effective news vote.
    The evaluator has no broker, portfolio, risk, or execution imports.
    """

    def __init__(
        self,
        signal_engine: SignalEngine | None = None,
        *,
        event_adapter: EventAlphaAdapter | None = None,
        buy_score_threshold: float = 65.0,
        sell_score_threshold: float = 65.0,
    ) -> None:
        self.signal_engine = signal_engine or SignalEngine()
        self.event_adapter = event_adapter or EventAlphaAdapter()
        self.buy_score_threshold = float(buy_score_threshold)
        self.sell_score_threshold = float(sell_score_threshold)

    @staticmethod
    def _strongest(forecasts: Sequence[ImpactForecast]) -> ImpactForecast | None:
        if not forecasts:
            return None
        return max(
            forecasts,
            key=lambda item: float(item.impact_score) * float(item.confidence),
        )

    def _action(self, direction: SignalDirection, score: float) -> str:
        if direction is SignalDirection.LONG and score >= self.buy_score_threshold:
            return "BUY"
        if direction is SignalDirection.SHORT and score >= self.sell_score_threshold:
            return "SELL"
        return "HOLD"

    def compare(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        forecasts: Sequence[ImpactForecast] = (),
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
        technical: SignalInsight | None = None,
    ) -> NewsShadowComparison:
        technical_insight = technical or self.signal_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )

        strongest = self._strongest(forecasts)
        if strongest is None:
            return NewsShadowComparison(
                symbol=symbol.upper(),
                observed_at=datetime.now(timezone.utc).isoformat(),
                technical_action=technical_insight.action,
                technical_score=float(technical_insight.score),
                technical_confidence=float(technical_insight.confidence),
                market_regime=technical_insight.regime.value,
                event_type=None,
                event_direction=None,
                event_impact_score=None,
                event_confidence=None,
                probability_up=None,
                probability_down=None,
                combined_action=technical_insight.action,
                combined_score=float(technical_insight.score),
                combined_confidence=float(technical_insight.confidence),
                combined_quality=float(technical_insight.quality),
                score_delta=0.0,
                decision_changed=False,
                reason="No qualifying recent news event",
            )

        event_alpha = self.event_adapter.to_alpha(strongest)
        fused = DEFAULT_FUSION_ENGINE.fuse(
            (*technical_insight.alphas, event_alpha),
            regime=technical_insight.regime,
        )
        combined_action = self._action(fused.direction, fused.score)

        return NewsShadowComparison(
            symbol=symbol.upper(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            technical_action=technical_insight.action,
            technical_score=float(technical_insight.score),
            technical_confidence=float(technical_insight.confidence),
            market_regime=technical_insight.regime.value,
            event_type=strongest.event_type.value,
            event_direction=strongest.direction,
            event_impact_score=float(strongest.impact_score),
            event_confidence=float(strongest.confidence),
            probability_up=float(strongest.probability_up),
            probability_down=float(strongest.probability_down),
            combined_action=combined_action,
            combined_score=float(fused.score),
            combined_confidence=float(fused.confidence),
            combined_quality=float(fused.quality),
            score_delta=round(float(fused.score) - float(technical_insight.score), 2),
            decision_changed=combined_action != technical_insight.action,
            reason=(
                f"Strongest event {strongest.event_type.value} {strongest.direction}; "
                f"impact={strongest.impact_score:.1f}; confidence={strongest.confidence:.1f}%"
            ),
        )

    @staticmethod
    def append_log(
        comparison: NewsShadowComparison,
        path: str | Path = "logs/news_shadow_decisions.jsonl",
    ) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    comparison.to_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
        return destination


DEFAULT_NEWS_SHADOW_EVALUATOR = NewsShadowEvaluator()
