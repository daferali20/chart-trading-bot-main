from __future__ import annotations

from app.events.models import ImpactForecast
from app.strategy.fusion import AlphaSignal, SignalDirection


class EventAlphaAdapter:
    """Convert an event forecast into an optional Fusion-compatible alpha.

    This adapter is not wired into DEFAULT_SIGNAL_ENGINE. Research must prove
    incremental out-of-sample value before activation.
    """

    name = "EventImpactAlpha"

    def to_alpha(self, forecast: ImpactForecast) -> AlphaSignal:
        if forecast.direction == "UP":
            direction = SignalDirection.LONG
            directional_probability = forecast.probability_up
        elif forecast.direction == "DOWN":
            direction = SignalDirection.SHORT
            directional_probability = forecast.probability_down
        else:
            direction = SignalDirection.NEUTRAL
            directional_probability = forecast.probability_neutral

        confidence = max(0.0, min(0.95, directional_probability))
        quality = max(0.45, min(0.95, forecast.confidence / 100.0))
        weight = 0.6 if forecast.risk_level in {"HIGH", "VERY_HIGH"} else 0.8

        return AlphaSignal(
            name=self.name,
            direction=direction,
            confidence=confidence,
            quality=quality,
            weight=weight,
            magnitude_pct=(forecast.expected_move_low_pct + forecast.expected_move_high_pct) / 2.0,
            horizon=forecast.horizon,
            reason=(
                f"{forecast.event_type.value} forecast {forecast.direction}; "
                f"impact={forecast.impact_score:.1f}; confidence={forecast.confidence:.1f}%"
            ),
        )
