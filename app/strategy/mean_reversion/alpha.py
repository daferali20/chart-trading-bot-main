from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class MeanReversionAlpha(AlphaModel):
    """Look for stretched pullbacks/rebounds rather than trend continuation.

    This model deliberately uses a different edge family from momentum/trend:
    it seeks temporary dislocations where price is extended from MA35 by ATR
    while oscillators are extreme.
    """

    name = "MeanReversionAlpha"
    version = "v1"
    required_features = ("close", "ma35", "atr14", "rsi14", "williams_r")

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        if any(pd.isna(row[column]) for column in self.required_features):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Mean-reversion features not ready")

        close = float(row["close"])
        ma35 = float(row["ma35"])
        atr = float(row["atr14"])
        rsi = float(row["rsi14"])
        williams = float(row["williams_r"])
        if atr <= 0:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="ATR not ready")

        stretch_atr = (close - ma35) / atr

        if stretch_atr <= -1.25 and rsi <= 38.0 and williams <= -80.0:
            confidence = min(0.92, 0.60 + min(abs(stretch_atr), 3.0) * 0.08)
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=0.80,
                weight=0.9,
                horizon="2-10D",
                reason=f"Oversold pullback {stretch_atr:.2f} ATR below MA35; RSI={rsi:.1f}",
            )

        if stretch_atr >= 1.50 and rsi >= 70.0 and williams >= -20.0:
            confidence = min(0.90, 0.58 + min(abs(stretch_atr), 3.0) * 0.08)
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=0.76,
                weight=0.85,
                horizon="2-10D",
                reason=f"Overbought extension {stretch_atr:.2f} ATR above MA35; RSI={rsi:.1f}",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.40,
            quality=0.68,
            weight=0.75,
            horizon="2-10D",
            reason="No statistically meaningful mean-reversion stretch",
        )
