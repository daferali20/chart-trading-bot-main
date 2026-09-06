from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Mapping, Sequence

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.portfolio.engine import PortfolioEngine
from app.portfolio.models import ExistingPosition, PortfolioCandidate, PortfolioPlan
from app.risk.portfolio_risk import (
    PortfolioRiskContext,
    PortfolioRiskDecision,
    PortfolioRiskEngine,
)
from app.strategy.signal_engine import SignalEngine, SignalInsight


@dataclass(frozen=True)
class OpportunityDecision:
    symbol: str
    insight: SignalInsight
    target_weight: float | None
    target_value: float | None
    risk: PortfolioRiskDecision | None
    status: str
    reason: str


@dataclass(frozen=True)
class DecisionBatch:
    opportunities: tuple[OpportunityDecision, ...]
    portfolio: PortfolioPlan
    analyzed_symbols: int
    buy_candidates: int
    ready_for_execution_gate: int


class DecisionPipeline:
    """End-to-end analysis pipeline that deliberately stops before execution.

    Flow:
        Market data -> Features/Alphas -> Signal Fusion -> Portfolio -> Risk

    Output status ``READY_FOR_EXECUTION_GATE`` means only that analysis,
    portfolio construction, and portfolio-level risk checks passed. It does
    NOT place an order. The existing ExecutionGate remains the final live
    authority when/if this pipeline is later wired into trading.
    """

    def __init__(
        self,
        *,
        signal_engine: SignalEngine | None = None,
        portfolio_engine: PortfolioEngine | None = None,
        risk_engine: PortfolioRiskEngine | None = None,
    ) -> None:
        self.signal_engine = signal_engine or SignalEngine()
        self.portfolio_engine = portfolio_engine or PortfolioEngine()
        self.risk_engine = risk_engine or PortfolioRiskEngine()

    @staticmethod
    def _latest_dollar_volume(df: pd.DataFrame) -> float | None:
        try:
            features = DEFAULT_FEATURE_ENGINE.build(df)
            value = features.iloc[-1].get("dollar_volume")
            if value is None or pd.isna(value):
                return None
            return float(value)
        except (ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _max_correlation(
        symbol: str,
        selected_symbols: Sequence[str],
        correlations: Mapping[tuple[str, str], float] | None,
    ) -> float | None:
        if not correlations or not selected_symbols:
            return None

        normalized_correlations = {
            (left.upper(), right.upper()): float(value)
            for (left, right), value in correlations.items()
        }
        values: list[float] = []
        symbol = symbol.upper()
        for other in selected_symbols:
            other = other.upper()
            if (symbol, other) in normalized_correlations:
                values.append(abs(normalized_correlations[(symbol, other)]))
            elif (other, symbol) in normalized_correlations:
                values.append(abs(normalized_correlations[(other, symbol)]))
        return max(values) if values else None

    def evaluate(
        self,
        symbol_data: Mapping[str, pd.DataFrame],
        *,
        market_df: pd.DataFrame | None,
        capital: float,
        peak_account_value: float,
        sectors: Mapping[str, str] | None = None,
        existing_positions: Sequence[ExistingPosition] = (),
        correlations: Mapping[tuple[str, str], float] | None = None,
        mtf_frames: Mapping[str, Mapping[str, pd.DataFrame]] | None = None,
    ) -> DecisionBatch:
        if capital <= 0:
            raise ValueError("capital must be positive")
        if peak_account_value <= 0:
            raise ValueError("peak_account_value must be positive")
        if not symbol_data:
            raise ValueError("symbol_data is empty")

        normalized_data = {symbol.upper(): df for symbol, df in symbol_data.items()}
        sectors = {key.upper(): value for key, value in (sectors or {}).items()}
        normalized_mtf = {
            symbol.upper(): frames
            for symbol, frames in (mtf_frames or {}).items()
        }

        insights: dict[str, SignalInsight] = {}
        candidates: list[PortfolioCandidate] = []

        for symbol, df in normalized_data.items():
            insight = self.signal_engine.analyze(
                df,
                market_df=market_df,
                mtf_frames=normalized_mtf.get(symbol),
            )
            insights[symbol] = insight

            if insight.action == "BUY":
                candidates.append(
                    PortfolioCandidate(
                        symbol=symbol,
                        score=insight.score,
                        confidence=insight.confidence,
                        sector=sectors.get(symbol, "UNKNOWN"),
                        expected_pct=insight.expected_pct,
                    )
                )

        portfolio = self.portfolio_engine.construct(
            candidates,
            capital=capital,
            existing_positions=existing_positions,
            correlations=correlations,
        )

        allocations = {item.symbol: item for item in portfolio.allocations}
        rejected = {
            item["symbol"]: item["reason"]
            for item in portfolio.rejected
            if "symbol" in item and "reason" in item
        }

        sector_weights: dict[str, float] = defaultdict(float)
        selected_symbols = [position.symbol.upper() for position in existing_positions]
        for position in existing_positions:
            sector_weights[position.sector.upper()] += position.weight

        decisions: list[OpportunityDecision] = []
        ready_count = 0

        for symbol, insight in insights.items():
            allocation = allocations.get(symbol)

            if insight.action != "BUY":
                decisions.append(
                    OpportunityDecision(
                        symbol=symbol,
                        insight=insight,
                        target_weight=None,
                        target_value=None,
                        risk=None,
                        status="NO_BUY_SIGNAL",
                        reason=f"Signal engine action is {insight.action}",
                    )
                )
                continue

            if allocation is None:
                decisions.append(
                    OpportunityDecision(
                        symbol=symbol,
                        insight=insight,
                        target_weight=None,
                        target_value=None,
                        risk=None,
                        status="PORTFOLIO_REJECTED",
                        reason=rejected.get(symbol, "Not selected by portfolio engine"),
                    )
                )
                continue

            sector = allocation.sector.upper()
            sector_weight_after = sector_weights[sector] + allocation.target_weight
            max_correlation = self._max_correlation(
                symbol,
                selected_symbols,
                correlations,
            )
            risk = self.risk_engine.evaluate(
                PortfolioRiskContext(
                    direction=insight.direction,
                    regime=insight.regime,
                    account_value=capital,
                    peak_account_value=peak_account_value,
                    active_positions=len(selected_symbols),
                    sector_weight_after_trade=sector_weight_after,
                    max_candidate_correlation=max_correlation,
                    dollar_volume=self._latest_dollar_volume(normalized_data[symbol]),
                )
            )

            if risk.allowed:
                status = "READY_FOR_EXECUTION_GATE"
                reason = "Signal, portfolio and risk checks passed"
                ready_count += 1
                selected_symbols.append(symbol)
                sector_weights[sector] = sector_weight_after
            else:
                status = "RISK_BLOCKED"
                reason = "; ".join(risk.reasons)

            decisions.append(
                OpportunityDecision(
                    symbol=symbol,
                    insight=insight,
                    target_weight=allocation.target_weight,
                    target_value=allocation.target_value,
                    risk=risk,
                    status=status,
                    reason=reason,
                )
            )

        return DecisionBatch(
            opportunities=tuple(decisions),
            portfolio=portfolio,
            analyzed_symbols=len(insights),
            buy_candidates=len(candidates),
            ready_for_execution_gate=ready_count,
        )


DEFAULT_DECISION_PIPELINE = DecisionPipeline()
