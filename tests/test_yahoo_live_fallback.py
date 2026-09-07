import unittest

import pandas as pd

from app.ui_worker2 import prepare_yahoo_live_frame, yahoo_fallback_spec


class YahooLiveFallbackTests(unittest.TestCase):
    def test_10_minute_timeframe_uses_5m_yahoo_and_resamples(self):
        period, interval, rule = yahoo_fallback_spec("10 mins")
        self.assertEqual(period, "1mo")
        self.assertEqual(interval, "5m")
        self.assertEqual(rule, "10min")

    def test_10_minute_resample_preserves_ohlcv_semantics(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2026-09-04 09:30:00",
                        "2026-09-04 09:35:00",
                        "2026-09-04 09:40:00",
                        "2026-09-04 09:45:00",
                    ]
                ),
                "open": [10.0, 10.5, 11.0, 11.4],
                "high": [10.7, 11.2, 11.6, 12.0],
                "low": [9.8, 10.3, 10.8, 11.2],
                "close": [10.5, 11.0, 11.4, 11.8],
                "volume": [100, 150, 200, 250],
            }
        )

        result = prepare_yahoo_live_frame(frame, "10min")

        self.assertEqual(len(result), 2)
        first = result.iloc[0]
        self.assertEqual(float(first["open"]), 10.0)
        self.assertEqual(float(first["high"]), 11.2)
        self.assertEqual(float(first["low"]), 9.8)
        self.assertEqual(float(first["close"]), 11.0)
        self.assertEqual(float(first["volume"]), 250.0)
        self.assertIn("timestamp", result.columns)

    def test_daily_fallback_uses_long_history_without_resampling(self):
        period, interval, rule = yahoo_fallback_spec("1 day")
        self.assertEqual((period, interval, rule), ("5y", "1d", None))


if __name__ == "__main__":
    unittest.main()
