from __future__ import annotations

import unittest

from app.research.scoring.temporal_stability import (
    AlphaTemporalStabilityEvaluator,
    TimeBucketAlphaEvidence,
)


def item(period: str, symbol: str, ret: float, hit: float = 0.55, samples: int = 5):
    return TimeBucketAlphaEvidence(
        symbol=symbol,
        period=period,
        model="TestAlpha",
        horizon_bars=5,
        samples=samples,
        average_signed_return_pct=ret,
        hit_rate=hit,
    )


class AlphaTemporalStabilityTests(unittest.TestCase):
    def test_edge_persistent_across_periods_passes(self) -> None:
        evaluator = AlphaTemporalStabilityEvaluator(
            minimum_periods=4,
            minimum_symbols_per_period=4,
            minimum_samples_per_symbol_period=3,
            minimum_positive_period_ratio=0.75,
        )
        evidence = []
        for period in ("P1", "P2", "P3", "P4"):
            evidence.extend(
                [
                    item(period, "AAA", 0.4),
                    item(period, "BBB", 0.2),
                    item(period, "CCC", 0.1),
                    item(period, "DDD", -0.05),
                ]
            )
        result = evaluator.evaluate(evidence)
        self.assertTrue(result.eligible)
        self.assertEqual(result.positive_periods, 4)
        self.assertEqual(result.periods_with_min_symbols, 4)

    def test_one_lucky_period_does_not_pass(self) -> None:
        evaluator = AlphaTemporalStabilityEvaluator(
            minimum_periods=4,
            minimum_symbols_per_period=4,
            minimum_samples_per_symbol_period=3,
            minimum_positive_period_ratio=0.75,
        )
        evidence = []
        for period, ret, hit in (
            ("P1", 1.2, 0.70),
            ("P2", -0.2, 0.45),
            ("P3", -0.1, 0.48),
            ("P4", -0.3, 0.44),
        ):
            for symbol in ("AAA", "BBB", "CCC", "DDD"):
                evidence.append(item(period, symbol, ret, hit=hit))
        result = evaluator.evaluate(evidence)
        self.assertFalse(result.eligible)
        self.assertLess(result.positive_period_ratio, 0.75)

    def test_period_with_too_few_symbol_samples_is_not_qualified(self) -> None:
        evaluator = AlphaTemporalStabilityEvaluator(
            minimum_periods=2,
            minimum_symbols_per_period=3,
            minimum_samples_per_symbol_period=3,
        )
        evidence = [
            item("P1", "AAA", 0.2),
            item("P1", "BBB", 0.2),
            item("P1", "CCC", 0.2),
            item("P2", "AAA", 0.2, samples=1),
            item("P2", "BBB", 0.2, samples=1),
            item("P2", "CCC", 0.2, samples=1),
        ]
        result = evaluator.evaluate(evidence)
        self.assertFalse(result.eligible)
        self.assertEqual(result.periods_with_min_symbols, 1)


if __name__ == "__main__":
    unittest.main()
