from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.strategy.fusion import AlphaSignal, SignalDirection


class MultiTimeframeAlpha:
    name = "MultiTimeframeAlpha"
    version = "v1"

    def __init__(self, minimum_agreement: float = 0.60) -> None:
        self.minimum_agreement = max(0.50, min(1.0, float(minimum_agreement)))

    def parameters(self) -> dict[str, object]:
        return {"minimum_agreement": self.minimum_agreement}

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        required = {"close", "ema10", "ma35", "momentum10"}
        if required.issubset(df.columns):
            return df
        return DEFAULT_FEATURE_ENGINE.build(df)

    def generate_alpha(self, frames: Mapping[str, pd.DataFrame]) -> AlphaSignal:
        if not frames:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="No timeframes supplied")

        bullish: list[str] = []
        bearish: list[str] = []
        usable: list[str] = []

        for timeframe, frame in frames.items():
            if frame is None or frame.empty:
                continue
            data = self._prepare(frame)
            row = data.iloc[-1]
            values = [row.get("close"), row.get("ema10"), row.get("ma35"), row.get("momentum10")]
            if any(value is None or pd.isna(value) for value in values):
                continue

            usable.append(timeframe)
            close = float(row["close"])
            ema10 = float(row["ema10"])
            ma35 = float(row["ma35"])
            momentum10 = float(row["momentum10"])

            if close > ema10 and close > ma35 and momentum10 > 0:
                bullish.append(timeframe)
            elif close < ema10 and close < ma35 and momentum10 < 0:
                bearish.append(timeframe)

        total = len(usable)
        if total == 0:
            return AlphaSignal(self.name, SignalDirection.NEUTRAL, 0.0, reason="MTF features not ready")

        bull_ratio = len(bullish) / total
        bear_ratio = len(bearish) / total

        if bull_ratio >= self.minimum_agreement and bull_ratio > bear_ratio:
            confidence = min(0.95, 0.55 + (0.40 * bull_ratio))
            return AlphaSignal(
                self.name,
                SignalDirection.LONG,
                confidence,
                quality=min(0.95, 0.65 + (0.30 * bull_ratio)),
                weight=1.1,
                horizon="MTF",
                reason=f"Bullish alignment on {len(bullish)}/{total} timeframes: {', '.join(bullish)}",
            )

        if bear_ratio >= self.minimum_agreement and bear_ratio > bull_ratio:
            confidence = min(0.95, 0.55 + (0.40 * bear_ratio))
            return AlphaSignal(
                self.name,
                SignalDirection.SHORT,
                confidence,
                quality=min(0.95, 0.65 + (0.30 * bear_ratio)),
                weight=1.1,
                horizon="MTF",
                reason=f"Bearish alignment on {len(bearish)}/{total} timeframes: {', '.join(bearish)}",
            )

        return AlphaSignal(
            self.name,
            SignalDirection.NEUTRAL,
            0.50,
            quality=0.65,
            weight=0.9,
            horizon="MTF",
            reason=f"Timeframe agreement insufficient: bull={bull_ratio:.0%}, bear={bear_ratio:.0%}",
        )
