from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.analysis.regime import MarketRegime, RegimeSnapshot
from app.strategy.adaptive_engine import AdaptiveSignalEngine


class AdaptiveSignalEngineTests(unittest.TestCase):
    @staticmethod
    def frame(rows: int = 260) -> pd.DataFrame:
        close = np.linspace(100.0, 130.0, rows) + np.sin(np.arange(rows) / 6.0)
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=rows, freq="D"),
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": [1_000_000.0] * rows,
            }
        )

    @staticmethod
    def snapshot(regime: MarketRegime) -> RegimeSnapshot:
        return RegimeSnapshot(
            regime=regime,
            confidence=90.0,
            reasons=(f"test {regime.value}",),
            metrics={},
        )

    def test_sideways_excludes_research_models_by_default(self) -> None:
        engine = AdaptiveSignalEngine(include_research=False)
        with patch(
            "app.strategy.adaptive_engine.DEFAULT_REGIME_ENGINE.classify",
            return_value=self.snapshot(MarketRegime.SIDEWAYS),
        ):
            result = engine.analyze(self.frame(), market_df=self.frame())

        self.assertIn("WEMA5_BASELINE_v1", result.selected_model_names)
        self.assertIn("VolumeAlpha", result.selected_model_names)
        self.assertNotIn("MeanReversionAlpha", result.selected_model_names)
        self.assertFalse(result.research_models_included)

    def test_research_mode_can_include_mean_reversion_without_promoting_it(self) -> None:
        engine = AdaptiveSignalEngine(include_research=True)
        with patch(
            "app.strategy.adaptive_engine.DEFAULT_REGIME_ENGINE.classify",
            return_value=self.snapshot(MarketRegime.SIDEWAYS),
        ):
            result = engine.analyze(self.frame(), market_df=self.frame())

        self.assertIn("MeanReversionAlpha", result.selected_model_names)
        self.assertIn("MeanReversionAlpha", result.selection.research_names)
        self.assertNotIn("MeanReversionAlpha", result.selection.active_names)

    def test_risk_off_with_no_approved_family_returns_hold(self) -> None:
        engine = AdaptiveSignalEngine(include_research=False)
        with patch(
            "app.strategy.adaptive_engine.DEFAULT_REGIME_ENGINE.classify",
            return_value=self.snapshot(MarketRegime.RISK_OFF),
        ):
            result = engine.analyze(self.frame(), market_df=self.frame())

        self.assertEqual(result.selected_model_names, ())
        self.assertEqual(result.insight.action, "HOLD")
        self.assertEqual(result.insight.score, 0.0)
        self.assertTrue(
            any("No approved alpha family" in reason for reason in result.insight.reasons)
        )


if __name__ == "__main__":
    unittest.main()
