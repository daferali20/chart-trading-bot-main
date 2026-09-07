from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from app.strategy.wema5.strategy import WEMA5Signal, WEMA5Strategy
from backtest.wema5.replay import _trade_metrics, replay


class WEMA5ReplayExecutionTests(unittest.TestCase):
    @staticmethod
    def frame(rows: int = 40) -> pd.DataFrame:
        dates = pd.date_range("2026-01-01", periods=rows, freq="D")
        return pd.DataFrame(
            {
                "date": dates,
                "open": [100.0 + index for index in range(rows)],
                "high": [101.0 + index for index in range(rows)],
                "low": [99.0 + index for index in range(rows)],
                "close": [100.5 + index for index in range(rows)],
                "volume": [1_000_000] * rows,
            }
        )

    def test_entry_and_exit_execute_on_next_bar_open(self) -> None:
        data = self.frame()

        def fake_signal(self, df, index=None, in_position=False):
            if index == 12 and not in_position:
                return WEMA5Signal("BUY", "AAA", float(df.iloc[index]["close"]), "test buy")
            if index == 15 and in_position:
                return WEMA5Signal("SELL", "AAA", float(df.iloc[index]["close"]), "test sell")
            return None

        with patch.object(WEMA5Strategy, "generate_signal", autospec=True, side_effect=fake_signal):
            result = replay("AAA", data, days=30)

        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_signal_date"], data.iloc[12]["date"])
        self.assertEqual(trade["entry_date"], data.iloc[13]["date"])
        self.assertEqual(trade["entry_price"], float(data.iloc[13]["open"]))
        self.assertEqual(trade["exit_signal_date"], data.iloc[15]["date"])
        self.assertEqual(trade["execution_date"], data.iloc[16]["date"])
        self.assertEqual(trade["exit_price"], float(data.iloc[16]["open"]))

    def test_last_bar_buy_signal_is_not_filled_without_next_bar(self) -> None:
        data = self.frame()
        last_index = len(data) - 1

        def fake_signal(self, df, index=None, in_position=False):
            if index == last_index and not in_position:
                return WEMA5Signal("BUY", "AAA", float(df.iloc[index]["close"]), "late buy")
            return None

        with patch.object(WEMA5Strategy, "generate_signal", autospec=True, side_effect=fake_signal):
            result = replay("AAA", data, days=30)

        self.assertEqual(result["trades"], [])
        self.assertIsNone(result["open_position"])

    def test_trade_metrics_expose_concentration_and_drawdown(self) -> None:
        trades = [
            {"return": 0.10},
            {"return": -0.05},
            {"return": 0.20},
        ]

        metrics = _trade_metrics(trades)

        self.assertAlmostEqual(metrics["max_drawdown"], 0.05)
        self.assertAlmostEqual(metrics["trade_concentration"], 2.0 / 3.0)
        self.assertAlmostEqual(metrics["best_trade_return"], 0.20)
        self.assertAlmostEqual(metrics["compound_without_best_trade"], 0.045)


if __name__ == "__main__":
    unittest.main()
