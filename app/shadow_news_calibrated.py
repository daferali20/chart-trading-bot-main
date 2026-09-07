from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Mapping, Sequence

import pandas as pd

from app.events.calibration import calibrate_impact_forecast
from app.events.models import ImpactForecast
from app.research.calibration import CalibrationSnapshot
from app.shadow_news import NewsShadowEvaluator
from app.strategy.signal_engine import SignalInsight


@dataclass(frozen=True)
class CalibratedNewsShadowComparison:
    symbol: str
    observed_at: str
    market_regime: str
    event_type: str | None
    raw_event_direction: str | None
    calibrated_event_direction: str | None
    raw_direction_probability: float | None
    calibrated_direction_probability: float | None
    raw_combined_action: str
    raw_combined_score: float
    calibrated_combined_action: str
    calibrated_combined_score: float
    score_delta: float
    decision_changed: bool
    probability_calibration_applied: bool

    def to_dict(self) -> dict:
        return asdict(self)


class CalibratedNewsShadowEvaluator:
    """Compare raw news-aware fusion with probability-calibrated news fusion."""

    def __init__(
        self,
        snapshot: CalibrationSnapshot,
        *,
        news_evaluator: NewsShadowEvaluator | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.news_evaluator = news_evaluator or NewsShadowEvaluator()

    @staticmethod
    def _direction_probability(forecast: ImpactForecast | None) -> float | None:
        if forecast is None:
            return None
        if forecast.direction == "UP":
            return float(forecast.probability_up)
        if forecast.direction == "DOWN":
            return float(forecast.probability_down)
        return float(forecast.probability_neutral)

    @staticmethod
    def _strongest(forecasts: Sequence[ImpactForecast]) -> ImpactForecast | None:
        if not forecasts:
            return None
        return max(
            forecasts,
            key=lambda item: float(item.impact_score) * float(item.confidence),
        )

    def compare(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        forecasts: Sequence[ImpactForecast] = (),
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
        technical: SignalInsight | None = None,
    ) -> CalibratedNewsShadowComparison:
        raw_forecasts = tuple(forecasts)
        calibrated_forecasts = tuple(
            calibrate_impact_forecast(item, self.snapshot)
            for item in raw_forecasts
        )

        raw = self.news_evaluator.compare(
            symbol,
            df,
            forecasts=raw_forecasts,
            market_df=market_df,
            mtf_frames=mtf_frames,
            technical=technical,
        )
        calibrated = self.news_evaluator.compare(
            symbol,
            df,
            forecasts=calibrated_forecasts,
            market_df=market_df,
            mtf_frames=mtf_frames,
            technical=technical,
        )

        raw_strongest = self._strongest(raw_forecasts)
        calibrated_strongest = self._strongest(calibrated_forecasts)
        event_type = raw.event_type
        applied = bool(
            event_type
            and abs(self.snapshot.event_probability_offset(event_type)) > 1e-12
        )

        return CalibratedNewsShadowComparison(
            symbol=symbol.upper(),
            observed_at=datetime.now(timezone.utc).isoformat(),
            market_regime=raw.market_regime,
            event_type=event_type,
            raw_event_direction=(None if raw_strongest is None else raw_strongest.direction),
            calibrated_event_direction=(
                None if calibrated_strongest is None else calibrated_strongest.direction
            ),
            raw_direction_probability=self._direction_probability(raw_strongest),
            calibrated_direction_probability=self._direction_probability(calibrated_strongest),
            raw_combined_action=raw.combined_action,
            raw_combined_score=float(raw.combined_score),
            calibrated_combined_action=calibrated.combined_action,
            calibrated_combined_score=float(calibrated.combined_score),
            score_delta=round(
                float(calibrated.combined_score) - float(raw.combined_score),
                2,
            ),
            decision_changed=calibrated.combined_action != raw.combined_action,
            probability_calibration_applied=applied,
        )

    @staticmethod
    def append_log(
        comparison: CalibratedNewsShadowComparison,
        path: str | Path = "logs/calibrated_news_shadow_decisions.jsonl",
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
