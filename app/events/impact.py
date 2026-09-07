from __future__ import annotations

import math

from app.analysis.regime import MarketRegime
from app.events.models import EventType, ImpactForecast, NewsEvent


class EventImpactEngine:
    """Research-only probabilistic event-impact model.

    It predicts a directional probability and move range, not an exact future
    price. The engine intentionally consumes normalized sentiment/relevance
    inputs so a future FinBERT, LLM or external news service can be plugged in
    without changing downstream portfolio or risk code.
    """

    BASE_MOVE_PCT = {
        EventType.EARNINGS: 6.0,
        EventType.GUIDANCE: 6.5,
        EventType.M_AND_A: 9.0,
        EventType.FDA: 12.0,
        EventType.CONTRACT: 4.5,
        EventType.OFFERING: 7.0,
        EventType.REGULATORY: 7.0,
        EventType.ANALYST_RATING: 3.0,
        EventType.MACRO: 3.5,
        EventType.MANAGEMENT: 4.0,
        EventType.PRODUCT: 4.0,
        EventType.LEGAL: 6.0,
        EventType.OTHER: 2.5,
    }

    EVENT_RISK = {
        EventType.FDA: "VERY_HIGH",
        EventType.M_AND_A: "VERY_HIGH",
        EventType.EARNINGS: "HIGH",
        EventType.GUIDANCE: "HIGH",
        EventType.OFFERING: "HIGH",
        EventType.REGULATORY: "HIGH",
        EventType.LEGAL: "HIGH",
        EventType.MACRO: "MEDIUM",
        EventType.CONTRACT: "MEDIUM",
        EventType.MANAGEMENT: "MEDIUM",
        EventType.PRODUCT: "MEDIUM",
        EventType.ANALYST_RATING: "LOW",
        EventType.OTHER: "LOW",
    }

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    def forecast(
        self,
        event: NewsEvent,
        *,
        market_regime: MarketRegime = MarketRegime.UNKNOWN,
        momentum20: float | None = None,
        rvol: float | None = None,
        gap_pct: float | None = None,
    ) -> ImpactForecast:
        base_move = self.BASE_MOVE_PCT[event.event_type]
        info_quality = event.relevance * event.novelty

        signed_strength = event.sentiment * info_quality * 65.0
        reasons = [
            f"{event.event_type.value} event",
            f"sentiment={event.sentiment:+.2f}",
            f"relevance={event.relevance:.2f}",
            f"novelty={event.novelty:.2f}",
        ]

        if event.surprise_pct is not None:
            surprise_component = self._clip(event.surprise_pct / 20.0, -1.0, 1.0) * 22.0
            signed_strength += surprise_component
            reasons.append(f"surprise={event.surprise_pct:+.2f}%")

        if momentum20 is not None:
            momentum_component = self._clip(momentum20 / 20.0, -1.0, 1.0) * 8.0
            signed_strength += momentum_component
            reasons.append(f"momentum20={momentum20:+.2f}%")

        if rvol is not None and rvol >= 1.5:
            signed_strength *= min(1.20, 1.0 + ((rvol - 1.5) * 0.08))
            reasons.append(f"elevated RVOL={rvol:.2f}")

        if gap_pct is not None and abs(gap_pct) >= base_move:
            # Much of the information may already be in price.
            signed_strength *= 0.82
            reasons.append("large price gap suggests partial information absorption")

        if market_regime is MarketRegime.RISK_OFF and signed_strength > 0:
            signed_strength *= 0.65
            reasons.append("RISK_OFF suppresses positive-event follow-through")
        elif market_regime is MarketRegime.BULL and signed_strength > 0:
            signed_strength *= 1.08
        elif market_regime is MarketRegime.BEAR and signed_strength < 0:
            signed_strength *= 1.08

        signed_strength = self._clip(signed_strength, -100.0, 100.0)
        impact_score = abs(signed_strength)

        neutral_probability = self._clip(0.48 - (impact_score / 180.0), 0.10, 0.55)
        directional_mass = 1.0 - neutral_probability
        positive_share = 1.0 / (1.0 + math.exp(-signed_strength / 18.0))
        probability_up = directional_mass * positive_share
        probability_down = directional_mass * (1.0 - positive_share)

        if signed_strength >= 12.0:
            direction = "UP"
        elif signed_strength <= -12.0:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"

        magnitude_multiplier = 0.45 + (0.90 * info_quality) + (0.45 * abs(event.sentiment))
        if event.surprise_pct is not None:
            magnitude_multiplier += min(abs(event.surprise_pct) / 50.0, 0.75)
        if rvol is not None:
            magnitude_multiplier += min(max(rvol - 1.0, 0.0) * 0.10, 0.35)

        expected_mid = base_move * magnitude_multiplier
        low = max(0.5, expected_mid * 0.55)
        high = max(low, expected_mid * 1.45)

        if event.event_type in {EventType.EARNINGS, EventType.GUIDANCE, EventType.FDA, EventType.M_AND_A}:
            horizon = "1-5D"
        elif event.event_type in {EventType.CONTRACT, EventType.PRODUCT, EventType.ANALYST_RATING}:
            horizon = "1-10D"
        else:
            horizon = "1-7D"

        confidence = self._clip(
            35.0 + (35.0 * info_quality) + (20.0 * abs(event.sentiment)) + min(impact_score * 0.10, 10.0),
            0.0,
            95.0,
        )

        # Round probabilities together while preserving an exact unit sum.
        p_up = round(probability_up, 4)
        p_down = round(probability_down, 4)
        p_neutral = round(1.0 - p_up - p_down, 4)

        return ImpactForecast(
            symbol=event.symbol.upper(),
            event_type=event.event_type,
            direction=direction,
            probability_up=p_up,
            probability_down=p_down,
            probability_neutral=p_neutral,
            impact_score=round(impact_score, 2),
            expected_move_low_pct=round(low, 2),
            expected_move_high_pct=round(high, 2),
            horizon=horizon,
            risk_level=self.EVENT_RISK[event.event_type],
            confidence=round(confidence, 2),
            reasons=tuple(reasons),
        )


DEFAULT_EVENT_IMPACT_ENGINE = EventImpactEngine()
