from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from collections import defaultdict
from collections.abc import Iterable


@dataclass(frozen=True)
class TimeBucketAlphaEvidence:
    symbol: str
    period: str
    model: str
    horizon_bars: int
    samples: int
    average_signed_return_pct: float
    hit_rate: float


@dataclass(frozen=True)
class TimeBucketSummary:
    period: str
    symbols_with_min_samples: int
    total_samples: int
    positive_symbol_breadth: float
    median_symbol_signed_return_pct: float
    median_symbol_hit_rate: float
    positive: bool


@dataclass(frozen=True)
class AlphaTemporalStabilityEvidence:
    model: str
    horizon_bars: int
    periods_tested: int
    periods_with_min_symbols: int
    positive_periods: int
    positive_period_ratio: float
    median_period_signed_return_pct: float
    median_period_hit_rate: float
    worst_period_signed_return_pct: float
    best_period_signed_return_pct: float
    periods: tuple[TimeBucketSummary, ...]
    eligible: bool
    reasons: tuple[str, ...]


class AlphaTemporalStabilityEvaluator:
    """Require an Alpha edge to persist across time, not only across symbols.

    Each period is evaluated from symbol-level averages, so one very active
    stock cannot dominate a time bucket. The caller decides how periods are
    constructed (for example equal one-year buckets from a dataset start).
    """

    def __init__(
        self,
        *,
        minimum_periods: int = 4,
        minimum_symbols_per_period: int = 10,
        minimum_samples_per_symbol_period: int = 3,
        minimum_positive_symbol_breadth: float = 0.50,
        minimum_positive_period_ratio: float = 0.60,
        minimum_median_period_return_pct: float = 0.0,
        minimum_median_period_hit_rate: float = 0.50,
    ) -> None:
        self.minimum_periods = max(1, int(minimum_periods))
        self.minimum_symbols_per_period = max(1, int(minimum_symbols_per_period))
        self.minimum_samples_per_symbol_period = max(
            1, int(minimum_samples_per_symbol_period)
        )
        self.minimum_positive_symbol_breadth = max(
            0.0, min(1.0, float(minimum_positive_symbol_breadth))
        )
        self.minimum_positive_period_ratio = max(
            0.0, min(1.0, float(minimum_positive_period_ratio))
        )
        self.minimum_median_period_return_pct = float(
            minimum_median_period_return_pct
        )
        self.minimum_median_period_hit_rate = max(
            0.0, min(1.0, float(minimum_median_period_hit_rate))
        )

    def evaluate(
        self,
        evidence: Iterable[TimeBucketAlphaEvidence],
    ) -> AlphaTemporalStabilityEvidence:
        items = tuple(evidence)
        if not items:
            return AlphaTemporalStabilityEvidence(
                model="",
                horizon_bars=0,
                periods_tested=0,
                periods_with_min_symbols=0,
                positive_periods=0,
                positive_period_ratio=0.0,
                median_period_signed_return_pct=0.0,
                median_period_hit_rate=0.0,
                worst_period_signed_return_pct=0.0,
                best_period_signed_return_pct=0.0,
                periods=(),
                eligible=False,
                reasons=("No temporal Alpha evidence",),
            )

        models = {item.model for item in items}
        horizons = {item.horizon_bars for item in items}
        if len(models) != 1:
            raise ValueError("Temporal evidence must contain one Alpha model")
        if len(horizons) != 1:
            raise ValueError("Temporal evidence must contain one forward horizon")

        grouped: dict[str, list[TimeBucketAlphaEvidence]] = defaultdict(list)
        for item in items:
            grouped[item.period].append(item)

        period_summaries: list[TimeBucketSummary] = []
        for period in sorted(grouped):
            qualified = [
                item
                for item in grouped[period]
                if item.samples >= self.minimum_samples_per_symbol_period
            ]
            returns = [item.average_signed_return_pct for item in qualified]
            hits = [item.hit_rate for item in qualified]
            positive_symbols = sum(value > 0.0 for value in returns)
            breadth = 0.0 if not qualified else positive_symbols / len(qualified)
            median_return = 0.0 if not returns else float(median(returns))
            median_hit = 0.0 if not hits else float(median(hits))
            enough_symbols = len(qualified) >= self.minimum_symbols_per_period
            positive_period = (
                enough_symbols
                and breadth >= self.minimum_positive_symbol_breadth
                and median_return > self.minimum_median_period_return_pct
                and median_hit >= self.minimum_median_period_hit_rate
            )
            period_summaries.append(
                TimeBucketSummary(
                    period=period,
                    symbols_with_min_samples=len(qualified),
                    total_samples=sum(item.samples for item in qualified),
                    positive_symbol_breadth=round(breadth, 6),
                    median_symbol_signed_return_pct=round(median_return, 6),
                    median_symbol_hit_rate=round(median_hit, 6),
                    positive=positive_period,
                )
            )

        qualified_periods = [
            item
            for item in period_summaries
            if item.symbols_with_min_samples >= self.minimum_symbols_per_period
        ]
        positive_periods = sum(item.positive for item in qualified_periods)
        positive_ratio = (
            0.0 if not qualified_periods else positive_periods / len(qualified_periods)
        )
        period_returns = [
            item.median_symbol_signed_return_pct for item in qualified_periods
        ]
        period_hits = [item.median_symbol_hit_rate for item in qualified_periods]
        median_period_return = (
            0.0 if not period_returns else float(median(period_returns))
        )
        median_period_hit = 0.0 if not period_hits else float(median(period_hits))
        worst = 0.0 if not period_returns else float(min(period_returns))
        best = 0.0 if not period_returns else float(max(period_returns))

        reasons: list[str] = []
        if len(qualified_periods) < self.minimum_periods:
            reasons.append(
                f"Insufficient periods with >= {self.minimum_symbols_per_period} symbols: "
                f"{len(qualified_periods)} < {self.minimum_periods}"
            )
        if positive_ratio < self.minimum_positive_period_ratio:
            reasons.append(
                f"Positive period ratio too low: {positive_ratio:.1%} < "
                f"{self.minimum_positive_period_ratio:.1%}"
            )
        if median_period_return <= self.minimum_median_period_return_pct:
            reasons.append(
                "Median period signed return did not exceed "
                f"{self.minimum_median_period_return_pct:+.3f}%"
            )
        if median_period_hit < self.minimum_median_period_hit_rate:
            reasons.append(
                f"Median period hit rate too low: {median_period_hit:.1%} < "
                f"{self.minimum_median_period_hit_rate:.1%}"
            )

        return AlphaTemporalStabilityEvidence(
            model=next(iter(models)),
            horizon_bars=next(iter(horizons)),
            periods_tested=len(period_summaries),
            periods_with_min_symbols=len(qualified_periods),
            positive_periods=positive_periods,
            positive_period_ratio=round(positive_ratio, 6),
            median_period_signed_return_pct=round(median_period_return, 6),
            median_period_hit_rate=round(median_period_hit, 6),
            worst_period_signed_return_pct=round(worst, 6),
            best_period_signed_return_pct=round(best, 6),
            periods=tuple(period_summaries),
            eligible=not reasons,
            reasons=tuple(reasons or ("Temporal Alpha stability gates passed",)),
        )


DEFAULT_ALPHA_TEMPORAL_STABILITY_EVALUATOR = AlphaTemporalStabilityEvaluator()
