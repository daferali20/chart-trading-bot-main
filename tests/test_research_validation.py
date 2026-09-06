from __future__ import annotations

import unittest

import pandas as pd

from app.research.scoring.robustness import RobustnessScorer
from app.research.validation.walk_forward import (
    WalkForwardConfig,
    WalkForwardValidator,
)


class WalkForwardTests(unittest.TestCase):
    def test_splits_are_chronological_and_disjoint(self) -> None:
        validator = WalkForwardValidator(
            WalkForwardConfig(
                train_bars=60,
                validation_bars=20,
                step_bars=20,
            )
        )
        splits = validator.splits(140)
        self.assertEqual(len(splits), 4)
        for split in splits:
            self.assertLessEqual(split.train_end, split.validation_start)
            self.assertEqual(split.validation_start, split.train_end)
            self.assertEqual(split.validation_end - split.validation_start, 20)

    def test_validate_aggregates_oos_metrics(self) -> None:
        data = pd.DataFrame({"value": range(120)})
        validator = WalkForwardValidator(
            WalkForwardConfig(train_bars=60, validation_bars=20)
        )

        def evaluator(train, validation, split):
            self.assertLess(train.index.max(), validation.index.min())
            return {
                "return": 0.05 * split.fold,
                "win_rate": 0.50 + (0.05 * split.fold),
            }

        result = validator.validate(data, evaluator)
        self.assertEqual(result.aggregate["folds"], 3)
        self.assertAlmostEqual(result.aggregate["return_mean"], 0.10)
        self.assertGreater(result.aggregate["return_std"], 0.0)

    def test_insufficient_history_produces_no_folds(self) -> None:
        validator = WalkForwardValidator(
            WalkForwardConfig(train_bars=100, validation_bars=30)
        )
        self.assertEqual(validator.splits(120), ())


class RobustnessScorerTests(unittest.TestCase):
    def test_robust_oos_profile_scores_better_than_overfit_profile(self) -> None:
        scorer = RobustnessScorer()

        robust = scorer.score(
            {
                "return": 0.25,
                "profit_factor": 1.8,
                "win_rate": 0.58,
                "sharpe": 1.5,
                "max_drawdown": 0.10,
            },
            {
                "return": 0.20,
                "profit_factor": 1.7,
                "win_rate": 0.56,
                "sharpe": 1.3,
                "max_drawdown": 0.11,
            },
            stability=0.80,
            trade_concentration=0.20,
        )

        overfit = scorer.score(
            {
                "return": 0.80,
                "profit_factor": 3.0,
                "win_rate": 0.75,
                "sharpe": 2.8,
                "max_drawdown": 0.06,
            },
            {
                "return": 0.05,
                "profit_factor": 0.90,
                "win_rate": 0.42,
                "sharpe": 0.30,
                "max_drawdown": 0.25,
            },
            stability=0.25,
            trade_concentration=0.70,
        )

        self.assertGreater(robust.score, overfit.score)
        self.assertTrue(
            any("degradation" in warning.lower() for warning in overfit.warnings)
        )
        self.assertGreater(overfit.components["overfit_penalty"], 0.0)

    def test_negative_oos_return_is_flagged(self) -> None:
        result = RobustnessScorer().score(
            {"return": 0.20},
            {
                "return": -0.10,
                "profit_factor": 0.7,
                "win_rate": 0.35,
                "sharpe": -0.4,
                "max_drawdown": 0.30,
            },
        )
        self.assertTrue(
            any("negative" in warning.lower() for warning in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
