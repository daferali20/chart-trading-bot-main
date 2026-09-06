from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RISK_OFF = "RISK_OFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: MarketRegime
    confidence: float
    reasons: tuple[str, ...]
    metrics: dict[str, Any]


class MarketRegimeEngine:
    """Classify broad market conditions from benchmark OHLCV data.

    This layer is intentionally execution-free. A caller can feed SPY or any
    benchmark and use the resulting regime as context for strategies, fusion,
    portfolio construction, or risk controls.
    """

    def __init__(self, trend_lookback: int = 5, volatility_lookback: int = 60) -> None:
        self.trend_lookback = max(1, int(trend_lookback))
        self.volatility_lookback = max(20, int(volatility_lookback))

    def classify(self, df: pd.DataFrame) -> RegimeSnapshot:
        if df is None or len(df) < 200:
            return RegimeSnapshot(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                reasons=("At least 200 bars are required for MA200 regime context",),
                metrics={},
            )

        data = DEFAULT_FEATURE_ENGINE.build(df)
        row = data.iloc[-1]
        close = float(row["close"])
        ma200 = row["ma200"]
        ma35 = row["ma35"]
        momentum20 = row["momentum20"]
        volatility20 = row["volatility20"]
        rvol20 = row.get("rvol20", pd.NA)

        if any(pd.isna(value) for value in (ma200, ma35, momentum20, volatility20)):
            return RegimeSnapshot(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                reasons=("Regime indicators are not ready",),
                metrics={},
            )

        prior_index = max(0, len(data) - 1 - self.trend_lookback)
        prior_ma35 = data.iloc[prior_index]["ma35"]
        ma35_slope = 0.0 if pd.isna(prior_ma35) else float(ma35 - prior_ma35)

        vol_history = data["volatility20"].dropna().tail(self.volatility_lookback)
        vol_median = float(vol_history.median()) if not vol_history.empty else float(volatility20)
        high_vol = vol_median > 0 and float(volatility20) >= (vol_median * 1.5)

        above_ma200 = close > float(ma200)
        below_ma200 = close < float(ma200)
        rising_ma35 = ma35_slope > 0
        falling_ma35 = ma35_slope < 0
        positive_momentum = float(momentum20) > 0
        negative_momentum = float(momentum20) < 0
        elevated_volume = pd.notna(rvol20) and float(rvol20) >= 1.30

        metrics = {
            "close": close,
            "ma200": float(ma200),
            "ma35": float(ma35),
            "ma35_slope": ma35_slope,
            "momentum20": float(momentum20),
            "volatility20": float(volatility20),
            "volatility_median": vol_median,
            "rvol20": None if pd.isna(rvol20) else float(rvol20),
        }

        if below_ma200 and negative_momentum and high_vol and elevated_volume:
            return RegimeSnapshot(
                regime=MarketRegime.RISK_OFF,
                confidence=90.0,
                reasons=(
                    "Benchmark below MA200",
                    "20-bar momentum negative",
                    "Volatility expanded materially above recent median",
                    "Relative volume elevated",
                ),
                metrics=metrics,
            )

        if high_vol:
            return RegimeSnapshot(
                regime=MarketRegime.HIGH_VOLATILITY,
                confidence=80.0,
                reasons=("Volatility expanded materially above recent median",),
                metrics=metrics,
            )

        bull_votes = sum((above_ma200, rising_ma35, positive_momentum))
        bear_votes = sum((below_ma200, falling_ma35, negative_momentum))

        if bull_votes == 3:
            return RegimeSnapshot(
                regime=MarketRegime.BULL,
                confidence=90.0,
                reasons=(
                    "Benchmark above MA200",
                    "MA35 rising",
                    "20-bar momentum positive",
                ),
                metrics=metrics,
            )

        if bear_votes == 3:
            return RegimeSnapshot(
                regime=MarketRegime.BEAR,
                confidence=90.0,
                reasons=(
                    "Benchmark below MA200",
                    "MA35 falling",
                    "20-bar momentum negative",
                ),
                metrics=metrics,
            )

        confidence = 55.0 + (10.0 * abs(bull_votes - bear_votes))
        return RegimeSnapshot(
            regime=MarketRegime.SIDEWAYS,
            confidence=min(confidence, 75.0),
            reasons=("Trend and momentum signals are mixed",),
            metrics=metrics,
        )


DEFAULT_REGIME_ENGINE = MarketRegimeEngine()
