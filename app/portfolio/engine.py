from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from app.portfolio.models import (
    ExistingPosition,
    PortfolioAllocation,
    PortfolioCandidate,
    PortfolioPlan,
)


class PortfolioEngine:
    """Construct a bounded portfolio plan from ranked candidates.

    The engine does not place orders. It only proposes weights while enforcing
    position-count, single-name, sector, and correlation concentration limits.
    """

    def __init__(
        self,
        max_positions: int = 7,
        max_symbol_weight: float = 0.25,
        max_sector_weight: float = 0.40,
        max_correlation: float = 0.85,
        min_score: float = 0.0,
        min_confidence: float = 0.0,
    ) -> None:
        if max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if not 0 < max_symbol_weight <= 1:
            raise ValueError("max_symbol_weight must be between 0 and 1")
        if not 0 < max_sector_weight <= 1:
            raise ValueError("max_sector_weight must be between 0 and 1")
        if not 0 <= max_correlation <= 1:
            raise ValueError("max_correlation must be between 0 and 1")

        self.max_positions = max_positions
        self.max_symbol_weight = max_symbol_weight
        self.max_sector_weight = max_sector_weight
        self.max_correlation = max_correlation
        self.min_score = min_score
        self.min_confidence = min_confidence

    @staticmethod
    def _edge(candidate: PortfolioCandidate) -> float:
        return (0.70 * candidate.score) + (0.30 * candidate.confidence)

    @staticmethod
    def _correlation(
        left: str,
        right: str,
        correlations: Mapping[tuple[str, str], float] | None,
    ) -> float | None:
        if not correlations:
            return None
        a, b = left.upper(), right.upper()
        if (a, b) in correlations:
            return abs(float(correlations[(a, b)]))
        if (b, a) in correlations:
            return abs(float(correlations[(b, a)]))
        return None

    def construct(
        self,
        candidates: Sequence[PortfolioCandidate],
        *,
        capital: float,
        existing_positions: Sequence[ExistingPosition] = (),
        correlations: Mapping[tuple[str, str], float] | None = None,
    ) -> PortfolioPlan:
        if capital <= 0:
            raise ValueError("capital must be positive")

        existing_symbols = {position.symbol.upper() for position in existing_positions}
        existing_weight = sum(position.weight for position in existing_positions)
        if existing_weight > 1.0 + 1e-9:
            raise ValueError("existing position weights cannot exceed 100%")

        sector_weights: dict[str, float] = defaultdict(float)
        for position in existing_positions:
            sector_weights[position.sector.upper()] += position.weight

        available_slots = max(0, self.max_positions - len(existing_symbols))
        rejected: list[dict] = []
        eligible: list[PortfolioCandidate] = []

        for candidate in sorted(candidates, key=self._edge, reverse=True):
            symbol = candidate.symbol.upper()
            sector = candidate.sector.upper()

            if symbol in existing_symbols:
                rejected.append({"symbol": symbol, "reason": "Position already exists"})
                continue
            if candidate.score < self.min_score:
                rejected.append({"symbol": symbol, "reason": "Score below portfolio minimum"})
                continue
            if candidate.confidence < self.min_confidence:
                rejected.append({"symbol": symbol, "reason": "Confidence below portfolio minimum"})
                continue
            if len(eligible) >= available_slots:
                rejected.append({"symbol": symbol, "reason": "Maximum position count reached"})
                continue

            selected_symbols = existing_symbols | {item.symbol.upper() for item in eligible}
            correlated_with = None
            for other in selected_symbols:
                corr = self._correlation(symbol, other, correlations)
                if corr is not None and corr >= self.max_correlation:
                    correlated_with = (other, corr)
                    break
            if correlated_with is not None:
                other, corr = correlated_with
                rejected.append(
                    {
                        "symbol": symbol,
                        "reason": f"Correlation {corr:.2f} with {other} exceeds limit",
                    }
                )
                continue

            # Do not select a candidate if the sector has no remaining room.
            if sector_weights[sector] >= self.max_sector_weight:
                rejected.append({"symbol": symbol, "reason": "Sector exposure limit reached"})
                continue

            eligible.append(candidate)

        available_weight = max(0.0, 1.0 - existing_weight)
        total_edge = sum(max(self._edge(candidate), 0.0) for candidate in eligible)
        allocations: list[PortfolioAllocation] = []

        for candidate in eligible:
            symbol = candidate.symbol.upper()
            sector = candidate.sector.upper()
            if total_edge <= 0 or available_weight <= 0:
                rejected.append({"symbol": symbol, "reason": "No portfolio capacity"})
                continue

            raw_weight = available_weight * (self._edge(candidate) / total_edge)
            sector_room = max(0.0, self.max_sector_weight - sector_weights[sector])
            target_weight = min(raw_weight, self.max_symbol_weight, sector_room)

            if target_weight <= 0:
                rejected.append({"symbol": symbol, "reason": "No sector or symbol capacity"})
                continue

            sector_weights[sector] += target_weight
            allocations.append(
                PortfolioAllocation(
                    symbol=symbol,
                    target_weight=round(target_weight, 6),
                    target_value=round(capital * target_weight, 2),
                    score=candidate.score,
                    confidence=candidate.confidence,
                    sector=sector,
                    reason="Ranked by fused score/confidence within portfolio limits",
                )
            )

        allocated_weight = sum(item.target_weight for item in allocations)
        cash_weight = max(0.0, 1.0 - existing_weight - allocated_weight)
        return PortfolioPlan(
            allocations=tuple(allocations),
            rejected=tuple(rejected),
            existing_weight=round(existing_weight, 6),
            allocated_weight=round(allocated_weight, 6),
            cash_weight=round(cash_weight, 6),
            max_positions=self.max_positions,
        )
