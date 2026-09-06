from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.research.agent.coordinator import (
    ResearchAgentCoordinator,
    ResearchApprovalPolicy,
)
from app.research.experiments.models import ExperimentStatus
from app.research.registry.models import StrategyRecord, StrategyStatus
from app.research.registry.strategy_registry import StrategyRegistry
from app.research.validation.walk_forward import WalkForwardConfig


class ResearchAgentTests(unittest.TestCase):
    @staticmethod
    def dataset(rows: int = 180) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=rows, freq="D"),
                "open": [100.0] * rows,
                "high": [101.0] * rows,
                "low": [99.0] * rows,
                "close": [100.5] * rows,
                "volume": [1_000_000] * rows,
            }
        )

    @staticmethod
    def register_pair(registry: StrategyRegistry, candidate: str) -> None:
        registry.register(
            StrategyRecord(
                name="BASELINE",
                status=StrategyStatus.BASELINE,
                source_path="baseline.py",
                locked=True,
            )
        )
        registry.register(
            StrategyRecord(
                name=candidate,
                status=StrategyStatus.RESEARCH,
                source_path="candidate.py",
                locked=False,
            )
        )

    def test_robust_candidate_is_approved_without_touching_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = StrategyRegistry(root / "registry.json")
            self.register_pair(registry, "GOOD")

            def backtest(strategy, data, parameters):
                if strategy == "BASELINE":
                    return {
                        "return": 0.10,
                        "profit_factor": 1.30,
                        "win_rate": 0.52,
                        "sharpe": 1.00,
                        "max_drawdown": 0.12,
                        "trade_concentration": 0.30,
                    }
                return {
                    "return": 0.18,
                    "profit_factor": 1.80,
                    "win_rate": 0.60,
                    "sharpe": 1.60,
                    "max_drawdown": 0.10,
                    "trade_concentration": 0.20,
                }

            agent = ResearchAgentCoordinator(
                registry=registry,
                backtest=backtest,
                walk_forward=WalkForwardConfig(
                    train_bars=60,
                    validation_bars=40,
                    step_bars=40,
                ),
                policy=ResearchApprovalPolicy(min_robustness_score=60.0),
                reports_dir=root / "experiments",
                approved_dir=root / "approved",
                rejected_dir=root / "rejected",
            )
            experiment = agent.create_experiment(
                experiment_id="EXP_GOOD",
                hypothesis="Candidate improves baseline robustly",
                baseline_strategy="BASELINE",
                candidate_strategy="GOOD",
                dataset="synthetic",
            )

            result, decision = agent.run(experiment, self.dataset())

            self.assertEqual(result.status, ExperimentStatus.APPROVED)
            self.assertEqual(decision.status, ExperimentStatus.APPROVED)
            self.assertGreaterEqual(decision.robustness_score, 60.0)
            self.assertEqual(registry.require("GOOD").status, StrategyStatus.APPROVED)
            self.assertEqual(registry.require("BASELINE").status, StrategyStatus.BASELINE)
            self.assertTrue(registry.require("BASELINE").locked)
            self.assertTrue(Path(decision.report_path).exists())
            self.assertIn("walk_forward", result.validation)

    def test_degrading_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = StrategyRegistry(root / "registry.json")
            self.register_pair(registry, "BAD")

            def backtest(strategy, data, parameters):
                if strategy == "BASELINE":
                    return {
                        "return": 0.10,
                        "profit_factor": 1.30,
                        "win_rate": 0.52,
                        "sharpe": 1.00,
                        "max_drawdown": 0.12,
                    }
                if len(data) > 100:
                    return {
                        "return": 0.80,
                        "profit_factor": 3.00,
                        "win_rate": 0.75,
                        "sharpe": 2.80,
                        "max_drawdown": 0.06,
                    }
                return {
                    "return": -0.05,
                    "profit_factor": 0.70,
                    "win_rate": 0.40,
                    "sharpe": -0.20,
                    "max_drawdown": 0.30,
                }

            agent = ResearchAgentCoordinator(
                registry=registry,
                backtest=backtest,
                walk_forward=WalkForwardConfig(
                    train_bars=60,
                    validation_bars=40,
                    step_bars=40,
                ),
                reports_dir=root / "experiments",
                approved_dir=root / "approved",
                rejected_dir=root / "rejected",
            )
            experiment = agent.create_experiment(
                experiment_id="EXP_BAD",
                hypothesis="Candidate may be overfit",
                baseline_strategy="BASELINE",
                candidate_strategy="BAD",
                dataset="synthetic",
            )

            result, decision = agent.run(experiment, self.dataset())

            self.assertEqual(result.status, ExperimentStatus.REJECTED)
            self.assertEqual(registry.require("BAD").status, StrategyStatus.REJECTED)
            self.assertEqual(registry.require("BASELINE").status, StrategyStatus.BASELINE)
            self.assertTrue(decision.reasons)
            self.assertTrue(Path(decision.report_path).exists())

    def test_insufficient_walk_forward_history_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = StrategyRegistry(root / "registry.json")
            self.register_pair(registry, "SHORT_HISTORY")

            def backtest(strategy, data, parameters):
                return {
                    "return": 0.20,
                    "profit_factor": 1.80,
                    "win_rate": 0.60,
                    "sharpe": 1.50,
                    "max_drawdown": 0.10,
                }

            agent = ResearchAgentCoordinator(
                registry=registry,
                backtest=backtest,
                walk_forward=WalkForwardConfig(
                    train_bars=100,
                    validation_bars=60,
                ),
                reports_dir=root / "experiments",
                approved_dir=root / "approved",
                rejected_dir=root / "rejected",
            )
            experiment = agent.create_experiment(
                experiment_id="EXP_SHORT",
                hypothesis="Insufficient data must not approve",
                baseline_strategy="BASELINE",
                candidate_strategy="SHORT_HISTORY",
                dataset="short",
            )

            result, decision = agent.run(experiment, self.dataset(120))

            self.assertEqual(result.status, ExperimentStatus.REJECTED)
            self.assertTrue(
                any("folds" in reason.lower() or "missing oos" in reason.lower() for reason in decision.reasons)
            )


if __name__ == "__main__":
    unittest.main()
