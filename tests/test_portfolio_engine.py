from __future__ import annotations

import unittest

from app.portfolio.engine import PortfolioEngine
from app.portfolio.models import ExistingPosition, PortfolioCandidate


class PortfolioEngineTests(unittest.TestCase):
    def test_ranks_and_respects_position_limit(self) -> None:
        engine = PortfolioEngine(max_positions=2, max_symbol_weight=0.60, max_sector_weight=1.0)
        plan = engine.construct(
            [
                PortfolioCandidate("AAA", 90, 90, "TECH"),
                PortfolioCandidate("BBB", 80, 80, "FIN"),
                PortfolioCandidate("CCC", 70, 70, "HEALTH"),
            ],
            capital=100_000,
        )
        self.assertEqual([item.symbol for item in plan.allocations], ["AAA", "BBB"])
        self.assertTrue(any(item["symbol"] == "CCC" for item in plan.rejected))

    def test_existing_position_consumes_slot_and_weight(self) -> None:
        engine = PortfolioEngine(max_positions=2, max_symbol_weight=0.50, max_sector_weight=1.0)
        plan = engine.construct(
            [
                PortfolioCandidate("AAA", 95, 90, "TECH"),
                PortfolioCandidate("BBB", 85, 85, "FIN"),
            ],
            capital=100_000,
            existing_positions=(ExistingPosition("XYZ", 0.40, "ENERGY"),),
        )
        self.assertEqual(len(plan.allocations), 1)
        self.assertLessEqual(plan.allocated_weight, 0.50)
        self.assertAlmostEqual(plan.existing_weight, 0.40)

    def test_sector_limit_caps_allocation(self) -> None:
        engine = PortfolioEngine(max_positions=3, max_symbol_weight=0.50, max_sector_weight=0.40)
        plan = engine.construct(
            [
                PortfolioCandidate("AAA", 95, 95, "TECH"),
                PortfolioCandidate("BBB", 90, 90, "TECH"),
                PortfolioCandidate("CCC", 80, 80, "FIN"),
            ],
            capital=100_000,
        )
        tech_weight = sum(item.target_weight for item in plan.allocations if item.sector == "TECH")
        self.assertLessEqual(tech_weight, 0.40 + 1e-9)

    def test_high_correlation_rejects_candidate(self) -> None:
        engine = PortfolioEngine(max_positions=3, max_symbol_weight=0.50, max_sector_weight=1.0, max_correlation=0.85)
        plan = engine.construct(
            [
                PortfolioCandidate("AAA", 95, 95, "TECH"),
                PortfolioCandidate("BBB", 90, 90, "TECH"),
                PortfolioCandidate("CCC", 80, 80, "FIN"),
            ],
            capital=100_000,
            correlations={
                ("AAA", "BBB"): 0.92,
                ("AAA", "CCC"): 0.30,
            },
        )
        symbols = {item.symbol for item in plan.allocations}
        self.assertIn("AAA", symbols)
        self.assertNotIn("BBB", symbols)
        self.assertTrue(
            any(
                item["symbol"] == "BBB" and "Correlation" in item["reason"]
                for item in plan.rejected
            )
        )


if __name__ == "__main__":
    unittest.main()
