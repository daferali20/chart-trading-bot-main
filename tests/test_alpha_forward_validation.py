from __future__ import annotations

import unittest

import pandas as pd

from app.research.validation.alpha_forward import AlphaForwardValidator
from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class TestAlpha(AlphaModel):
    name = "TestAlpha"
    version = "v1"
    required_features = ("close",)

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        close = float(df.iloc[-1]["close"])
        if close > 100.0:
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                0.8,
                quality=0.8,
                weight=1.0,
            )
        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.0,
        )


class AlphaForwardValidatorTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=7, freq="D"),
                "open": [100.0, 101.0, 102.0, 104.0, 103.0, 105.0, 106.0],
                "high": [101.0, 103.0, 104.0, 105.0, 104.0, 107.0, 108.0],
                "low": [99.0, 100.0, 101.0, 102.0, 99.0, 104.0, 105.0],
                "close": [100.0, 102.0, 103.0, 100.0, 99.0, 106.0, 107.0],
                "volume": [1_000_000.0] * 7,
            }
        )

    def test_consecutive_same_direction_is_one_episode(self) -> None:
        result = AlphaForwardValidator(horizons=(1,), deduplicate_episodes=True).validate(
            TestAlpha(),
            self.frame(),
        )
        # Directional closes at indexes 1,2 and 5,6. The final episode has no
        # next bar for index 6, but it is still a detected directional signal.
        self.assertEqual(result.raw_directional_signals, 4)
        self.assertEqual(result.independent_signal_episodes, 2)
        self.assertEqual(result.summaries[0].samples, 2)

    def test_entry_is_next_bar_open_not_signal_close(self) -> None:
        result = AlphaForwardValidator(horizons=(1,), deduplicate_episodes=True).validate(
            TestAlpha(),
            self.frame(),
        )
        first = result.observations[0]
        self.assertEqual(first.signal_date[:10], "2026-01-02")
        self.assertEqual(first.entry_date[:10], "2026-01-03")
        self.assertAlmostEqual(first.entry_price, 102.0)
        self.assertAlmostEqual(first.exit_price, 103.0)
        self.assertAlmostEqual(first.raw_return_pct, (103.0 / 102.0 - 1.0) * 100.0)

    def test_without_episode_deduplication_counts_each_directional_bar(self) -> None:
        result = AlphaForwardValidator(horizons=(1,), deduplicate_episodes=False).validate(
            TestAlpha(),
            self.frame(),
        )
        # Last directional bar has no next-bar execution and therefore cannot
        # become an observation.
        self.assertEqual(result.raw_directional_signals, 4)
        self.assertEqual(result.independent_signal_episodes, 4)
        self.assertEqual(result.summaries[0].samples, 3)


if __name__ == "__main__":
    unittest.main()
