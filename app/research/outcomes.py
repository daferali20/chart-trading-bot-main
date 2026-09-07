from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from collections.abc import Iterable, Sequence

import pandas as pd

from app.data.normalizer import DEFAULT_DATA_NORMALIZER


@dataclass(frozen=True)
class ForwardOutcome:
    observed_at: str
    action: str
    horizon_bars: int
    anchor_date: str
    anchor_close: float
    future_date: str
    future_close: float
    realized_return_pct: float
    signed_return_pct: float
    correct_direction: bool
    mfe_pct: float
    mae_pct: float


@dataclass(frozen=True)
class OutcomeSummary:
    samples: int
    hit_rate: float
    average_signed_return_pct: float
    median_signed_return_pct: float
    average_mfe_pct: float
    average_mae_pct: float


class ForwardOutcomeEvaluator:
    """Evaluate logged shadow actions after future bars become available.

    The evaluator is deliberately generic: it can score Legacy, Signal v2,
    regime-adaptive, or news-aware decisions using the same forward-return
    definition. It never places trades and does not require broker access.
    """

    def __init__(
        self,
        *,
        horizons: Sequence[int] = (1, 3, 5),
        neutral_band_pct: float = 0.50,
    ) -> None:
        cleaned = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
        if not cleaned:
            raise ValueError("At least one positive horizon is required")
        self.horizons = cleaned
        self.neutral_band_pct = abs(float(neutral_band_pct))

    @staticmethod
    def _as_utc_timestamp(value: str | datetime | pd.Timestamp) -> pd.Timestamp:
        return pd.to_datetime(value, utc=True)

    def evaluate(
        self,
        *,
        observed_at: str | datetime | pd.Timestamp,
        action: str,
        bars: pd.DataFrame,
    ) -> tuple[ForwardOutcome, ...]:
        data = DEFAULT_DATA_NORMALIZER.normalize(
            bars,
            require_open=False,
            require_volume=False,
            preserve_extra=True,
        )
        if data.empty:
            return ()

        dates = pd.to_datetime(data["date"], utc=True)
        observed = self._as_utc_timestamp(observed_at)
        eligible = data.index[dates <= observed].tolist()
        if not eligible:
            return ()

        anchor_index = int(eligible[-1])
        anchor_close = float(data.loc[anchor_index, "close"])
        if anchor_close <= 0:
            return ()

        action_upper = str(action).upper()
        if action_upper == "BUY":
            sign = 1.0
        elif action_upper == "SELL":
            sign = -1.0
        else:
            sign = 0.0

        outcomes: list[ForwardOutcome] = []
        for horizon in self.horizons:
            future_index = anchor_index + horizon
            if future_index >= len(data):
                continue

            future_close = float(data.loc[future_index, "close"])
            realized = ((future_close / anchor_close) - 1.0) * 100.0
            window = data.iloc[anchor_index + 1 : future_index + 1]
            if window.empty:
                continue

            max_high = float(window["high"].max())
            min_low = float(window["low"].min())
            raw_up = ((max_high / anchor_close) - 1.0) * 100.0
            raw_down = ((min_low / anchor_close) - 1.0) * 100.0

            if action_upper == "BUY":
                mfe = raw_up
                mae = raw_down
                correct = realized > self.neutral_band_pct
            elif action_upper == "SELL":
                mfe = -raw_down
                mae = -raw_up
                correct = realized < -self.neutral_band_pct
            else:
                mfe = max(abs(raw_up), abs(raw_down))
                mae = 0.0
                correct = abs(realized) <= self.neutral_band_pct

            outcomes.append(
                ForwardOutcome(
                    observed_at=observed.isoformat(),
                    action=action_upper,
                    horizon_bars=horizon,
                    anchor_date=dates.iloc[anchor_index].isoformat(),
                    anchor_close=round(anchor_close, 6),
                    future_date=dates.iloc[future_index].isoformat(),
                    future_close=round(future_close, 6),
                    realized_return_pct=round(realized, 4),
                    signed_return_pct=round(realized * sign, 4),
                    correct_direction=bool(correct),
                    mfe_pct=round(mfe, 4),
                    mae_pct=round(mae, 4),
                )
            )

        return tuple(outcomes)

    @staticmethod
    def summarize(outcomes: Iterable[ForwardOutcome]) -> OutcomeSummary:
        items = tuple(outcomes)
        if not items:
            return OutcomeSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0)

        signed = [item.signed_return_pct for item in items]
        return OutcomeSummary(
            samples=len(items),
            hit_rate=round(
                sum(item.correct_direction for item in items) / len(items),
                4,
            ),
            average_signed_return_pct=round(sum(signed) / len(signed), 4),
            median_signed_return_pct=round(float(median(signed)), 4),
            average_mfe_pct=round(sum(item.mfe_pct for item in items) / len(items), 4),
            average_mae_pct=round(sum(item.mae_pct for item in items) / len(items), 4),
        )


DEFAULT_FORWARD_OUTCOME_EVALUATOR = ForwardOutcomeEvaluator()
