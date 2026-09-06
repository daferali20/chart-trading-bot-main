from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioCandidate:
    symbol: str
    score: float
    confidence: float
    sector: str = "UNKNOWN"
    expected_pct: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not 0.0 <= self.score <= 100.0:
            raise ValueError("score must be between 0 and 100")
        if not 0.0 <= self.confidence <= 100.0:
            raise ValueError("confidence must be between 0 and 100")


@dataclass(frozen=True)
class ExistingPosition:
    symbol: str
    weight: float
    sector: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError("weight must be between 0 and 1")


@dataclass(frozen=True)
class PortfolioAllocation:
    symbol: str
    target_weight: float
    target_value: float
    score: float
    confidence: float
    sector: str
    reason: str


@dataclass(frozen=True)
class PortfolioPlan:
    allocations: tuple[PortfolioAllocation, ...]
    rejected: tuple[dict, ...]
    existing_weight: float
    allocated_weight: float
    cash_weight: float
    max_positions: int
