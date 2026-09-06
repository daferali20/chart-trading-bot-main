from __future__ import annotations

import unittest

from app.analysis.regime import MarketRegime
from app.risk.portfolio_risk import (
    PortfolioRiskContext,
    PortfolioRiskEngine,
    PortfolioRiskPolicy,
)
from app.strategy.fusion import SignalDirection


class PortfolioRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PortfolioRiskEngine(
            PortfolioRiskPolicy(
                max_positions=7,
                max_portfolio_drawdown=0.12,
                max_sector_weight=0.40,
                max_correlation=0.85,
                min_dollar_volume=5_000_000.0,
            )
        )

    def test_normal_context_is_allowed(self) -> None:
        decision = self.engine.evaluate(
            PortfolioRiskContext(
                direction=SignalDirection.LONG,
                regime=MarketRegime.BULL,
                account_value=98_000,
                peak_account_value=100_000,
                active_positions=3,
                sector_weight_after_trade=0.30,
                max_candidate_correlation=0.50,
                dollar_volume=20_000_000,
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ("OK",))

    def test_drawdown_limit_blocks_new_risk(self) -> None:
        decision = self.engine.evaluate(
            PortfolioRiskContext(
                direction=SignalDirection.LONG,
                regime=MarketRegime.BULL,
                account_value=85_000,
                peak_account_value=100_000,
                active_positions=2,
                sector_weight_after_trade=0.20,
                max_candidate_correlation=0.30,
                dollar_volume=20_000_000,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("drawdown" in reason.lower() for reason in decision.reasons))

    def test_risk_off_blocks_new_long(self) -> None:
        decision = self.engine.evaluate(
            PortfolioRiskContext(
                direction=SignalDirection.LONG,
                regime=MarketRegime.RISK_OFF,
                account_value=100_000,
                peak_account_value=100_000,
                active_positions=1,
                sector_weight_after_trade=0.20,
                max_candidate_correlation=0.30,
                dollar_volume=20_000_000,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("RISK_OFF" in reason for reason in decision.reasons))

    def test_liquidity_and_correlation_can_block(self) -> None:
        decision = self.engine.evaluate(
            PortfolioRiskContext(
                direction=SignalDirection.LONG,
                regime=MarketRegime.SIDEWAYS,
                account_value=100_000,
                peak_account_value=100_000,
                active_positions=1,
                sector_weight_after_trade=0.20,
                max_candidate_correlation=0.92,
                dollar_volume=1_000_000,
            )
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("Correlation" in reason for reason in decision.reasons))
        self.assertTrue(any("Liquidity" in reason for reason in decision.reasons))

    def test_high_volatility_adds_warning_not_automatic_block(self) -> None:
        decision = self.engine.evaluate(
            PortfolioRiskContext(
                direction=SignalDirection.LONG,
                regime=MarketRegime.HIGH_VOLATILITY,
                account_value=100_000,
                peak_account_value=100_000,
                active_positions=1,
                sector_weight_after_trade=0.20,
                max_candidate_correlation=0.30,
                dollar_volume=20_000_000,
            )
        )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.warnings)


if __name__ == "__main__":
    unittest.main()
