from __future__ import annotations

import unittest

from app.events.calibration import calibrate_impact_forecast
from app.events.models import EventType, ImpactForecast
from app.research.calibration import CalibrationSnapshot


class EventProbabilityCalibrationTests(unittest.TestCase):
    @staticmethod
    def forecast() -> ImpactForecast:
        return ImpactForecast(
            symbol="AAA",
            event_type=EventType.EARNINGS,
            direction="UP",
            probability_up=0.80,
            probability_down=0.10,
            probability_neutral=0.10,
            impact_score=70.0,
            expected_move_low_pct=3.0,
            expected_move_high_pct=8.0,
            horizon="1-5D",
            risk_level="HIGH",
            confidence=80.0,
            reasons=("test",),
        )

    def test_negative_offset_reduces_upside_probability_and_preserves_sum(self) -> None:
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={},
            event_probability_offsets={"EARNINGS": -0.15},
            engine_weights={},
        )
        result = calibrate_impact_forecast(self.forecast(), snapshot)

        self.assertAlmostEqual(result.probability_up, 0.65)
        self.assertAlmostEqual(
            result.probability_up + result.probability_down + result.probability_neutral,
            1.0,
            places=7,
        )
        self.assertEqual(result.direction, "UP")

    def test_missing_event_calibration_is_identity(self) -> None:
        forecast = self.forecast()
        snapshot = CalibrationSnapshot(
            generated_at="2026-01-01T00:00:00+00:00",
            horizon_bars=3,
            minimum_samples=30,
            alpha_weights={},
            event_probability_offsets={},
            engine_weights={},
        )
        result = calibrate_impact_forecast(forecast, snapshot)
        self.assertIs(result, forecast)


if __name__ == "__main__":
    unittest.main()
