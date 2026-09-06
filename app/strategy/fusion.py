from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from app.analysis.regime import MarketRegime


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

    @property
    def sign(self) -> int:
        if self is SignalDirection.LONG:
            return 1
        if self is SignalDirection.SHORT:
            return -1
        return 0


@dataclass(frozen=True)
class AlphaSignal:
    name: str
    direction: SignalDirection
    confidence: float
    quality: float = 1.0
    weight: float = 1.0
    magnitude_pct: float | None = None
    horizon: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError("quality must be between 0 and 1")
        if self.weight <= 0:
            raise ValueError("weight must be greater than zero")


@dataclass(frozen=True)
class FusionResult:
    direction: SignalDirection
    score: float
    confidence: float
    quality: float
    expected_pct: float | None
    horizon: str | None
    regime: MarketRegime
    direction_strength: float
    contributions: tuple[dict, ...]


class SignalFusionEngine:
    """Combine multiple independent Alpha signals into one decision context.

    The result is analysis only. This class has no broker/execution access.
    Risk and portfolio layers remain responsible for deciding whether an
    otherwise attractive fused signal may proceed toward execution.
    """

    def __init__(self, minimum_direction_strength: float = 0.15) -> None:
        self.minimum_direction_strength = max(0.0, min(1.0, minimum_direction_strength))

    @staticmethod
    def _regime_multiplier(regime: MarketRegime, direction: SignalDirection) -> float:
        if direction is SignalDirection.NEUTRAL:
            return 1.0

        if regime is MarketRegime.BULL:
            return 1.10 if direction is SignalDirection.LONG else 0.70
        if regime is MarketRegime.BEAR:
            return 0.65 if direction is SignalDirection.LONG else 1.10
        if regime is MarketRegime.RISK_OFF:
            return 0.35 if direction is SignalDirection.LONG else 1.15
        if regime is MarketRegime.HIGH_VOLATILITY:
            return 0.75
        return 1.0

    def fuse(
        self,
        signals: Iterable[AlphaSignal],
        regime: MarketRegime = MarketRegime.UNKNOWN,
    ) -> FusionResult:
        items = tuple(signals)
        if not items:
            return FusionResult(
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                confidence=0.0,
                quality=0.0,
                expected_pct=None,
                horizon=None,
                regime=regime,
                direction_strength=0.0,
                contributions=(),
            )

        signed_vote = 0.0
        total_effective_weight = 0.0
        confidence_weighted = 0.0
        quality_weighted = 0.0
        magnitude_weighted = 0.0
        magnitude_weight = 0.0
        horizons: list[str] = []
        contributions: list[dict] = []

        for signal in items:
            regime_multiplier = self._regime_multiplier(regime, signal.direction)
            effective_weight = signal.weight * regime_multiplier
            vote = (
                signal.direction.sign
                * signal.confidence
                * signal.quality
                * effective_weight
            )

            signed_vote += vote
            total_effective_weight += effective_weight
            confidence_weighted += signal.confidence * effective_weight
            quality_weighted += signal.quality * effective_weight

            if signal.magnitude_pct is not None and signal.direction is not SignalDirection.NEUTRAL:
                magnitude_weighted += abs(float(signal.magnitude_pct)) * effective_weight
                magnitude_weight += effective_weight

            if signal.horizon:
                horizons.append(signal.horizon)

            contributions.append(
                {
                    "name": signal.name,
                    "direction": signal.direction.value,
                    "confidence": round(signal.confidence * 100.0, 2),
                    "quality": round(signal.quality * 100.0, 2),
                    "weight": signal.weight,
                    "regime_multiplier": regime_multiplier,
                    "effective_vote": vote,
                    "reason": signal.reason,
                }
            )

        if total_effective_weight <= 0:
            direction_strength_signed = 0.0
            confidence = 0.0
            quality = 0.0
        else:
            direction_strength_signed = signed_vote / total_effective_weight
            confidence = confidence_weighted / total_effective_weight
            quality = quality_weighted / total_effective_weight

        absolute_strength = min(1.0, abs(direction_strength_signed))
        if absolute_strength < self.minimum_direction_strength:
            direction = SignalDirection.NEUTRAL
        elif direction_strength_signed > 0:
            direction = SignalDirection.LONG
        else:
            direction = SignalDirection.SHORT

        # Transparent composite: agreement/direction has the largest weight,
        # followed by model confidence and signal quality.
        score = 100.0 * (
            (0.50 * absolute_strength)
            + (0.30 * confidence)
            + (0.20 * quality)
        )

        expected_pct = (
            magnitude_weighted / magnitude_weight
            if magnitude_weight > 0
            else None
        )

        unique_horizons = tuple(dict.fromkeys(horizons))
        horizon = None
        if len(unique_horizons) == 1:
            horizon = unique_horizons[0]
        elif len(unique_horizons) > 1:
            horizon = "MIXED"

        return FusionResult(
            direction=direction,
            score=round(min(100.0, max(0.0, score)), 2),
            confidence=round(confidence * 100.0, 2),
            quality=round(quality * 100.0, 2),
            expected_pct=None if expected_pct is None else round(expected_pct, 2),
            horizon=horizon,
            regime=regime,
            direction_strength=round(direction_strength_signed, 4),
            contributions=tuple(contributions),
        )


DEFAULT_FUSION_ENGINE = SignalFusionEngine()
