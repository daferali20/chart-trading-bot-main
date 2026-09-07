from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from app.research.experiments.models import (
    ExperimentDefinition,
    ExperimentResult,
    ExperimentStatus,
    utc_now_iso,
)
from app.research.experiments.runner import BacktestCallable, ExperimentRunner
from app.research.registry.models import StrategyStatus
from app.research.registry.strategy_registry import StrategyRegistry
from app.research.scoring.robustness import RobustnessScorer
from app.research.validation.walk_forward import (
    WalkForwardConfig,
    WalkForwardValidator,
)


@dataclass(frozen=True)
class ResearchApprovalPolicy:
    min_walk_forward_folds: int = 3
    min_robustness_score: float = 60.0
    min_oos_return: float = 0.0
    min_oos_profit_factor: float = 1.0
    max_oos_drawdown: float = 0.25
    # Applied automatically when an event-aware backtest supplies normal-market
    # metrics. Legacy experiments remain backward-compatible until they are
    # upgraded to classify NORMAL vs EVENT_RELATED trades.
    min_normal_trade_count: int = 10
    min_normal_return: float = 0.0
    min_normal_profit_factor: float = 1.20
    max_event_profit_share: float = 0.60


@dataclass(frozen=True)
class ResearchDecision:
    experiment_id: str
    status: ExperimentStatus
    robustness_score: float
    reasons: tuple[str, ...]
    report_path: str


