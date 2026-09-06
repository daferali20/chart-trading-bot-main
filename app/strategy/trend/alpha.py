from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class TrendAlpha(AlphaModel):
    name = "TrendAlpha"
    version = "v1"
    required_features = ("close", "ema10", "ma35", "ma50", "ma200")

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        required = [row[column] for column in self.required_features]
        if any(pd.isna(value) for value in required):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Trend features not ready")

        close = float(row["close"])
        ema10 = float(row["ema10"])
        ma35 = float(row["ma35"])
        ma50 = float(row["ma50"])
        ma200 = float(row["ma200"])

        bull_votes = sum((close > ema10, close > ma35, ma35 > ma50, close > ma200))
        bear_votes = sum((close < ema10, close < ma35, ma35 < ma50, close < ma200))

        if bull_votes >= 3 and bull_votes > bear_votes:
            confidence = min(0.95, 0.50 + (0.11 * bull_votes))
            quality = 0.95 if bull_votes == 4 else 0.82
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=quality,
                weight=1.1,
                horizon="10-30D",
                reason=f"Bullish trend alignment {bull_votes}/4",
            )

        if bear_votes >= 3 and bear_votes > bull_votes:
            confidence = min(0.95, 0.50 + (0.11 * bear_votes))
            quality = 0.95 if bear_votes == 4 else 0.82
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=quality,
                weight=1.1,
                horizon="10-30D",
                reason=f"Bearish trend alignment {bear_votes}/4",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.45,
            quality=0.70,
            weight=0.9,
            horizon="10-30D",
            reason="Trend structure is mixed",
        )
