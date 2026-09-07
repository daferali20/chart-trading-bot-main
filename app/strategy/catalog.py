from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyCatalogEntry:
    name: str
    family: str
    timeframe: str
    regime_fit: tuple[str, ...]
    status: str
    implementation: str
    notes: str = ""


STRATEGY_CATALOG: tuple[StrategyCatalogEntry, ...] = (
    StrategyCatalogEntry(
        "WEMA5_BASELINE_v1", "recovery", "1D", ("BULL", "SIDEWAYS"), "BASELINE",
        "app.strategy.wema5.strategy.WEMA5Strategy",
        "Williams recovery with EMA10 exit; protected baseline.",
    ),
    StrategyCatalogEntry(
        "MomentumAlpha", "momentum", "1D", ("BULL",), "ACTIVE_ANALYSIS",
        "app.strategy.momentum.alpha.MomentumAlpha",
    ),
    StrategyCatalogEntry(
        "TrendAlpha", "trend", "1D", ("BULL", "BEAR"), "ACTIVE_ANALYSIS",
        "app.strategy.trend.alpha.TrendAlpha",
    ),
    StrategyCatalogEntry(
        "BreakoutAlpha", "breakout", "1D", ("BULL", "HIGH_VOLATILITY"), "ACTIVE_ANALYSIS",
        "app.strategy.breakout.alpha.BreakoutAlpha",
    ),
    StrategyCatalogEntry(
        "VolumeAlpha", "liquidity_volume", "1D", ("BULL", "SIDEWAYS", "HIGH_VOLATILITY"), "ACTIVE_ANALYSIS",
        "app.strategy.volume.alpha.VolumeAlpha",
    ),
    StrategyCatalogEntry(
        "MultiTimeframeAlpha", "multi_timeframe", "5m-1D", ("BULL", "BEAR", "SIDEWAYS"), "ACTIVE_ANALYSIS",
        "app.strategy.mtf.alpha.MultiTimeframeAlpha",
    ),
    StrategyCatalogEntry(
        "MeanReversionAlpha", "mean_reversion", "1D", ("SIDEWAYS",), "RESEARCH",
        "app.strategy.mean_reversion.alpha.MeanReversionAlpha",
        "Must prove positive normal-market expectancy before fusion activation.",
    ),
    StrategyCatalogEntry(
        "VolatilityExpansionAlpha", "volatility_breakout", "1D", ("BULL", "HIGH_VOLATILITY"), "RESEARCH",
        "app.strategy.volatility.alpha.VolatilityExpansionAlpha",
        "Designed for compression-to-expansion transitions.",
    ),
    StrategyCatalogEntry(
        "OpeningRangeBreakout", "intraday_breakout", "1m-15m", ("BULL", "HIGH_VOLATILITY"), "PLANNED_RESEARCH",
        "",
        "Requires intraday opening-session data; do not validate on daily bars.",
    ),
    StrategyCatalogEntry(
        "VWAPReclaim", "intraday_mean_reversion", "1m-15m", ("SIDEWAYS", "BULL"), "PLANNED_RESEARCH",
        "",
        "Requires intraday VWAP and session-volume data.",
    ),
    StrategyCatalogEntry(
        "PostEventDrift", "event_driven", "1D", ("BULL", "SIDEWAYS"), "PLANNED_RESEARCH",
        "",
        "Must be conditioned on event type, surprise, sentiment and out-of-sample evidence.",
    ),
)


def by_status(status: str) -> tuple[StrategyCatalogEntry, ...]:
    status = status.upper()
    return tuple(item for item in STRATEGY_CATALOG if item.status == status)
