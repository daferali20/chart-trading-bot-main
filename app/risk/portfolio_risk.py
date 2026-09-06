from __future__ import annotations

from dataclasses import dataclass

from app.analysis.regime import MarketRegime
from app.strategy.fusion import SignalDirection


@dataclass(frozen=True)
class PortfolioRiskPolicy:
    max_positions: int = 7
    max_portfolio_drawdown: float = 0.12
    max_sector_weight: float = 0.40
    max_correlation: float = 0.85
    min_dollar_volume: float = 5_000_000.0
    block_new_longs_in_risk_off: bool = True


@dataclass(frozen=True)
class PortfolioRiskContext:
    direction: SignalDirection
    regime: MarketRegime
    account_value: float
    peak_account_value: float
    active_positions: int
    sector_weight_after_trade: float
    max_candidate_correlation: float | None
    dollar_volume: float | None


@dataclass(frozen=True)
class PortfolioRiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    drawdown: float


class PortfolioRiskEngine:
    """Final portfolio-level policy check before the Execution Gate.

    This engine does not know how to send orders and does not query IBKR.
    Callers provide a snapshot of current portfolio/market state.
    """

    def __init__(self, policy: PortfolioRiskPolicy | None = None) -> None:
        self.policy = policy or PortfolioRiskPolicy()

    def evaluate(self, context: PortfolioRiskContext) -> PortfolioRiskDecision:
        if context.account_value <= 0:
            return PortfolioRiskDecision(False, ("Account value must be positive",), (), 0.0)
        if context.peak_account_value <= 0:
            return PortfolioRiskDecision(False, ("Peak account value must be positive",), (), 0.0)

        drawdown = max(
            0.0,
            (context.peak_account_value - context.account_value)
            / context.peak_account_value,
        )

        reasons: list[str] = []
        warnings: list[str] = []

        if context.active_positions >= self.policy.max_positions:
            reasons.append(
                f"Position limit reached: {context.active_positions}/{self.policy.max_positions}"
            )

        if drawdown >= self.policy.max_portfolio_drawdown:
            reasons.append(
                "Portfolio drawdown limit reached: "
                f"{drawdown:.2%} >= {self.policy.max_portfolio_drawdown:.2%}"
            )

        if context.sector_weight_after_trade > self.policy.max_sector_weight:
            reasons.append(
                "Sector exposure too high: "
                f"{context.sector_weight_after_trade:.2%} > {self.policy.max_sector_weight:.2%}"
            )

        if (
            context.max_candidate_correlation is not None
            and abs(context.max_candidate_correlation) >= self.policy.max_correlation
        ):
            reasons.append(
                "Correlation limit exceeded: "
                f"{abs(context.max_candidate_correlation):.2f} >= {self.policy.max_correlation:.2f}"
            )

        if context.dollar_volume is None:
            warnings.append("Dollar-volume data unavailable")
        elif context.dollar_volume < self.policy.min_dollar_volume:
            reasons.append(
                "Liquidity below minimum: "
                f"${context.dollar_volume:,.0f} < ${self.policy.min_dollar_volume:,.0f}"
            )

        if (
            self.policy.block_new_longs_in_risk_off
            and context.direction is SignalDirection.LONG
            and context.regime is MarketRegime.RISK_OFF
        ):
            reasons.append("New LONG positions are blocked in RISK_OFF regime")

        if context.regime is MarketRegime.HIGH_VOLATILITY:
            warnings.append("HIGH_VOLATILITY regime: consider smaller sizing / wider ATR logic")

        return PortfolioRiskDecision(
            allowed=not reasons,
            reasons=tuple(reasons) if reasons else ("OK",),
            warnings=tuple(warnings),
            drawdown=round(drawdown, 6),
        )


DEFAULT_PORTFOLIO_RISK_ENGINE = PortfolioRiskEngine()
