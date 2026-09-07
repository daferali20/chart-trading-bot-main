from __future__ import annotations

import unittest

from app.research.scoring.alpha_breadth import (
    AlphaBreadthEvaluator,
    SymbolAlphaEvidence,
)
from app.research.validation.alpha_forward import AlphaForwardSummary


def summary(symbol_model: str, *, samples: int, avg: float, hit: float) -> AlphaForwardSummary:
    return AlphaForwardSummary(
        model=symbol_model,
        horizon_bars=5,
        samples=samples,
        long_samples=samples,
        short_samples=0,
        hit_rate=hit,
        average_signed_return_pct=avg,
        median_signed_return_pct=avg,
        average_mfe_pct=max(avg, 0.0) + 1.0,
        average_mae_pct=min(avg, 0.0) - 1.0,
    )


class AlphaBreadthTests(unittest.TestCase):
    def test_one_exceptional_symbol_cannot_pass_breadth_gate(self) -> None:
        evaluator = AlphaBreadthEvaluator(
            minimum_symbols=4,
            minimum_samples_per_symbol=10,
            minimum_positive_breadth=0.60,
        )
        evidence = (
            SymbolAlphaEvidence("NVDA", summary("MeanReversionAlpha", samples=12, avg=5.0, hit=0.85)),
            SymbolAlphaEvidence("AMD", summary("MeanReversionAlpha", samples=12, avg=-2.0, hit=0.45)),
            SymbolAlphaEvidence("AAPL", summary("MeanReversionAlpha", samples=12, avg=0.2, hit=0.52)),
            SymbolAlphaEvidence("SPY", summary("MeanReversionAlpha", samples=12, avg=-0.3, hit=0.45)),
        )
        result = evaluator.evaluate(evidence)
        self.assertFalse(result.eligible)
        self.assertLess(result.positive_breadth, 0.60)

    def test_broad_repeatable_edge_can_pass(self) -> None:
        evaluator = AlphaBreadthEvaluator(
            minimum_symbols=4,
            minimum_samples_per_symbol=10,
            minimum_positive_breadth=0.60,
            minimum_median_return_pct=0.0,
            minimum_median_hit_rate=0.50,
        )
        evidence = tuple(
            SymbolAlphaEvidence(symbol, summary("WilliamsAlpha", samples=20, avg=avg, hit=hit))
            for symbol, avg, hit in (
                ("AAPL", 0.8, 0.60),
                ("AMD", 1.1, 0.62),
                ("NVDA", 0.3, 0.54),
                ("SPY", 0.4, 0.56),
            )
        )
        result = evaluator.evaluate(evidence)
        self.assertTrue(result.eligible)
        self.assertEqual(result.positive_breadth, 1.0)
        self.assertEqual(result.symbols_with_min_samples, 4)

    def test_low_sample_symbols_do_not_count_as_evidence(self) -> None:
        evaluator = AlphaBreadthEvaluator(
            minimum_symbols=3,
            minimum_samples_per_symbol=10,
        )
        evidence = (
            SymbolAlphaEvidence("AAA", summary("TrendAlpha", samples=4, avg=5.0, hit=1.0)),
            SymbolAlphaEvidence("BBB", summary("TrendAlpha", samples=4, avg=4.0, hit=1.0)),
            SymbolAlphaEvidence("CCC", summary("TrendAlpha", samples=12, avg=1.0, hit=0.60)),
        )
        result = evaluator.evaluate(evidence)
        self.assertFalse(result.eligible)
        self.assertEqual(result.symbols_with_min_samples, 1)

    def test_mixed_models_are_rejected(self) -> None:
        evaluator = AlphaBreadthEvaluator()
        with self.assertRaises(ValueError):
            evaluator.evaluate(
                (
                    SymbolAlphaEvidence("AAA", summary("A", samples=20, avg=1.0, hit=0.6)),
                    SymbolAlphaEvidence("BBB", summary("B", samples=20, avg=1.0, hit=0.6)),
                )
            )


if __name__ == "__main__":
    unittest.main()