class ResearchAgentCoordinator:
    """Historical-research coordinator with no broker/execution capability.

    Workflow:
      hypothesis -> baseline/candidate backtest -> walk-forward OOS validation
      -> robustness/overfit score -> APPROVED or REJECTED -> registry/report.

    The coordinator cannot place orders and never imports app.broker or
    app.execution. Approval only changes research metadata.
    """

    REQUIRED_OOS_METRICS = (
        "return",
        "profit_factor",
        "win_rate",
        "max_drawdown",
    )
    NORMAL_MARKET_METRICS = (
        "normal_trade_count",
        "normal_return",
        "normal_profit_factor",
        "event_profit_share",
    )

    def __init__(
        self,
        *,
        registry: StrategyRegistry,
        backtest: BacktestCallable,
        walk_forward: WalkForwardConfig,
        policy: ResearchApprovalPolicy | None = None,
        reports_dir: str | Path = "research/experiments",
        approved_dir: str | Path = "research/approved",
        rejected_dir: str | Path = "research/rejected",
    ) -> None:
        self.registry = registry
        self.backtest = backtest
        self.walk_forward_config = walk_forward
        self.policy = policy or ResearchApprovalPolicy()
        self.reports_dir = Path(reports_dir)
        self.approved_dir = Path(approved_dir)
        self.rejected_dir = Path(rejected_dir)
        self.scorer = RobustnessScorer()
        self.runner = ExperimentRunner(
            registry,
            backtest,
            reports_dir=self.reports_dir,
        )

    @staticmethod
    def create_experiment(
        *,
        hypothesis: str,
        baseline_strategy: str,
        candidate_strategy: str,
        dataset: str,
        parameters: Mapping[str, Any] | None = None,
        notes: str = "",
        experiment_id: str | None = None,
    ) -> ExperimentDefinition:
        if not hypothesis.strip():
            raise ValueError("hypothesis is required")
        if not experiment_id:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            experiment_id = f"EXP_{stamp}_{uuid4().hex[:6].upper()}"

        return ExperimentDefinition(
            experiment_id=experiment_id,
            hypothesis=hypothesis,
            baseline_strategy=baseline_strategy,
            candidate_strategy=candidate_strategy,
            dataset=dataset,
            parameters=dict(parameters or {}),
            notes=notes,
        )

    def _walk_forward(
        self,
        experiment: ExperimentDefinition,
        data: pd.DataFrame,
    ) -> dict[str, Any]:
        validator = WalkForwardValidator(self.walk_forward_config)

        def evaluate_fold(train, validation, split):
            # Fixed-parameter experiments are evaluated only on the unseen
            # validation frame. The train frame is reserved for future fitting
            # or parameter selection and is intentionally not mixed into OOS.
            baseline = dict(
                self.backtest(
                    experiment.baseline_strategy,
                    validation,
                    {},
                )
            )
            candidate = dict(
                self.backtest(
                    experiment.candidate_strategy,
                    validation,
                    experiment.parameters,
                )
            )

            output: dict[str, Any] = {}
            for prefix, metrics in (
                ("baseline", baseline),
                ("candidate", candidate),
            ):
                for key, value in metrics.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        output[f"{prefix}_{key}"] = float(value)
            return output

        result = validator.validate(data, evaluate_fold)
        return {
            "folds": result.aggregate.get("folds", 0),
            "aggregate": result.aggregate,
            "fold_results": [
                {
                    "fold": fold.split.fold,
                    "train_start": fold.split.train_start,
                    "train_end": fold.split.train_end,
                    "validation_start": fold.split.validation_start,
                    "validation_end": fold.split.validation_end,
                    "metrics": fold.metrics,
                }
                for fold in result.folds
            ],
        }

    @staticmethod
    def _candidate_oos_metrics(walk_forward: Mapping[str, Any]) -> dict[str, float]:
        aggregate = walk_forward.get("aggregate", {})
        metrics: dict[str, float] = {}
        suffix = "_mean"
        prefix = "candidate_"
        for key, value in aggregate.items():
            if key.startswith(prefix) and key.endswith(suffix):
                metric = key[len(prefix):-len(suffix)]
                metrics[metric] = float(value)
        return metrics

    @staticmethod
    def _stability(walk_forward: Mapping[str, Any]) -> float:
        aggregate = walk_forward.get("aggregate", {})
        std = abs(float(aggregate.get("candidate_return_std", 1.0)))
        # 0% fold dispersion -> 1.0 stability; 20%+ -> 0.0.
        return max(0.0, min(1.0, 1.0 - (std / 0.20)))

    def _normal_market_reasons(self, oos: Mapping[str, float]) -> list[str]:
        # Only activate this gate when the experiment supplies at least one
        # event-aware metric. Once activated, the full evidence set is required.
        if not any(key in oos for key in self.NORMAL_MARKET_METRICS):
            return []

        reasons: list[str] = []
        missing = [key for key in self.NORMAL_MARKET_METRICS if key not in oos]
        if missing:
            return [
                "Incomplete normal-market OOS evidence: " + ", ".join(missing)
            ]

        normal_trades = int(round(oos["normal_trade_count"]))
        if normal_trades < self.policy.min_normal_trade_count:
            reasons.append(
                f"Insufficient normal-market trades: {normal_trades} < "
                f"{self.policy.min_normal_trade_count}"
            )
        if oos["normal_return"] <= self.policy.min_normal_return:
            reasons.append("Normal-market OOS return did not exceed minimum")
        if oos["normal_profit_factor"] < self.policy.min_normal_profit_factor:
            reasons.append(
                "Normal-market OOS profit factor below minimum "
                f"({oos['normal_profit_factor']:.2f} < "
                f"{self.policy.min_normal_profit_factor:.2f})"
            )
        if oos["event_profit_share"] > self.policy.max_event_profit_share:
            reasons.append(
                "Candidate depends too heavily on event-driven positive returns "
                f"({oos['event_profit_share']:.1%} > "
                f"{self.policy.max_event_profit_share:.1%})"
            )
        return reasons

    def _decision_reasons(
        self,
        *,
        folds: int,
        oos: Mapping[str, float],
        robustness_score: float,
    ) -> list[str]:
        reasons: list[str] = []
        missing = [key for key in self.REQUIRED_OOS_METRICS if key not in oos]
        if missing:
            reasons.append(f"Missing OOS metrics: {', '.join(missing)}")
        if folds < self.policy.min_walk_forward_folds:
            reasons.append(
                f"Insufficient walk-forward folds: {folds} < "
                f"{self.policy.min_walk_forward_folds}"
            )
        if robustness_score < self.policy.min_robustness_score:
            reasons.append(
                f"Robustness score too low: {robustness_score:.2f} < "
                f"{self.policy.min_robustness_score:.2f}"
            )
        if oos.get("return", float("-inf")) <= self.policy.min_oos_return:
            reasons.append("Out-of-sample return did not exceed minimum")
        if oos.get("profit_factor", float("-inf")) < self.policy.min_oos_profit_factor:
            reasons.append("Out-of-sample profit factor below minimum")
        if abs(oos.get("max_drawdown", float("inf"))) > self.policy.max_oos_drawdown:
            reasons.append("Out-of-sample drawdown exceeds maximum")
        reasons.extend(self._normal_market_reasons(oos))
        return reasons

    def _save_final_report(self, result: ExperimentResult) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        primary = self.reports_dir / f"{result.experiment.experiment_id}.json"
        payload = json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
        primary.write_text(payload, encoding="utf-8")

        destination_dir = (
            self.approved_dir
            if result.status is ExperimentStatus.APPROVED
            else self.rejected_dir
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / primary.name
        destination.write_text(payload, encoding="utf-8")
        return destination

    def run(
        self,
        experiment: ExperimentDefinition,
        data: pd.DataFrame,
    ) -> tuple[ExperimentResult, ResearchDecision]:
        if data is None or data.empty:
            raise ValueError("Research dataset is empty")

        # Verify both records first; locked BASELINE stays untouched.
        self.registry.require(experiment.baseline_strategy)
        candidate_record = self.registry.require(experiment.candidate_strategy)
        if candidate_record.locked:
            raise ValueError("Candidate strategy must not be locked")

        result = self.runner.run(experiment, data)
        walk_forward = self._walk_forward(experiment, data)
        oos = self._candidate_oos_metrics(walk_forward)
        stability = self._stability(walk_forward)
        concentration = oos.get("trade_concentration")

        robustness = self.scorer.score(
            result.candidate_metrics,
            oos,
            stability=stability,
            trade_concentration=concentration,
        )

        reasons = self._decision_reasons(
            folds=int(walk_forward["folds"]),
            oos=oos,
            robustness_score=robustness.score,
        )

        approved = not reasons
        result.status = (
            ExperimentStatus.APPROVED
            if approved
            else ExperimentStatus.REJECTED
        )
        result.validation = {
            "walk_forward": walk_forward,
            "oos_candidate_metrics": oos,
            "normal_market_evidence_present": any(
                key in oos for key in self.NORMAL_MARKET_METRICS
            ),
            "stability": stability,
            "robustness_score": robustness.score,
            "robustness_components": robustness.components,
            "robustness_warnings": list(robustness.warnings),
            "decision_reasons": reasons or ["All research approval gates passed"],
        }
        result.finished_at = utc_now_iso()

        self.registry.update_status(
            experiment.candidate_strategy,
            StrategyStatus.APPROVED if approved else StrategyStatus.REJECTED,
            last_tested_at=result.finished_at,
        )
        report_path = self._save_final_report(result)

        return result, ResearchDecision(
            experiment_id=experiment.experiment_id,
            status=result.status,
            robustness_score=robustness.score,
            reasons=tuple(reasons or ["All research approval gates passed"]),
            report_path=str(report_path),
        )
