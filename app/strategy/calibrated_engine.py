from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

import pandas as pd

from app.research.calibration import CalibrationSnapshot, ReliabilityCalibrator
from app.strategy.adaptive_engine import AdaptiveSignalEngine, AdaptiveSignalResult
from app.strategy.fusion import DEFAULT_FUSION_ENGINE, SignalDirection
from app.strategy.signal_engine import SignalInsight


@dataclass(frozen=True)
class CalibratedAdaptiveResult:
    insight: SignalInsight
    base: AdaptiveSignalResult
    applied_multipliers: tuple[dict, ...]
    calibration_applied: bool


class CalibratedAdaptiveSignalEngine:
    """Research-only adaptive engine with learned, bounded alpha multipliers.

    The calibration snapshot can only change relative Alpha weights. It cannot
    enable research strategies, bypass risk, or reach broker/execution code.
    """

    def __init__(
        self,
        snapshot: CalibrationSnapshot,
        *,
        base_engine: AdaptiveSignalEngine | None = None,
        buy_score_threshold: float = 65.0,
        sell_score_threshold: float = 65.0,
    ) -> None:
        self.snapshot = snapshot
        self.base_engine = base_engine or AdaptiveSignalEngine(include_research=False)
        self.buy_score_threshold = float(buy_score_threshold)
        self.sell_score_threshold = float(sell_score_threshold)

    def _action(self, direction: SignalDirection, score: float) -> str:
        if direction is SignalDirection.LONG and score >= self.buy_score_threshold:
            return "BUY"
        if direction is SignalDirection.SHORT and score >= self.sell_score_threshold:
            return "SELL"
        return "HOLD"

    def analyze(
        self,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> CalibratedAdaptiveResult:
        base = self.base_engine.analyze(
            df,
            market_df=market_df,
            mtf_frames=mtf_frames,
        )
        base_insight = base.insight
        regime_name = base_insight.regime.value

        adjusted = []
        applied: list[dict] = []
        for alpha in base_insight.alphas:
            multiplier = self.snapshot.alpha_multiplier(alpha.name, regime_name)
            adjusted_alpha = ReliabilityCalibrator.apply(alpha, multiplier)
            adjusted.append(adjusted_alpha)
            applied.append(
                {
                    "name": alpha.name,
                    "regime": regime_name,
                    "base_weight": round(float(alpha.weight), 6),
                    "multiplier": round(float(multiplier), 6),
                    "calibrated_weight": round(float(adjusted_alpha.weight), 6),
                }
            )

        fused = DEFAULT_FUSION_ENGINE.fuse(
            adjusted,
            regime=base_insight.regime,
        )
        action = self._action(fused.direction, fused.score)
        changed_weights = tuple(
            item for item in applied if abs(float(item["multiplier"]) - 1.0) > 1e-9
        )

        reasons = tuple(base_insight.reasons)
        if changed_weights:
            reasons = reasons + tuple(
                f"Calibration {item['name']} x{item['multiplier']:.3f} in {regime_name}"
                for item in changed_weights
            )
        else:
            reasons = reasons + ("No eligible alpha calibration for current regime",)

        insight = SignalInsight(
            action=action,
            direction=fused.direction,
            score=fused.score,
            confidence=fused.confidence,
            quality=fused.quality,
            expected_pct=fused.expected_pct,
            horizon=fused.horizon,
            regime=fused.regime,
            regime_confidence=base_insight.regime_confidence,
            entry=base_insight.entry,
            alphas=tuple(adjusted),
            contributions=fused.contributions,
            reasons=reasons,
        )
        return CalibratedAdaptiveResult(
            insight=insight,
            base=base,
            applied_multipliers=tuple(applied),
            calibration_applied=bool(changed_weights),
        )
