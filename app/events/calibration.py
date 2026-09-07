from __future__ import annotations

from dataclasses import replace

from app.events.models import ImpactForecast
from app.research.calibration import CalibrationSnapshot


def _redistribute_remaining(
    remaining: float,
    first: float,
    second: float,
) -> tuple[float, float]:
    total = max(0.0, float(first)) + max(0.0, float(second))
    if total <= 1e-12:
        return remaining / 2.0, remaining / 2.0
    return (
        remaining * max(0.0, float(first)) / total,
        remaining * max(0.0, float(second)) / total,
    )


def calibrate_impact_forecast(
    forecast: ImpactForecast,
    snapshot: CalibrationSnapshot,
) -> ImpactForecast:
    """Apply event-type probability calibration without changing event meaning.

    Calibration can weaken or strengthen the forecast direction, but it never
    flips an UP event directly into DOWN (or vice versa). If calibration makes
    the original direction no longer dominant, the result becomes NEUTRAL.
    """

    event_key = forecast.event_type.value
    offset = snapshot.event_probability_offset(event_key)
    if abs(offset) <= 1e-12 or forecast.direction not in {"UP", "DOWN"}:
        return forecast

    if forecast.direction == "UP":
        new_up = snapshot.calibrate_event_probability(
            event_key,
            forecast.probability_up,
        )
        remaining = 1.0 - new_up
        new_down, new_neutral = _redistribute_remaining(
            remaining,
            forecast.probability_down,
            forecast.probability_neutral,
        )
        original_probability = forecast.probability_up
        calibrated_probability = new_up
        direction = "UP" if new_up >= max(new_down, new_neutral) else "NEUTRAL"
    else:
        new_down = snapshot.calibrate_event_probability(
            event_key,
            forecast.probability_down,
        )
        remaining = 1.0 - new_down
        new_up, new_neutral = _redistribute_remaining(
            remaining,
            forecast.probability_up,
            forecast.probability_neutral,
        )
        original_probability = forecast.probability_down
        calibrated_probability = new_down
        direction = "DOWN" if new_down >= max(new_up, new_neutral) else "NEUTRAL"

    reasons = tuple(forecast.reasons) + (
        f"historical {event_key} probability calibration "
        f"{original_probability:.3f}->{calibrated_probability:.3f}",
    )
    return replace(
        forecast,
        direction=direction,
        probability_up=float(new_up),
        probability_down=float(new_down),
        probability_neutral=float(new_neutral),
        reasons=reasons,
    )
