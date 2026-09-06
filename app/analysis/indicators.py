from __future__ import annotations

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible entry point for the current bot.

    Existing callers can keep importing ``add_indicators`` while all shared
    technical features are now calculated by the canonical Feature Engine.
    """

    return DEFAULT_FEATURE_ENGINE.build(df)
