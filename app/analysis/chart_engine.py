from __future__ import annotations

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE


def add_chart_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add chart-only context on top of the canonical feature set."""

    out = DEFAULT_FEATURE_ENGINE.build(df)
    h, l, c = out["high"], out["low"], out["close"]

    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    out["tenkan"] = tenkan
    out["kijun"] = kijun
    out["senkou_a"] = ((tenkan + kijun) / 2).shift(26)
    out["senkou_b"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)

    if "volume" in out.columns:
        typical = (h + l + c) / 3
        raw_money_flow = typical * out["volume"]
        direction = typical.diff()
        positive = raw_money_flow.where(direction > 0, 0.0).rolling(14).sum()
        negative = raw_money_flow.where(direction < 0, 0.0).rolling(14).sum()
        out["mfi14"] = 100 - (100 / (1 + positive / negative.replace(0, pd.NA)))
    else:
        out["mfi14"] = pd.NA

    # Compatibility aliases expected by the existing UI.
    out["ema50_chart"] = out["ema50"]
    out["volume_sma20"] = out.get("volume_sma20", pd.Series(pd.NA, index=out.index))
    out["volume_ratio"] = out.get("rvol20", pd.Series(pd.NA, index=out.index))

    out["cloud_top"] = pd.concat([out["senkou_a"], out["senkou_b"]], axis=1).max(axis=1)
    out["cloud_bottom"] = pd.concat([out["senkou_a"], out["senkou_b"]], axis=1).min(axis=1)
    out["above_cloud"] = c > out["cloud_top"]
    out["below_cloud"] = c < out["cloud_bottom"]
    return out


def chart_context(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    return {
        "close": float(row.close),
        "ema50": float(row.ema50_chart) if pd.notna(row.ema50_chart) else None,
        "williams_r": float(row.williams_r) if pd.notna(row.williams_r) else None,
        "mfi14": float(row.mfi14) if pd.notna(row.mfi14) else None,
        "volume_ratio": float(row.volume_ratio) if pd.notna(row.volume_ratio) else None,
        "above_cloud": bool(row.above_cloud) if pd.notna(row.above_cloud) else False,
        "below_cloud": bool(row.below_cloud) if pd.notna(row.below_cloud) else False,
        "cloud_top": float(row.cloud_top) if pd.notna(row.cloud_top) else None,
        "cloud_bottom": float(row.cloud_bottom) if pd.notna(row.cloud_bottom) else None,
    }
