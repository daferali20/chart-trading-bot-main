from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class BreakoutAlpha(AlphaModel):
    name = "BreakoutAlpha"
    version = "v1"
    required_features = ("close", "breakout_high", "breakout_low", "atr14")

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        if any(pd.isna(row[column]) for column in self.required_features):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Breakout features not ready")

        close = float(row["close"])
        high = float(row["breakout_high"])
        low = float(row["breakout_low"])
        atr = float(row["atr14"])
        if atr <= 0:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="ATR not ready")

        if close > high:
            extension_atr = (close - high) / atr
            confidence = min(0.95, 0.68 + min(max(extension_atr, 0.0), 1.5) * 0.12)
            quality = 0.90 if extension_atr <= 1.0 else 0.75
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=quality,
                weight=1.0,
                horizon="3-15D",
                reason=f"Close broke above prior 20-bar high by {extension_atr:.2f} ATR",
            )

        if close < low:
            extension_atr = (low - close) / atr
            confidence = min(0.95, 0.68 + min(max(extension_atr, 0.0), 1.5) * 0.12)
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=0.85,
                weight=1.0,
                horizon="3-15D",
                reason=f"Close broke below prior 20-bar low by {extension_atr:.2f} ATR",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.45,
            quality=0.70,
            weight=0.8,
            horizon="3-15D",
            reason="No confirmed 20-bar breakout",
        )
