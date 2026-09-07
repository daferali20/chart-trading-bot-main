from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Mapping

import pandas as pd

from app.research.calibration import CalibrationSnapshot
from app.strategy.adaptive_engine import AdaptiveSignalEngine
from app.strategy.calibrated_engine import CalibratedAdaptiveSignalEngine


@dataclass(frozen=True)
class CalibratedShadowComparison:
    symbol: str
    observed_at: str
    market_regime: str
    adaptive_action: str
    adaptive_score: float
    calibrated_action: str
    calibrated_score: float
    score_delta: float
    decision_changed: bool
    calibration_applied: bool
    applied_multipliers: tuple[dict, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class CalibratedShadowEvaluator:
    """Compare regime-adaptive analysis with learned research calibration."""

    def __init__(
        self,
        snapshot: CalibrationSnapshot,
        *,
        adaptive_engine: AdaptiveSignalEngine | None = None,
    ) -> None:
        self.adaptive_engine = adaptive_engine or AdaptiveSignalEngine(
            include_research=False
        )
        self.calibrated_engine = CalibratedAdaptiveSignalEngine(
            snapshot,
            base_engine=self.adaptive_engine,
        )

    def compare(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> CalibratedShadowComparison:
        adaptive = self.adaptive_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )
        calibrated = self.calibrated_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )
        base = adaptive.insight
        learned = calibrated.insight

        return CalibratedShadowComparison(
            symbol=symbol.upper(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            market_regime=learned.regime.value,
            adaptive_action=base.action,
            adaptive_score=float(base.score),
            calibrated_action=learned.action,
            calibrated_score=float(learned.score),
            score_delta=round(float(learned.score) - float(base.score), 2),
            decision_changed=learned.action != base.action,
            calibration_applied=calibrated.calibration_applied,
            applied_multipliers=calibrated.applied_multipliers,
        )

    @staticmethod
    def append_log(
        comparison: CalibratedShadowComparison,
        path: str | Path = "logs/calibrated_shadow_decisions.jsonl",
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
