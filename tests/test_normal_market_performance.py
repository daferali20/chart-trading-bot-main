from __future__ import annotations

import unittest

from app.research.agent.coordinator import (
    ResearchAgentCoordinator,
    ResearchApprovalPolicy,
)
from app.research.scoring.normal_market import NormalMarketPerformanceAnalyzer


class NormalMarketPerformanceTests(unittest.TestCase):
    def test_analyzer_separates_normal_and_event_returns(self) -> None:
        analyzer = NormalMarketPerformanceAnalyzer()
        result = analyzer.analyze(
            [
                {"return_pct": 2.0, "classification": "NORMAL"},
                {"return_pct": -1.0, "classification": "NORMAL"},
                {"return_pct": 1.5, "classification": "NORMAL"},
                {"return_pct": 12.0, "classification": "EVENT_RELATED"},
                {"return_pct": -3.0, "classification": "EVENT_RELATED"},
            ]
        )

        self.assertEqual(result.normal_trade_count, 3)
        self.assertEqual(result.event_trade_count, 2)
        self.assertGreater(result.normal_return, 0.0)
        self.assertGreater(result.normal_profit_factor, 1.0)
        self.assertGreater(result.event_profit_share, 0.5)

    def test_event_driven_candidate_is_rejected_when_metrics_are_present(self) -> None:
        coordinator = object.__new__(ResearchAgentCoordinator)
        coordinator.policy = ResearchApprovalPolicy(
            min_normal_trade_count=10,
            min_normal_return=0.0,
            min_normal_profit_factor=1.20,
            max_event_profit_share=0.60,
        )
        reasons = coordinator._normal_market_reasons(
            {
                "normal_trade_count": 20.0,
                "normal_return": -3.0,
                "normal_profit_factor": 0.90,
                "event_profit_share": 0.85,
            }
        )

        self.assertTrue(any("Normal-market OOS return" in reason for reason in reasons))
        self.assertTrue(any("profit factor" in reason for reason in reasons))
        self.assertTrue(any("event-driven" in reason for reason in reasons))

    def test_repeatable_normal_market_candidate_passes_gate(self) -> None:
        coordinator = object.__new__(ResearchAgentCoordinator)
        coordinator.policy = ResearchApprovalPolicy(
            min_normal_trade_count=10,
            min_normal_return=0.0,
            min_normal_profit_factor=1.20,
            max_event_profit_share=0.60,
        )
        reasons = coordinator._normal_market_reasons(
            {
                "normal_trade_count": 25.0,
                "normal_return": 8.5,
                "normal_profit_factor": 1.65,
                "event_profit_share": 0.25,
            }
        )
        self.assertEqual(reasons, [])

    def test_legacy_metrics_do_not_trigger_incomplete_event_gate(self) -> None:
        coordinator = object.__new__(ResearchAgentCoordinator)
        coordinator.policy = ResearchApprovalPolicy()
        self.assertEqual(
            coordinator._normal_market_reasons(
                {
                    "return": 0.12,
                    "profit_factor": 1.5,
                    "win_rate": 0.55,
                    "max_drawdown": 0.10,
                }
            ),
            [],
        )

    def test_partial_event_metrics_are_rejected_as_incomplete(self) -> None:
        coordinator = object.__new__(ResearchAgentCoordinator)
        coordinator.policy = ResearchApprovalPolicy()
        reasons = coordinator._normal_market_reasons(
            {
                "normal_return": 5.0,
                "normal_profit_factor": 1.4,
            }
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("Incomplete normal-market OOS evidence", reasons[0])


if __name__ == "__main__":
    unittest.main()
