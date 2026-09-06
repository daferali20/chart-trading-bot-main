from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Mapping

import pandas as pd

from app.analysis.indicators import add_indicators
from app.strategy.signal import analyze as legacy_analyze
from app.strategy.signal_engine import SignalEngine


@dataclass(frozen=True)
class ShadowComparison:
    symbol: str
    observed_at: str
    legacy_action: str
    legacy_score: float
    advanced_action: str
    advanced_score: float
    advanced_confidence: float
    advanced_quality: float
    market_regime: str
    agreement: bool
    score_delta: float
    advanced_reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class ShadowEvaluator:
    """Compare the current legacy signal with Signal Engine v2.

    This module is read-only with respect to trading. It does not import the
    broker, order manager, or ExecutionGate and cannot submit an order.
    """

    def __init__(self, advanced_engine: SignalEngine | None = None) -> None:
        self.advanced_engine = advanced_engine or SignalEngine()

    def compare(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> ShadowComparison:
        legacy_features = add_indicators(df)
        legacy = legacy_analyze(legacy_features)
        advanced = self.advanced_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )

        return ShadowComparison(
            symbol=symbol.upper(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            legacy_action=legacy.action,
            legacy_score=float(legacy.score),
            advanced_action=advanced.action,
            advanced_score=float(advanced.score),
            advanced_confidence=float(advanced.confidence),
            advanced_quality=float(advanced.quality),
            market_regime=advanced.regime.value,
            agreement=legacy.action == advanced.action,
            score_delta=round(float(advanced.score) - float(legacy.score), 2),
            advanced_reasons=advanced.reasons,
        )

    @staticmethod
    def append_log(
        comparison: ShadowComparison,
        path: str | Path = "logs/shadow_decisions.jsonl",
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


DEFAULT_SHADOW_EVALUATOR = ShadowEvaluator()
