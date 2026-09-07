from __future__ import annotations

import pandas as pd

from app.strategy.base import AlphaModel
from app.strategy.fusion import AlphaSignal, SignalDirection


class VolatilityExpansionAlpha(AlphaModel):
    """Detect transition from compressed volatility into confirmed expansion."""

    name = "VolatilityExpansionAlpha"
    version = "v1"
    required_features = (
        "close",
        "volatility20",
        "rvol20",
        "breakout_high",
        "breakout_low",
        "atr14",
    )

    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        data = self.prepare(df)
        row = data.iloc[-1]
        if any(pd.isna(row[column]) for column in self.required_features):
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Volatility features not ready")

        vol_history = data["volatility20"].dropna().tail(60)
        if len(vol_history) < 20:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Not enough volatility history")

        current_vol = float(row["volatility20"])
        median_vol = float(vol_history.iloc[:-1].median()) if len(vol_history) > 1 else current_vol
        close = float(row["close"])
        breakout_high = float(row["breakout_high"])
        breakout_low = float(row["breakout_low"])
        rvol = float(row["rvol20"])
        atr = float(row["atr14"])

        if median_vol <= 0 or atr <= 0:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="Volatility baseline not ready")

        expansion_ratio = current_vol / median_vol
        confirmed_expansion = expansion_ratio >= 1.15 and rvol >= 1.15

        if confirmed_expansion and close > breakout_high:
            confidence = min(0.95, 0.64 + min(expansion_ratio - 1.0, 1.5) * 0.14 + min(rvol - 1.0, 2.0) * 0.06)
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=0.88,
                weight=1.0,
                horizon="2-12D",
                reason=f"Volatility expansion {expansion_ratio:.2f}x with RVOL={rvol:.2f} and upside breakout",
            )

        if confirmed_expansion and close < breakout_low:
            confidence = min(0.95, 0.64 + min(expansion_ratio - 1.0, 1.5) * 0.14 + min(rvol - 1.0, 2.0) * 0.06)
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=0.86,
                weight=1.0,
                horizon="2-12D",
                reason=f"Volatility expansion {expansion_ratio:.2f}x with RVOL={rvol:.2f} and downside breakout",
            )

        if expansion_ratio <= 0.80:
            return AlphaSignal(
                self.name,
                SignalDirection.NEUTRAL,
                0.48,
                quality=0.76,
                weight=0.8,
                horizon="2-12D",
                reason=f"Volatility compression detected ({expansion_ratio:.2f}x median); waiting for expansion",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.42,
            quality=0.68,
            weight=0.8,
            horizon="2-12D",
            reason="No confirmed volatility expansion breakout",
        )
