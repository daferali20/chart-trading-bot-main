from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from collections.abc import Iterable

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.strategy.base import AlphaModel
from app.strategy.fusion import SignalDirection


@dataclass(frozen=True)
class AlphaForwardObservation:
    model: str
    direction: str
    signal_date: str
    entry_date: str
    horizon_bars: int
    entry_price: float
    exit_price: float
    raw_return_pct: float
    signed_return_pct: float
    correct_direction: bool
    mfe_pct: float
    mae_pct: float


@dataclass(frozen=True)
class AlphaForwardSummary:
    model: str
    horizon_bars: int
    samples: int
    long_samples: int
    short_samples: int
    hit_rate: float
    average_signed_return_pct: float
    median_signed_return_pct: float
    average_mfe_pct: float
    average_mae_pct: float


@dataclass(frozen=True)
class AlphaForwardValidationResult:
    observations: tuple[AlphaForwardObservation, ...]
    summaries: tuple[AlphaForwardSummary, ...]
    raw_directional_signals: int
    independent_signal_episodes: int


class AlphaForwardValidator:
    """Measure an AlphaModel's forward directional edge without exit-rule bias.

    A signal is generated on a completed bar and is assumed executable only at
    the NEXT bar open. Returns are then measured to the close at 1/3/5/... bars
    after the signal. Consecutive same-direction signals are one episode by
    default so persistent conditions do not artificially inflate sample size.
    """

    def __init__(
        self,
        horizons: Iterable[int] = (1, 3, 5, 10),
        *,
        deduplicate_episodes: bool = True,
    ) -> None:
        cleaned = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
        if not cleaned:
            raise ValueError("At least one positive forward horizon is required")
        self.horizons = cleaned
        self.deduplicate_episodes = bool(deduplicate_episodes)

    @staticmethod
    def _date(row: pd.Series) -> str:
        value = row.get("date", row.get("timestamp", ""))
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _summary(
        model: str,
        horizon: int,
        observations: list[AlphaForwardObservation],
    ) -> AlphaForwardSummary:
        if not observations:
            return AlphaForwardSummary(
                model=model,
                horizon_bars=horizon,
                samples=0,
                long_samples=0,
                short_samples=0,
                hit_rate=0.0,
                average_signed_return_pct=0.0,
                median_signed_return_pct=0.0,
                average_mfe_pct=0.0,
                average_mae_pct=0.0,
            )
        count = len(observations)
        signed = [item.signed_return_pct for item in observations]
        return AlphaForwardSummary(
            model=model,
            horizon_bars=horizon,
            samples=count,
            long_samples=sum(item.direction == "LONG" for item in observations),
            short_samples=sum(item.direction == "SHORT" for item in observations),
            hit_rate=sum(item.correct_direction for item in observations) / count,
            average_signed_return_pct=sum(signed) / count,
            median_signed_return_pct=median(signed),
            average_mfe_pct=sum(item.mfe_pct for item in observations) / count,
            average_mae_pct=sum(item.mae_pct for item in observations) / count,
        )

    def validate(
        self,
        model: AlphaModel,
        data: pd.DataFrame,
    ) -> AlphaForwardValidationResult:
        if data is None or data.empty:
            raise ValueError("Validation data is empty")

        features = DEFAULT_FEATURE_ENGINE.build(data)
        observations: list[AlphaForwardObservation] = []
        raw_directional = 0
        independent = 0
        active_episode_direction: SignalDirection | None = None

        for index in range(len(features)):
            prefix = features.iloc[: index + 1]
            signal = model.generate_alpha(prefix)
            direction = signal.direction
            directional = direction in {SignalDirection.LONG, SignalDirection.SHORT}

            if not directional:
                active_episode_direction = None
                continue

            raw_directional += 1
            if (
                self.deduplicate_episodes
                and active_episode_direction is direction
            ):
                continue

            active_episode_direction = direction
            independent += 1
            entry_index = index + 1
            if entry_index >= len(features):
                continue

            entry = float(features.iloc[entry_index]["open"])
            if entry <= 0:
                continue

            for horizon in self.horizons:
                exit_index = index + horizon
                if exit_index >= len(features) or exit_index < entry_index:
                    continue

                exit_price = float(features.iloc[exit_index]["close"])
                raw_return = ((exit_price / entry) - 1.0) * 100.0
                signed_return = (
                    raw_return
                    if direction is SignalDirection.LONG
                    else -raw_return
                )

                window = features.iloc[entry_index : exit_index + 1]
                if direction is SignalDirection.LONG:
                    mfe = ((float(window["high"].max()) - entry) / entry) * 100.0
                    mae = ((float(window["low"].min()) - entry) / entry) * 100.0
                else:
                    # Express excursions in symmetric percentage-of-entry terms.
                    # Favorable for a short is price falling below entry; adverse
                    # is price rising above it.
                    mfe = ((entry - float(window["low"].min())) / entry) * 100.0
                    mae = -((float(window["high"].max()) - entry) / entry) * 100.0

                observations.append(
                    AlphaForwardObservation(
                        model=model.name,
                        direction=direction.value,
                        signal_date=self._date(features.iloc[index]),
                        entry_date=self._date(features.iloc[entry_index]),
                        horizon_bars=horizon,
                        entry_price=entry,
                        exit_price=exit_price,
                        raw_return_pct=raw_return,
                        signed_return_pct=signed_return,
                        correct_direction=signed_return > 0.0,
                        mfe_pct=mfe,
                        mae_pct=mae,
                    )
                )

        summaries = tuple(
            self._summary(
                model.name,
                horizon,
                [item for item in observations if item.horizon_bars == horizon],
            )
            for horizon in self.horizons
        )
        return AlphaForwardValidationResult(
            observations=tuple(observations),
            summaries=summaries,
            raw_directional_signals=raw_directional,
            independent_signal_episodes=independent,
        )


DEFAULT_ALPHA_FORWARD_VALIDATOR = AlphaForwardValidator()
