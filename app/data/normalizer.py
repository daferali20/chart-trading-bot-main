from __future__ import annotations

import pandas as pd


class DataNormalizer:
    """Normalize market data from IBKR, CSV, TradingView or future sources.

    Canonical columns are lower-case and chronologically ordered. ``date`` is
    created from common time aliases such as ``timestamp`` when available.
    Extra source columns are preserved by default for backward compatibility.
    """

    TIME_ALIASES = ("date", "timestamp", "datetime", "time")

    def normalize(
        self,
        df: pd.DataFrame,
        *,
        require_open: bool = False,
        require_volume: bool = False,
        preserve_extra: bool = True,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("DataFrame is empty.")

        out = df.copy()
        out.columns = [str(column).strip().lower() for column in out.columns]

        required = {"high", "low", "close"}
        if require_open:
            required.add("open")
        if require_volume:
            required.add("volume")

        missing = required - set(out.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        time_column = next(
            (column for column in self.TIME_ALIASES if column in out.columns),
            None,
        )
        if time_column is not None:
            parsed = pd.to_datetime(out[time_column], errors="coerce", utc=False)
            out[time_column] = parsed
            if "date" not in out.columns:
                out["date"] = parsed

        numeric_columns = [
            column
            for column in ("open", "high", "low", "close", "volume")
            if column in out.columns
        ]
        for column in numeric_columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

        essential = ["high", "low", "close"]
        if require_open:
            essential.append("open")
        if require_volume:
            essential.append("volume")
        if time_column is not None:
            essential.append("date")

        out = out.dropna(subset=list(dict.fromkeys(essential)))

        if "date" in out.columns:
            out = out.sort_values("date", kind="stable")
            out = out.drop_duplicates(subset=["date"], keep="last")

        out = out.reset_index(drop=True)

        if preserve_extra:
            return out

        canonical = [
            column
            for column in ("date", "open", "high", "low", "close", "volume")
            if column in out.columns
        ]
        return out[canonical].copy()


DEFAULT_DATA_NORMALIZER = DataNormalizer()
