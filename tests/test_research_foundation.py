from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.research.experiments.models import ExperimentDefinition, ExperimentStatus
from app.research.experiments.runner import ExperimentRunner
from app.research.registry.models import StrategyRecord, StrategyStatus
from app.research.registry.strategy_registry import RegistryError, StrategyRegistry


class ResearchFoundationTests(unittest.TestCase):
    def test_locked_baseline_cannot_be_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(Path(temp_dir) / "registry.json")
            baseline = StrategyRecord(
                name="BASELINE_v1",
                status=StrategyStatus.BASELINE,
                source_path="strategy.py",
                locked=True,
            )
            registry.register(baseline)

            with self.assertRaises(RegistryError):
                registry.register(baseline, replace_existing=True)

    def test_experiment_runner_compares_without_execution_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = StrategyRegistry(root / "registry.json")
            registry.register(
                StrategyRecord(
                    name="BASELINE_v1",
                    status=StrategyStatus.BASELINE,
                    source_path="baseline.py",
                    locked=True,
                )
            )
            registry.register(
                StrategyRecord(
                    name="CANDIDATE_v1",
                    status=StrategyStatus.RESEARCH,
                    source_path="candidate.py",
                )
            )

            def fake_backtest(name, data, parameters):
                if name == "BASELINE_v1":
                    return {"return_pct": 10.0, "max_drawdown_pct": 8.0}
                return {"return_pct": 12.0, "max_drawdown_pct": 7.0}

            runner = ExperimentRunner(
                registry,
                fake_backtest,
                reports_dir=root / "experiments",
            )
            experiment = ExperimentDefinition(
                experiment_id="EXP_001",
                hypothesis="Candidate improves return without increasing drawdown",
                baseline_strategy="BASELINE_v1",
                candidate_strategy="CANDIDATE_v1",
                dataset="TEST",
            )
            result = runner.run(experiment, data=[])

            self.assertEqual(result.status, ExperimentStatus.COMPLETED)
            self.assertEqual(result.comparison["return_pct"]["delta"], 2.0)
            self.assertEqual(result.comparison["max_drawdown_pct"]["delta"], -1.0)
            self.assertTrue((root / "experiments" / "EXP_001.json").exists())


if __name__ == "__main__":
    unittest.main()
