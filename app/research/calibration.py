from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from collections.abc import Iterable, Sequence

from app.research.outcomes import ForwardOutcome
from app.strategy.fusion import AlphaSignal


@dataclass(frozen=True)
class ReliabilityEstimate:
    key: str
    samples: int
    hit_rate: float
    posterior_hit_rate: float
    average_signed_return_pct: float
    average_mfe_pct: float
    average_mae_pct: float
    weight_multiplier: float
    eligible: bool
    reason: str


@dataclass(frozen=True)
class ProbabilityCalibrationEstimate:
    key: str
    samples: int
    mean_predicted_probability: float
    empirical_hit_rate: float
    posterior_hit_rate: float
    probability_offset: float
    eligible: bool
    reason: str

    def calibrate(self, raw_probability: float) -> float:
        raw = max(0.01, min(0.99, float(raw_probability)))
        if not self.eligible:
            return raw
        return max(0.05, min(0.95, raw + self.probability_offset))


@dataclass(frozen=True)
class CalibrationSnapshot:
    generated_at: str
    horizon_bars: int
    minimum_samples: int
    alpha_weights: dict[str, float]
    event_probability_offsets: dict[str, float]
    engine_weights: dict[str, float]
    training_end_at: str | None = None
    valid_until: str | None = None
    source_symbol: str = ""

    @staticmethod
    def _utc(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def to_dict(self) -> dict:
        return asdict(self)

    def alpha_multiplier(self, alpha_name: str, regime: str) -> float:
        return float(
            self.alpha_weights.get(
                f"{str(alpha_name)}|{str(regime).upper()}",
                1.0,
            )
        )

    def event_probability_offset(self, event_type: str) -> float:
        return float(self.event_probability_offsets.get(str(event_type).upper(), 0.0))

    def engine_multiplier(self, engine_name: str) -> float:
        return float(self.engine_weights.get(str(engine_name), 1.0))

    def calibrate_event_probability(self, event_type: str, raw_probability: float) -> float:
        raw = max(0.01, min(0.99, float(raw_probability)))
        return max(
            0.05,
            min(0.95, raw + self.event_probability_offset(event_type)),
        )

    def is_causal_for(self, observed_at: str | datetime) -> bool:
        """True only when the decision occurs strictly after calibration training data."""
        observed = self._utc(observed_at)
        boundary_text = self.training_end_at or self.generated_at
        try:
            boundary = self._utc(boundary_text)
        except (TypeError, ValueError):
            return False
        return observed > boundary

    def is_fresh(
        self,
        *,
        now: str | datetime | None = None,
        fallback_max_age_days: int = 30,
    ) -> bool:
        """Reject expired, future-dated, or excessively old research state."""
        current = self._utc(now or datetime.now(timezone.utc))
        try:
            generated = self._utc(self.generated_at)
        except (TypeError, ValueError):
            return False
        if generated > current + timedelta(minutes=5):
            return False

        if self.valid_until:
            try:
                return current <= self._utc(self.valid_until)
            except (TypeError, ValueError):
                return False

        age_limit = timedelta(days=max(1, int(fallback_max_age_days)))
        return (current - generated) <= age_limit

    def usable_for(
        self,
        observed_at: str | datetime,
        *,
        fallback_max_age_days: int = 30,
    ) -> bool:
        return self.is_fresh(
            now=observed_at,
            fallback_max_age_days=fallback_max_age_days,
        ) and self.is_causal_for(observed_at)

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationSnapshot":
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls(
            generated_at=str(payload["generated_at"]),
            horizon_bars=int(payload["horizon_bars"]),
            minimum_samples=int(payload["minimum_samples"]),
            alpha_weights={
                str(key): float(value)
                for key, value in dict(payload.get("alpha_weights", {})).items()
            },
            event_probability_offsets={
                str(key): float(value)
                for key, value in dict(payload.get("event_probability_offsets", {})).items()
            },
            engine_weights={
                str(key): float(value)
                for key, value in dict(payload.get("engine_weights", {})).items()
            },
            training_end_at=(
                None
                if payload.get("training_end_at") in {None, ""}
                else str(payload["training_end_at"])
            ),
            valid_until=(
                None
                if payload.get("valid_until") in {None, ""}
                else str(payload["valid_until"])
            ),
            source_symbol=str(payload.get("source_symbol") or ""),
        )


class ReliabilityCalibrator:
    """Conservative reliability-to-weight calibration for research signals.

    The calibrator deliberately shrinks observed hit rates toward 50% and
    refuses to alter weights until ``minimum_samples`` matured outcomes exist.
    Multipliers are bounded so one lucky period cannot dominate Signal Fusion.
    """

    def __init__(
        self,
        *,
        minimum_samples: int = 30,
        prior_samples: int = 20,
        target_signed_return_pct: float = 1.0,
        minimum_weight: float = 0.65,
        maximum_weight: float = 1.35,
    ) -> None:
        self.minimum_samples = max(1, int(minimum_samples))
        self.prior_samples = max(0, int(prior_samples))
        self.target_signed_return_pct = max(0.10, abs(float(target_signed_return_pct)))
        self.minimum_weight = max(0.05, float(minimum_weight))
        self.maximum_weight = max(self.minimum_weight, float(maximum_weight))

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    def estimate(
        self,
        key: str,
        outcomes: Iterable[ForwardOutcome],
    ) -> ReliabilityEstimate:
        items = tuple(outcomes)
        samples = len(items)
        if samples == 0:
            return ReliabilityEstimate(
                key=str(key),
                samples=0,
                hit_rate=0.0,
                posterior_hit_rate=0.5,
                average_signed_return_pct=0.0,
                average_mfe_pct=0.0,
                average_mae_pct=0.0,
                weight_multiplier=1.0,
                eligible=False,
                reason="No matured outcomes",
            )

        hits = sum(bool(item.correct_direction) for item in items)
        hit_rate = hits / samples
        prior_hits = 0.5 * self.prior_samples
        posterior_hit = (hits + prior_hits) / (samples + self.prior_samples)
        average_signed = sum(item.signed_return_pct for item in items) / samples
        average_mfe = sum(item.mfe_pct for item in items) / samples
        average_mae = sum(item.mae_pct for item in items) / samples

        eligible = samples >= self.minimum_samples
        if not eligible:
            return ReliabilityEstimate(
                key=str(key),
                samples=samples,
                hit_rate=round(hit_rate, 4),
                posterior_hit_rate=round(posterior_hit, 4),
                average_signed_return_pct=round(average_signed, 4),
                average_mfe_pct=round(average_mfe, 4),
                average_mae_pct=round(average_mae, 4),
                weight_multiplier=1.0,
                eligible=False,
                reason=f"Need {self.minimum_samples - samples} more matured outcomes",
            )

        hit_edge = self._clip((posterior_hit - 0.50) / 0.15, -1.0, 1.0)
        return_edge = self._clip(
            average_signed / self.target_signed_return_pct,
            -1.0,
            1.0,
        )
        adverse = max(abs(min(average_mae, 0.0)), 0.25)
        payoff_edge = self._clip(average_signed / adverse, -1.0, 1.0)

        composite = (
            (0.55 * hit_edge)
            + (0.30 * return_edge)
            + (0.15 * payoff_edge)
        )
        multiplier = self._clip(
            1.0 + (0.35 * composite),
            self.minimum_weight,
            self.maximum_weight,
        )

        return ReliabilityEstimate(
            key=str(key),
            samples=samples,
            hit_rate=round(hit_rate, 4),
            posterior_hit_rate=round(posterior_hit, 4),
            average_signed_return_pct=round(average_signed, 4),
            average_mfe_pct=round(average_mfe, 4),
            average_mae_pct=round(average_mae, 4),
            weight_multiplier=round(multiplier, 4),
            eligible=True,
            reason="Calibrated from matured shadow outcomes",
        )

    @staticmethod
    def apply(signal: AlphaSignal, multiplier: float) -> AlphaSignal:
        adjusted = max(0.05, float(signal.weight) * max(0.05, float(multiplier)))
        return replace(signal, weight=adjusted)


class DirectionalProbabilityCalibrator:
    """Calibrate event directional probabilities by event type.

    Each sample is ``(predicted_direction_probability, was_direction_correct)``.
    The observed accuracy is shrunk toward a neutral 50% prior. Until enough
    samples mature, the probability offset remains exactly zero.
    """

    def __init__(
        self,
        *,
        minimum_samples: int = 30,
        prior_samples: int = 20,
        maximum_offset: float = 0.20,
    ) -> None:
        self.minimum_samples = max(1, int(minimum_samples))
        self.prior_samples = max(0, int(prior_samples))
        self.maximum_offset = max(0.0, min(0.40, abs(float(maximum_offset))))

    def estimate(
        self,
        key: str,
        samples: Sequence[tuple[float, bool]],
    ) -> ProbabilityCalibrationEstimate:
        items = tuple(samples)
        count = len(items)
        if count == 0:
            return ProbabilityCalibrationEstimate(
                key=str(key),
                samples=0,
                mean_predicted_probability=0.0,
                empirical_hit_rate=0.0,
                posterior_hit_rate=0.5,
                probability_offset=0.0,
                eligible=False,
                reason="No matured event outcomes",
            )

        predicted = [max(0.01, min(0.99, float(item[0]))) for item in items]
        hits = sum(bool(item[1]) for item in items)
        mean_predicted = sum(predicted) / count
        empirical = hits / count
        posterior = (hits + (0.5 * self.prior_samples)) / (
            count + self.prior_samples
        )

        eligible = count >= self.minimum_samples
        if not eligible:
            return ProbabilityCalibrationEstimate(
                key=str(key),
                samples=count,
                mean_predicted_probability=round(mean_predicted, 4),
                empirical_hit_rate=round(empirical, 4),
                posterior_hit_rate=round(posterior, 4),
                probability_offset=0.0,
                eligible=False,
                reason=f"Need {self.minimum_samples - count} more matured event outcomes",
            )

        raw_offset = posterior - mean_predicted
        offset = max(-self.maximum_offset, min(self.maximum_offset, raw_offset))
        return ProbabilityCalibrationEstimate(
            key=str(key),
            samples=count,
            mean_predicted_probability=round(mean_predicted, 4),
            empirical_hit_rate=round(empirical, 4),
            posterior_hit_rate=round(posterior, 4),
            probability_offset=round(offset, 4),
            eligible=True,
            reason="Calibrated from matured event outcomes",
        )


def build_snapshot(
    *,
    horizon_bars: int,
    minimum_samples: int,
    alpha_estimates: Iterable[ReliabilityEstimate] = (),
    event_estimates: Iterable[ProbabilityCalibrationEstimate] = (),
    engine_estimates: Iterable[ReliabilityEstimate] = (),
    training_end_at: str | None = None,
    source_symbol: str = "",
    validity_days: int = 30,
    generated_at: str | None = None,
) -> CalibrationSnapshot:
    generated = (
        datetime.now(timezone.utc)
        if generated_at is None
        else CalibrationSnapshot._utc(generated_at)
    )
    valid_until = generated + timedelta(days=max(1, int(validity_days)))
    return CalibrationSnapshot(
        generated_at=generated.isoformat(),
        horizon_bars=int(horizon_bars),
        minimum_samples=int(minimum_samples),
        alpha_weights={
            item.key: item.weight_multiplier
            for item in alpha_estimates
            if item.eligible
        },
        event_probability_offsets={
            item.key: item.probability_offset
            for item in event_estimates
            if item.eligible
        },
        engine_weights={
            item.key: item.weight_multiplier
            for item in engine_estimates
            if item.eligible
        },
        training_end_at=training_end_at,
        valid_until=valid_until.isoformat(),
        source_symbol=str(source_symbol).upper(),
    )


DEFAULT_RELIABILITY_CALIBRATOR = ReliabilityCalibrator()
DEFAULT_EVENT_PROBABILITY_CALIBRATOR = DirectionalProbabilityCalibrator()
