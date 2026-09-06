from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.regime import MarketRegime
from app.pipeline import DecisionPipeline
from app.portfolio.engine import PortfolioEngine
from app.risk.portfolio_risk import PortfolioRiskEngine, PortfolioRiskPolicy
from app.strategy.fusion import SignalDirection
from app.strategy.signal_engine import SignalInsight


class FakeSignalEngine:
    def __init__(self, insights: dict[str, SignalInsight]) -> None:
        self.insights = insights
        self.calls = 0

    def analyze(self, df, *, market_df=None, mtf_frames=None):
        symbol = str(df.attrs["symbol"]).upper()
        self.calls += 1
        return self.insights[symbol]


class DecisionPipelineTests(unittest.TestCase):
    @staticmethod
    def data(symbol: str, close: float = 100.0, volume: float = 200_000.0) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=30, freq="D"),
                "open": [close - 0.25] * 30,
                "high": [close + 0.50] * 30,
                "low": [close - 0.50] * 30,
                "close": [close] * 30,
                "volume": [volume] * 30,
            }
        )
        frame.attrs["symbol"] = symbol
        return frame

    @staticmethod
    def insight(
        *,
        action: str = "BUY",
        score: float = 80.0,
        confidence: float = 80.0,
        regime: MarketRegime = MarketRegime.BULL,
    ) -> SignalInsight:
        return SignalInsight(
            action=action,
            direction=(SignalDirection.LONG if action == "BUY" else SignalDirection.NEUTRAL),
            score=score,
            confidence=confidence,
            quality=85.0,
            expected_pct=4.0,
            horizon="10-20D",
            regime=regime,
            regime_confidence=90.0,
            entry=100.0,
            alphas=(),
            contributions=(),
            reasons=("test",),
        )

    def test_ready_status_stops_before_execution_gate(self) -> None:
        fake = FakeSignalEngine({"AAA": self.insight()})
        pipeline = DecisionPipeline(
            signal_engine=fake,
            portfolio_engine=PortfolioEngine(
                max_positions=7,
                max_symbol_weight=0.25,
                max_sector_weight=0.40,
            ),
            risk_engine=PortfolioRiskEngine(
                PortfolioRiskPolicy(min_dollar_volume=5_000_000.0)
            ),
        )

        batch = pipeline.evaluate(
            {"aaa": self.data("AAA")},
            market_df=None,
            capital=100_000.0,
            peak_account_value=100_000.0,
            sectors={"aaa": "TECH"},
        )

        self.assertEqual(batch.analyzed_symbols, 1)
        self.assertEqual(batch.buy_candidates, 1)
        self.assertEqual(batch.ready_for_execution_gate, 1)
        decision = batch.opportunities[0]
        self.assertEqual(decision.symbol, "AAA")
        self.assertEqual(decision.status, "READY_FOR_EXECUTION_GATE")
        self.assertTrue(decision.risk and decision.risk.allowed)
        self.assertIsNotNone(decision.target_value)

    def test_drawdown_blocks_before_execution_gate(self) -> None:
        fake = FakeSignalEngine({"AAA": self.insight()})
        pipeline = DecisionPipeline(signal_engine=fake)

        batch = pipeline.evaluate(
            {"AAA": self.data("AAA")},
            market_df=None,
            capital=80_000.0,
            peak_account_value=100_000.0,
            sectors={"AAA": "TECH"},
        )

        decision = batch.opportunities[0]
        self.assertEqual(decision.status, "RISK_BLOCKED")
        self.assertEqual(batch.ready_for_execution_gate, 0)
        self.assertTrue(any("drawdown" in reason.lower() for reason in decision.risk.reasons))

    def test_non_buy_signal_never_enters_portfolio(self) -> None:
        fake = FakeSignalEngine(
            {"AAA": self.insight(action="HOLD", score=45.0, confidence=55.0)}
        )
        pipeline = DecisionPipeline(signal_engine=fake)

        batch = pipeline.evaluate(
            {"AAA": self.data("AAA")},
            market_df=None,
            capital=100_000.0,
            peak_account_value=100_000.0,
        )

        self.assertEqual(batch.buy_candidates, 0)
        self.assertEqual(batch.ready_for_execution_gate, 0)
        self.assertEqual(batch.opportunities[0].status, "NO_BUY_SIGNAL")
        self.assertEqual(len(batch.portfolio.allocations), 0)

    def test_position_limit_can_reject_candidate_at_portfolio_layer(self) -> None:
        fake = FakeSignalEngine(
            {
                "AAA": self.insight(score=90.0),
                "BBB": self.insight(score=80.0),
            }
        )
        pipeline = DecisionPipeline(
            signal_engine=fake,
            portfolio_engine=PortfolioEngine(
                max_positions=1,
                max_symbol_weight=1.0,
                max_sector_weight=1.0,
            ),
        )

        batch = pipeline.evaluate(
            {
                "AAA": self.data("AAA"),
                "BBB": self.data("BBB"),
            },
            market_df=None,
            capital=100_000.0,
            peak_account_value=100_000.0,
            sectors={"AAA": "TECH", "BBB": "FIN"},
        )

        statuses = {item.symbol: item.status for item in batch.opportunities}
        self.assertEqual(statuses["AAA"], "READY_FOR_EXECUTION_GATE")
        self.assertEqual(statuses["BBB"], "PORTFOLIO_REJECTED")
        self.assertEqual(batch.ready_for_execution_gate, 1)


if __name__ == "__main__":
    unittest.main()
