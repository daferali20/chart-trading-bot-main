from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class MomentumAlpha(AlphaModel):
    name = "MomentumAlpha"
    version = "v1"
    required_features = (
        "momentum5",
        "momentum10",
        "momentum14",
        "momentum20",
        "rsi14",
    )

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        momentum_columns = ("momentum5", "momentum10", "momentum14", "momentum20")
        values = [row[column] for column in momentum_columns]
        if any(pd.isna(value) for value in values) or pd.isna(row["rsi14"]):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Momentum not ready")

        positive = sum(float(value) > 0 for value in values)
        negative = sum(float(value) < 0 for value in values)
        rsi = float(row["rsi14"])

        if positive >= 3 and 50.0 <= rsi < 80.0:
            confidence = min(0.95, 0.55 + (0.09 * positive))
            quality = 0.90 if rsi < 72.0 else 0.75
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=quality,
                weight=1.0,
                horizon="5-20D",
                reason=f"{positive}/4 momentum windows positive; RSI14={rsi:.1f}",
            )

        if negative >= 3 and rsi < 50.0:
            confidence = min(0.95, 0.55 + (0.09 * negative))
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=0.85,
                weight=1.0,
                horizon="5-20D",
                reason=f"{negative}/4 momentum windows negative; RSI14={rsi:.1f}",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.45,
            quality=0.70,
            weight=0.8,
            horizon="5-20D",
            reason="Momentum windows are mixed",
        )
