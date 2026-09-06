from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class WalkForwardConfig:
    train_bars: int
    validation_bars: int
    step_bars: int | None = None
    expanding_train: bool = False

    def __post_init__(self) -> None:
        if self.train_bars <= 0:
            raise ValueError("train_bars must be positive")
        if self.validation_bars <= 0:
            raise ValueError("validation_bars must be positive")
        if self.step_bars is not None and self.step_bars <= 0:
            raise ValueError("step_bars must be positive")


@dataclass(frozen=True)
class WalkForwardSplit:
    fold: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int


@dataclass(frozen=True)
class WalkForwardFoldResult:
    split: WalkForwardSplit
    metrics: dict[str, Any]


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[WalkForwardFoldResult, ...]
    aggregate: dict[str, Any]


Evaluator = Callable[
    [pd.DataFrame, pd.DataFrame, WalkForwardSplit],
    Mapping[str, Any],
]


class WalkForwardValidator:
    """Generate chronological train/OOS folds without look-ahead leakage."""

    def __init__(self, config: WalkForwardConfig) -> None:
        self.config = config

    def splits(self, total_bars: int) -> tuple[WalkForwardSplit, ...]:
        if total_bars < self.config.train_bars + self.config.validation_bars:
            return ()

        step = self.config.step_bars or self.config.validation_bars
        folds: list[WalkForwardSplit] = []
        validation_start = self.config.train_bars
        fold = 1

        while validation_start + self.config.validation_bars <= total_bars:
            train_start = 0 if self.config.expanding_train else validation_start - self.config.train_bars
            train_end = validation_start
            validation_end = validation_start + self.config.validation_bars

            folds.append(
                WalkForwardSplit(
                    fold=fold,
                    train_start=train_start,
                    train_end=train_end,
                    validation_start=validation_start,
                    validation_end=validation_end,
                )
            )
            fold += 1
            validation_start += step

        return tuple(folds)

    @staticmethod
    def _aggregate(folds: list[WalkForwardFoldResult]) -> dict[str, Any]:
        if not folds:
            return {"folds": 0}

        numeric_keys = set.intersection(
            *[
                {
                    key
                    for key, value in fold.metrics.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
                for fold in folds
            ]
        ) if folds else set()

        aggregate: dict[str, Any] = {"folds": len(folds)}
        for key in sorted(numeric_keys):
            values = pd.Series([float(fold.metrics[key]) for fold in folds], dtype="float64")
            aggregate[f"{key}_mean"] = float(values.mean())
            aggregate[f"{key}_median"] = float(values.median())
            aggregate[f"{key}_std"] = float(values.std(ddof=0))
            aggregate[f"{key}_min"] = float(values.min())
            aggregate[f"{key}_max"] = float(values.max())

        return aggregate

    def validate(self, data: pd.DataFrame, evaluator: Evaluator) -> WalkForwardResult:
        if data is None or data.empty:
            raise ValueError("Validation data is empty")

        fold_results: list[WalkForwardFoldResult] = []
        for split in self.splits(len(data)):
            train = data.iloc[split.train_start:split.train_end].copy()
            validation = data.iloc[split.validation_start:split.validation_end].copy()

            # The evaluator receives disjoint chronological frames. It may fit
            # parameters on train, but metrics returned here must describe the
            # validation/OOS frame.
            metrics = dict(evaluator(train, validation, split))
            fold_results.append(
                WalkForwardFoldResult(
                    split=split,
                    metrics=metrics,
                )
            )

        return WalkForwardResult(
            folds=tuple(fold_results),
            aggregate=self._aggregate(fold_results),
        )
