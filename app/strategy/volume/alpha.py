from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class VolumeAlpha(AlphaModel):
    name = "VolumeAlpha"
    version = "v1"
    required_features = ("rvol20", "dollar_volume", "momentum20")

    def __init__(self, min_rvol: float = 1.20, min_dollar_volume: float = 5_000_000.0) -> None:
        self.min_rvol = float(min_rvol)
        self.min_dollar_volume = float(min_dollar_volume)

    def parameters(self) -> dict[str, object]:
        return {
            "min_rvol": self.min_rvol,
            "min_dollar_volume": self.min_dollar_volume,
        }

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        if any(pd.isna(row[column]) for column in self.required_features):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Volume features not ready")

        rvol = float(row["rvol20"])
        dollar_volume = float(row["dollar_volume"])
        momentum20 = float(row["momentum20"])

        if rvol < self.min_rvol or dollar_volume < self.min_dollar_volume:
            return AlphaSignal(
                self.name,
                SignalDirection.NEUTRAL,
                0.45,
                quality=0.60,
                weight=0.8,
                horizon="1-10D",
                reason=(
                    f"Volume confirmation absent: RVOL={rvol:.2f}, "
                    f"DollarVol=${dollar_volume:,.0f}"
                ),
            )

        confidence = min(0.95, 0.60 + min(max(rvol - 1.0, 0.0), 2.0) * 0.15)
        quality = 0.92 if dollar_volume >= 20_000_000 else 0.80

        if momentum20 > 0:
            direction = SignalDirection.LONG
            reason = f"RVOL={rvol:.2f} with positive 20-bar momentum"
        elif momentum20 < 0:
            direction = SignalDirection.SHORT
            reason = f"RVOL={rvol:.2f} with negative 20-bar momentum"
        else:
            direction = SignalDirection.NEUTRAL
            reason = f"RVOL={rvol:.2f} but momentum is flat"

        return AlphaSignal(
            self.name,
            direction,
            confidence,
            quality=quality,
            weight=0.9,
            horizon="1-10D",
            reason=reason,
        )
