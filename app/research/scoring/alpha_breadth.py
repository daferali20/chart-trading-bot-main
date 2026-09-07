from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from collections.abc import Iterable

from app.research.validation.alpha_forward import AlphaForwardSummary


@dataclass(frozen=True)
class SymbolAlphaEvidence:
    symbol: str
    summary: AlphaForwardSummary


@dataclass(frozen=True)
class AlphaBreadthEvidence:
    model: str
    horizon_bars: int
    symbols_tested: int
    symbols_with_min_samples: int
    total_samples: int
    positive_symbols: int
    positive_breadth: float
    median_symbol_signed_return_pct: float
    median_symbol_hit_rate: float
    worst_symbol_signed_return_pct: float
    best_symbol_signed_return_pct: float
    eligible: bool
    reasons: tuple[str, ...]


class AlphaBreadthEvaluator:
    """Require Alpha evidence to generalize across symbols, not one lucky ticker.

    This gate intentionally evaluates symbol-level averages rather than pooling
    all observations. Pooling can let one highly active ticker dominate a
    candidate and hide poor breadth across the rest of the universe.
    """

    def __init__(
        self,
        *,
        minimum_symbols: int = 5,
        minimum_samples_per_symbol: int = 10,
        minimum_positive_breadth: float = 0.60,
        minimum_median_return_pct: float = 0.0,
        minimum_median_hit_rate: float = 0.50,
    ) -> None:
        self.minimum_symbols = max(1, int(minimum_symbols))
        self.minimum_samples_per_symbol = max(1, int(minimum_samples_per_symbol))
        self.minimum_positive_breadth = max(0.0, min(1.0, float(minimum_positive_breadth)))
        self.minimum_median_return_pct = float(minimum_median_return_pct)
        self.minimum_median_hit_rate = max(0.0, min(1.0, float(minimum_median_hit_rate)))

    def evaluate(
        self,
        evidence: Iterable[SymbolAlphaEvidence],
    ) -> AlphaBreadthEvidence:
        items = tuple(evidence)
        if not items:
            return AlphaBreadthEvidence(
                model="",
                horizon_bars=0,
                symbols_tested=0,
                symbols_with_min_samples=0,
                total_samples=0,
                positive_symbols=0,
                positive_breadth=0.0,
                median_symbol_signed_return_pct=0.0,
                median_symbol_hit_rate=0.0,
                worst_symbol_signed_return_pct=0.0,
                best_symbol_signed_return_pct=0.0,
                eligible=False,
                reasons=("No symbol-level Alpha evidence",),
            )

        models = {item.summary.model for item in items}
        horizons = {item.summary.horizon_bars for item in items}
        if len(models) != 1:
            raise ValueError("Breadth evidence must contain one Alpha model")
        if len(horizons) != 1:
            raise ValueError("Breadth evidence must contain one forward horizon")

        qualified = tuple(
            item
            for item in items
            if item.summary.samples >= self.minimum_samples_per_symbol
        )
        returns = [item.summary.average_signed_return_pct for item in qualified]
        hits = [item.summary.hit_rate for item in qualified]
        positive = sum(value > self.minimum_median_return_pct for value in returns)
        breadth = 0.0 if not qualified else positive / len(qualified)

        median_return = 0.0 if not returns else float(median(returns))
        median_hit = 0.0 if not hits else float(median(hits))
        worst = 0.0 if not returns else float(min(returns))
        best = 0.0 if not returns else float(max(returns))

        reasons: list[str] = []
        if len(qualified) < self.minimum_symbols:
            reasons.append(
                f"Insufficient symbols with >= {self.minimum_samples_per_symbol} samples: "
                f"{len(qualified)} < {self.minimum_symbols}"
            )
        if breadth < self.minimum_positive_breadth:
            reasons.append(
                f"Positive symbol breadth too low: {breadth:.1%} < "
                f"{self.minimum_positive_breadth:.1%}"
            )
        if median_return <= self.minimum_median_return_pct:
            reasons.append(
                f"Median symbol signed return did not exceed "
                f"{self.minimum_median_return_pct:+.3f}%"
            )
        if median_hit < self.minimum_median_hit_rate:
            reasons.append(
                f"Median symbol hit rate too low: {median_hit:.1%} < "
                f"{self.minimum_median_hit_rate:.1%}"
            )

        return AlphaBreadthEvidence(
            model=next(iter(models)),
            horizon_bars=next(iter(horizons)),
            symbols_tested=len(items),
            symbols_with_min_samples=len(qualified),
            total_samples=sum(item.summary.samples for item in qualified),
            positive_symbols=positive,
            positive_breadth=round(breadth, 6),
            median_symbol_signed_return_pct=round(median_return, 6),
            median_symbol_hit_rate=round(median_hit, 6),
            worst_symbol_signed_return_pct=round(worst, 6),
            best_symbol_signed_return_pct=round(best, 6),
            eligible=not reasons,
            reasons=tuple(reasons or ("Cross-symbol Alpha breadth gates passed",)),
        )


DEFAULT_ALPHA_BREADTH_EVALUATOR = AlphaBreadthEvaluator()
