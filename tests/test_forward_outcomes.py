from __future__ import annotations

import unittest

import pandas as pd

from app.research.outcomes import ForwardOutcomeEvaluator


class ForwardOutcomeEvaluatorTests(unittest.TestCase):
    @staticmethod
    def bars() -> pd.DataFrame:
        closes = [100.0, 102.0, 104.0, 103.0, 106.0, 108.0]
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="UTC"),
                "open": closes,
                "high": [value + 1.0 for value in closes],
                "low": [value - 1.0 for value in closes],
                "close": closes,
                "volume": [1_000_000.0] * len(closes),
            }
        )

    def test_buy_is_scored_on_forward_returns(self) -> None:
        evaluator = ForwardOutcomeEvaluator(horizons=(1, 3), neutral_band_pct=0.5)
        outcomes = evaluator.evaluate(
            observed_at="2026-01-02T23:59:00+00:00",
            action="BUY",
            bars=self.bars(),
        )

        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[0].horizon_bars, 1)
        self.assertGreater(outcomes[0].signed_return_pct, 0.0)
        self.assertTrue(outcomes[0].correct_direction)
        self.assertGreater(outcomes[0].mfe_pct, 0.0)

    def test_sell_inverts_forward_return_sign(self) -> None:
        evaluator = ForwardOutcomeEvaluator(horizons=(1,))
        outcomes = evaluator.evaluate(
            observed_at="2026-01-02T23:59:00+00:00",
            action="SELL",
            bars=self.bars(),
        )

        self.assertEqual(len(outcomes), 1)
        self.assertLess(outcomes[0].signed_return_pct, 0.0)
        self.assertFalse(outcomes[0].correct_direction)

    def test_not_enough_future_bars_returns_only_available_horizons(self) -> None:
        evaluator = ForwardOutcomeEvaluator(horizons=(1, 3, 5))
        outcomes = evaluator.evaluate(
            observed_at="2026-01-05T23:59:00+00:00",
            action="BUY",
            bars=self.bars(),
        )

        self.assertEqual(tuple(item.horizon_bars for item in outcomes), (1,))

    def test_summary_reports_hit_rate_and_average_edge(self) -> None:
        evaluator = ForwardOutcomeEvaluator(horizons=(1, 3))
        outcomes = evaluator.evaluate(
            observed_at="2026-01-02T23:59:00+00:00",
            action="BUY",
            bars=self.bars(),
        )
        summary = evaluator.summarize(outcomes)

        self.assertEqual(summary.samples, 2)
        self.assertGreater(summary.hit_rate, 0.0)
        self.assertGreater(summary.average_signed_return_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
