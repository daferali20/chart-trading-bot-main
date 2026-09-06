from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class WilliamsAlpha(AlphaModel):
    name = "WilliamsAlpha"
    version = "v1"
    required_features = ("williams_r", "williams_slope")

    def __init__(self, entry_level: float = -55.0) -> None:
        self.entry_level = float(entry_level)

    def parameters(self) -> dict[str, object]:
        return {"entry_level": self.entry_level}

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        if len(data) < 2:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Not enough bars")

        previous = data.iloc[-2]["williams_r"]
        current = data.iloc[-1]["williams_r"]
        slope = data.iloc[-1]["williams_slope"]
        if pd.isna(previous) or pd.isna(current):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Williams not ready")

        crossed_up = previous < self.entry_level <= current
        if crossed_up:
            acceleration = max(0.0, float(current - previous))
            confidence = min(0.95, 0.75 + (acceleration / 100.0))
            return AlphaSignal(
                name=self.name,
                direction=SignalDirection.LONG,
                confidence=confidence,
                quality=0.90,
                weight=1.0,
                horizon="10-20D",
                reason=f"Williams crossed above {self.entry_level:.0f}",
            )

        if current >= self.entry_level and pd.notna(slope) and float(slope) > 0:
            return AlphaSignal(
                name=self.name,
                direction=SignalDirection.LONG,
                confidence=0.60,
                quality=0.75,
                weight=0.8,
                horizon="10-20D",
                reason="Williams above entry level and rising",
            )

        return AlphaSignal(
            name=self.name,
            direction=SignalDirection.NEUTRAL,
            confidence=0.40,
            quality=0.70,
            weight=0.8,
            horizon="10-20D",
            reason="No Williams recovery signal",
        )
