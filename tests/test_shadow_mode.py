from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.regime import MarketRegime
from app.shadow import ShadowEvaluator
from app.strategy.fusion import SignalDirection
from app.strategy.signal_engine import SignalInsight


class FakeAdvancedEngine:
    def analyze(self, df, *, market_df=None, mtf_frames=None):
        return SignalInsight(
            action="BUY",
            direction=SignalDirection.LONG,
            score=78.0,
            confidence=82.0,
            quality=88.0,
            expected_pct=4.5,
            horizon="10-20D",
            regime=MarketRegime.BULL,
            regime_confidence=90.0,
            entry=float(df.iloc[-1]["close"]),
            alphas=(),
            contributions=(),
            reasons=("Advanced test reason",),
        )


class ShadowModeTests(unittest.TestCase):
    @staticmethod
    def frame(rows: int = 100) -> pd.DataFrame:
        index = np.arange(rows, dtype=float)
        close = 50.0 + (index * 0.20) + np.sin(index / 4.0)
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h"),
                "open": close - 0.10,
                "high": close + 0.40,
                "low": close - 0.40,
                "close": close,
                "volume": np.full(rows, 250_000.0),
            }
        )

    def test_compare_returns_both_legacy_and_advanced_results(self) -> None:
        evaluator = ShadowEvaluator(advanced_engine=FakeAdvancedEngine())
        result = evaluator.compare("aaa", self.frame())

        self.assertEqual(result.symbol, "AAA")
        self.assertIn(result.legacy_action, {"BUY", "HOLD"})
        self.assertEqual(result.advanced_action, "BUY")
        self.assertEqual(result.advanced_score, 78.0)
        self.assertEqual(result.market_regime, "BULL")
        self.assertIsInstance(result.agreement, bool)

    def test_shadow_log_is_append_only_jsonl(self) -> None:
        evaluator = ShadowEvaluator(advanced_engine=FakeAdvancedEngine())
        result = evaluator.compare("AAA", self.frame())

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shadow.jsonl"
            evaluator.append_log(result, path)
            evaluator.append_log(result, path)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            first = json.loads(lines[0])
            self.assertEqual(first["symbol"], "AAA")
            self.assertEqual(first["advanced_action"], "BUY")


if __name__ == "__main__":
    unittest.main()
