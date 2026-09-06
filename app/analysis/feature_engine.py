from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    """Default research/live feature configuration.

    The engine only derives market features. It never imports broker,
    execution, portfolio, or risk modules.
    """

    williams_period: int = 14
    williams_slope_period: int = 3
    ema_periods: tuple[int, ...] = (10, 20, 50)
    ma_periods: tuple[int, ...] = (35, 50, 200)
    momentum_periods: tuple[int, ...] = (5, 10, 14, 20)
    volume_period: int = 20
    atr_period: int = 14
    volatility_period: int = 20
    breakout_period: int = 20
    ath_period: int = 252


class FeatureEngine:
    """Create a canonical set of technical/market features from OHLCV data.

    Required columns for the core engine are ``high``, ``low`` and ``close``.
    ``volume`` is optional; volume features are only produced when it exists.
    ``date`` is optional; when present, rows are sorted chronologically.

    Compatibility aliases are intentionally retained for the current bot:
    ``williams_r``, ``ema20``, ``ema50``, ``atr14``, ``volume20``,
    ``breakout_high`` and ``breakout_low``.
    """

    def __init__(self, config: FeatureConfig | None = None) -> None:
        self.config = config or FeatureConfig()

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("DataFrame is empty.")

        out = df.copy()
        out.columns = [str(column).strip().lower() for column in out.columns]

        required = {"high", "low", "close"}
        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        numeric_columns = [
            column
            for column in ("open", "high", "low", "close", "volume")
            if column in out.columns
        ]
        for column in numeric_columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out = out.sort_values("date", kind="stable")
            out = out.drop_duplicates(subset=["date"], keep="last")

        return out.reset_index(drop=True)

    @staticmethod
    def _positive_periods(periods: Iterable[int]) -> tuple[int, ...]:
        cleaned = tuple(sorted({int(period) for period in periods if int(period) > 0}))
        if not cleaned:
            raise ValueError("At least one positive period is required.")
        return cleaned

    def _add_williams(self, out: pd.DataFrame) -> None:
        period = self.config.williams_period
        highest = out["high"].rolling(period, min_periods=period).max()
        lowest = out["low"].rolling(period, min_periods=period).min()
        denominator = (highest - lowest).replace(0, np.nan)

        out["williams_r"] = -100.0 * (highest - out["close"]) / denominator
        out["williams14"] = out["williams_r"]
        out["williams_slope"] = (
            out["williams_r"].diff(self.config.williams_slope_period)
            / float(self.config.williams_slope_period)
        )

    def _add_averages(self, out: pd.DataFrame) -> None:
        for period in self._positive_periods(self.config.ema_periods):
            # No min_periods here by design: this preserves the EMA behaviour
            # already used by the live bot and the WEMA5 baseline.
            out[f"ema{period}"] = out["close"].ewm(
                span=period,
                adjust=False,
            ).mean()

        for period in self._positive_periods(self.config.ma_periods):
            out[f"ma{period}"] = out["close"].rolling(
                period,
                min_periods=period,
            ).mean()

    def _add_momentum(self, out: pd.DataFrame) -> None:
        for period in self._positive_periods(self.config.momentum_periods):
            # Percentage price change over N completed bars.
            out[f"momentum{period}"] = out["close"].pct_change(periods=period) * 100.0

    def _add_volume(self, out: pd.DataFrame) -> None:
        if "volume" not in out.columns:
            return

        period = self.config.volume_period
        volume_mean = out["volume"].rolling(period, min_periods=period).mean()
        out[f"volume_sma{period}"] = volume_mean
        out["volume20"] = volume_mean if period == 20 else out["volume"].rolling(20, min_periods=20).mean()
        out["rvol"] = out["volume"] / volume_mean.replace(0, np.nan)
        out["rvol20"] = out["rvol"] if period == 20 else out["volume"] / out["volume20"].replace(0, np.nan)
        out["dollar_volume"] = out["close"] * out["volume"]

    def _add_atr(self, out: pd.DataFrame) -> None:
        period = self.config.atr_period
        previous_close = out["close"].shift(1)
        true_range = pd.concat(
            [
                out["high"] - out["low"],
                (out["high"] - previous_close).abs(),
                (out["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        out[f"atr{period}"] = true_range.rolling(period, min_periods=period).mean()
        if period != 14:
            out["atr14"] = true_range.rolling(14, min_periods=14).mean()

    def _add_volatility(self, out: pd.DataFrame) -> None:
        period = self.config.volatility_period
        returns = out["close"].pct_change(fill_method=None)
        out[f"volatility{period}"] = returns.rolling(period, min_periods=period).std() * 100.0

    def _add_breakout(self, out: pd.DataFrame) -> None:
        period = self.config.breakout_period
        breakout_high = out["high"].rolling(period, min_periods=period).max().shift(1)
        breakout_low = out["low"].rolling(period, min_periods=period).min().shift(1)

        out[f"breakout_high{period}"] = breakout_high
        out[f"breakout_low{period}"] = breakout_low
        out["breakout_high"] = breakout_high
        out["breakout_low"] = breakout_low
        out["breakout_distance_pct"] = (
            (out["close"] / breakout_high.replace(0, np.nan)) - 1.0
        ) * 100.0

    def _add_ath(self, out: pd.DataFrame) -> None:
        period = self.config.ath_period
        ath = out["high"].rolling(period, min_periods=period).max()
        out[f"ath{period}"] = ath
        out["distance_from_ath_pct"] = ((out["close"] / ath.replace(0, np.nan)) - 1.0) * 100.0

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return normalized OHLCV data plus the canonical feature set."""

        out = self.normalize(df)
        self._add_williams(out)
        self._add_averages(out)
        self._add_momentum(out)
        self._add_volume(out)
        self._add_atr(out)
        self._add_volatility(out)
        self._add_breakout(out)
        self._add_ath(out)
        return out


DEFAULT_FEATURE_ENGINE = FeatureEngine()
