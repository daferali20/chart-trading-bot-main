from __future__ import annotations

import unittest

from app.analysis.regime import MarketRegime
from app.strategy.selector import StrategySelector


class StrategySelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selector = StrategySelector()

    def test_bull_prefers_declared_bull_active_strategies(self) -> None:
        selection = self.selector.select(MarketRegime.BULL)
        self.assertIn("MomentumAlpha", selection.active_names)
        self.assertIn("TrendAlpha", selection.active_names)
        self.assertIn("BreakoutAlpha", selection.active_names)
        self.assertNotIn("MeanReversionAlpha", selection.active_names)
        self.assertIn("VolatilityExpansionAlpha", selection.research_names)

    def test_sideways_routes_mean_reversion_to_research_only(self) -> None:
        selection = self.selector.select(MarketRegime.SIDEWAYS)
        self.assertIn("WEMA5_BASELINE_v1", selection.active_names)
        self.assertIn("VolumeAlpha", selection.active_names)
        self.assertIn("MeanReversionAlpha", selection.research_names)
        self.assertNotIn("MeanReversionAlpha", selection.active_names)

    def test_high_volatility_keeps_research_strategy_separate(self) -> None:
        selection = self.selector.select(MarketRegime.HIGH_VOLATILITY)
        self.assertIn("BreakoutAlpha", selection.active_names)
        self.assertIn("VolatilityExpansionAlpha", selection.research_names)
        self.assertNotIn("VolatilityExpansionAlpha", selection.active_names)

    def test_unknown_regime_does_not_promote_research(self) -> None:
        selection = self.selector.select(MarketRegime.UNKNOWN)
        self.assertIn("MomentumAlpha", selection.active_names)
        self.assertIn("MeanReversionAlpha", selection.research_names)
        self.assertNotIn("MeanReversionAlpha", selection.active_names)


if __name__ == "__main__":
    unittest.main()
