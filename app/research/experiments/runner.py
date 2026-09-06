from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from app.research.experiments.models import (
    ExperimentDefinition,
    ExperimentResult,
    ExperimentStatus,
    utc_now_iso,
)
from app.research.registry.strategy_registry import StrategyRegistry

BacktestCallable = Callable[[str, Any, Mapping[str, Any]], Mapping[str, Any]]
ValidationCallable = Callable[[ExperimentResult], Mapping[str, Any]]


class ExperimentRunner:
    """Run research experiments without broker or execution access.

    The backtest engine is dependency-injected. This keeps the research layer
    isolated from IBKR and allows existing or future backtest engines to be
    plugged in without changing the experiment workflow.
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        backtest: BacktestCallable,
        *,
        validate: ValidationCallable | None = None,
        reports_dir: str | Path = "research/experiments",
    ) -> None:
        self.registry = registry
        self.backtest = backtest
        self.validate = validate
        self.reports_dir = Path(reports_dir)

    @staticmethod
    def _compare(
        baseline: Mapping[str, Any],
        candidate: Mapping[str, Any],
    ) -> Dict[str, Any]:
        comparison: Dict[str, Any] = {}
        numeric_keys = sorted(set(baseline) & set(candidate))
        for key in numeric_keys:
            left = baseline[key]
            right = candidate[key]
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                comparison[key] = {
                    "baseline": left,
                    "candidate": right,
                    "delta": right - left,
                }
        return comparison

    def _save_report(self, result: ExperimentResult) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{result.experiment.experiment_id}.json"
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def run(self, experiment: ExperimentDefinition, data: Any) -> ExperimentResult:
        self.registry.require(experiment.baseline_strategy)
        self.registry.require(experiment.candidate_strategy)

        result = ExperimentResult(
            experiment=experiment,
            status=ExperimentStatus.RUNNING,
        )

        try:
            baseline = dict(
                self.backtest(experiment.baseline_strategy, data, {})
            )
            candidate = dict(
                self.backtest(
                    experiment.candidate_strategy,
                    data,
                    experiment.parameters,
                )
            )

            result.baseline_metrics = baseline
            result.candidate_metrics = candidate
            result.comparison = self._compare(baseline, candidate)

            if self.validate is not None:
                result.validation = dict(self.validate(result))

            result.status = ExperimentStatus.COMPLETED
            result.finished_at = utc_now_iso()
        except Exception as exc:
            result.status = ExperimentStatus.FAILED
            result.error = f"{type(exc).__name__}: {exc}"
            result.finished_at = utc_now_iso()
            self._save_report(result)
            raise

        self._save_report(result)
        return result
