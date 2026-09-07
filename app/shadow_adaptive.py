from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Mapping

import pandas as pd

from app.strategy.adaptive_engine import AdaptiveSignalEngine
from app.strategy.signal_engine import SignalEngine


@dataclass(frozen=True)
class AdaptiveShadowComparison:
    symbol: str
    observed_at: str
    market_regime: str
    static_action: str
    static_score: float
    adaptive_action: str
    adaptive_score: float
    score_delta: float
    decision_changed: bool
    selected_models: tuple[str, ...]
    research_models_included: bool

    def to_dict(self) -> dict:
        return asdict(self)


class AdaptiveShadowEvaluator:
    """Compare static Signal Engine v2 with regime-selected alpha routing."""

    def __init__(
        self,
        *,
        static_engine: SignalEngine | None = None,
        adaptive_engine: AdaptiveSignalEngine | None = None,
    ) -> None:
        self.static_engine = static_engine or SignalEngine()
        self.adaptive_engine = adaptive_engine or AdaptiveSignalEngine(
            include_research=False
        )

    def compare(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> AdaptiveShadowComparison:
        static = self.static_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )
        adaptive_result = self.adaptive_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )
        adaptive = adaptive_result.insight

        return AdaptiveShadowComparison(
            symbol=symbol.upper(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            market_regime=adaptive.regime.value,
            static_action=static.action,
            static_score=float(static.score),
            adaptive_action=adaptive.action,
            adaptive_score=float(adaptive.score),
            score_delta=round(float(adaptive.score) - float(static.score), 2),
            decision_changed=adaptive.action != static.action,
            selected_models=adaptive_result.selected_model_names,
            research_models_included=adaptive_result.research_models_included,
        )

    @staticmethod
    def append_log(
        comparison: AdaptiveShadowComparison,
        path: str | Path = "logs/adaptive_shadow_decisions.jsonl",
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


DEFAULT_ADAPTIVE_SHADOW_EVALUATOR = AdaptiveShadowEvaluator()
