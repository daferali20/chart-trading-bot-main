from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.research.calibration import (
    CalibrationSnapshot,
    DirectionalProbabilityCalibrator,
    ReliabilityCalibrator,
    build_snapshot,
)
from app.research.outcomes import ForwardOutcome
from app.strategy.fusion import AlphaSignal, SignalDirection


def outcome(*, correct: bool, signed: float, mfe: float = 2.0, mae: float = -1.0) -> ForwardOutcome:
    return ForwardOutcome(
        observed_at="2026-01-01T00:00:00+00:00",
        action="BUY",
        horizon_bars=3,
        anchor_date="2026-01-01T00:00:00+00:00",
        anchor_close=100.0,
        future_date="2026-01-04T00:00:00+00:00",
        future_close=101.0,
        realized_return_pct=signed,
        signed_return_pct=signed,
        correct_direction=correct,
        mfe_pct=mfe,
        mae_pct=mae,
    )


class CalibrationTests(unittest.TestCase):
    def test_small_sample_never_changes_weight(self) -> None:
        calibrator = ReliabilityCalibrator(minimum_samples=10, prior_samples=10)
        items = [outcome(correct=True, signed=2.0) for _ in range(9)]
        result = calibrator.estimate("MomentumAlpha|BULL", items)
        self.assertFalse(result.eligible)
        self.assertEqual(result.weight_multiplier, 1.0)

    def test_consistently_good_outcomes_raise_weight_conservatively(self) -> None:
        calibrator = ReliabilityCalibrator(minimum_samples=20, prior_samples=20)
        items = [outcome(correct=True, signed=1.5, mfe=2.5, mae=-0.7) for _ in range(18)]
        items += [outcome(correct=False, signed=-0.6, mfe=0.8, mae=-1.2) for _ in range(2)]
        result = calibrator.estimate("TrendAlpha|BULL", items)
        self.assertTrue(result.eligible)
        self.assertGreater(result.weight_multiplier, 1.0)
        self.assertLessEqual(result.weight_multiplier, 1.35)

    def test_bad_outcomes_reduce_weight_but_do_not_disable_model(self) -> None:
        calibrator = ReliabilityCalibrator(minimum_samples=20, prior_samples=20)
        items = [outcome(correct=False, signed=-1.2, mfe=0.5, mae=-1.8) for _ in range(16)]
        items += [outcome(correct=True, signed=0.7, mfe=1.1, mae=-0.5) for _ in range(4)]
        result = calibrator.estimate("BreakoutAlpha|SIDEWAYS", items)
        self.assertTrue(result.eligible)
        self.assertLess(result.weight_multiplier, 1.0)
        self.assertGreaterEqual(result.weight_multiplier, 0.65)

    def test_probability_calibration_corrects_overconfidence(self) -> None:
        calibrator = DirectionalProbabilityCalibrator(
            minimum_samples=20,
            prior_samples=10,
            maximum_offset=0.20,
        )
        samples = [(0.80, True)] * 10 + [(0.80, False)] * 10
        estimate = calibrator.estimate("EARNINGS", samples)
        self.assertTrue(estimate.eligible)
        self.assertLess(estimate.probability_offset, 0.0)
        self.assertLess(estimate.calibrate(0.80), 0.80)

    def test_apply_keeps_alpha_contract_valid(self) -> None:
        signal = AlphaSignal(
            name="MomentumAlpha",
            direction=SignalDirection.LONG,
            confidence=0.70,
            quality=0.80,
            weight=1.0,
        )
        adjusted = ReliabilityCalibrator.apply(signal, 1.20)
        self.assertAlmostEqual(adjusted.weight, 1.20)
        self.assertEqual(adjusted.direction, signal.direction)
        self.assertEqual(adjusted.confidence, signal.confidence)

    def test_snapshot_round_trip_only_contains_eligible_estimates(self) -> None:
        reliability = ReliabilityCalibrator(minimum_samples=2, prior_samples=0)
        alpha = reliability.estimate(
            "VolumeAlpha|BULL",
            [
                outcome(correct=True, signed=1.0),
                outcome(correct=True, signed=0.8),
            ],
        )
        event = DirectionalProbabilityCalibrator(
            minimum_samples=2,
            prior_samples=0,
        ).estimate("CONTRACT", [(0.70, True), (0.70, True)])
        snapshot = build_snapshot(
            horizon_bars=3,
            minimum_samples=2,
            alpha_estimates=(alpha,),
            event_estimates=(event,),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = snapshot.save(Path(tmp) / "calibration.json")
            loaded = CalibrationSnapshot.load(path)

        self.assertIn("VolumeAlpha|BULL", loaded.alpha_weights)
        self.assertIn("CONTRACT", loaded.event_probability_offsets)
        self.assertEqual(loaded.horizon_bars, 3)


if __name__ == "__main__":
    unittest.main()
