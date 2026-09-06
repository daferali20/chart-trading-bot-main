from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class WEMA5Signal:
    action: str
    symbol: str
    price: float
    reason: str
    timestamp: Optional[str] = None


class WEMA5Strategy:
    """
    WEMA5 Baseline v1

    Williams %R:
        period = 14

    BUY:
        Williams %R crosses upward through -55.

    SELL:
        Five consecutive completed candle closes below EMA10.

    Important:
        Signals are generated from COMPLETED candles.
        Backtest execution should occur on the NEXT candle open.
    """

    NAME = "WEMA5_BASELINE_v1"

    WILLIAMS_PERIOD = 14
    EMA_PERIOD = 10

    ENTRY_LEVEL = -55.0
    EXIT_CONSECUTIVE_CANDLES = 5

    def __init__(self, symbol: str):
        self.symbol = symbol

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Williams %R(14) and EMA10.

        Required columns:
            high
            low
            close
        """

        if df is None or df.empty:
            raise ValueError("DataFrame is empty.")

        required = {"high", "low", "close"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}"
            )

        out = df.copy()

        highest_high = out["high"].rolling(
            WEMA5Strategy.WILLIAMS_PERIOD
        ).max()

        lowest_low = out["low"].rolling(
            WEMA5Strategy.WILLIAMS_PERIOD
        ).min()

        denominator = (
            highest_high - lowest_low
        ).replace(0, pd.NA)

        out["williams_r"] = (
            -100
            * (highest_high - out["close"])
            / denominator
        )

        out["ema10"] = out["close"].ewm(
            span=WEMA5Strategy.EMA_PERIOD,
            adjust=False,
        ).mean()

        return out

    @classmethod
    def detect_entry(
        cls,
        previous_williams: float,
        current_williams: float,
    ) -> bool:
        """
        Entry occurs when Williams crosses upward through -55.

        Example:

            previous = -60
            current  = -52

        => BUY
        """

        if pd.isna(previous_williams) or pd.isna(current_williams):
            return False

        return (
            previous_williams < cls.ENTRY_LEVEL
            and current_williams >= cls.ENTRY_LEVEL
        )

    @classmethod
    def count_ema10_below(
        cls,
        df: pd.DataFrame,
        end_index: int,
    ) -> int:
        """
        Count consecutive completed candle closes below EMA10,
        ending at end_index.
        """

        if end_index < 0:
            return 0

        count = 0

        for i in range(end_index, -1, -1):
            close = df.iloc[i]["close"]
            ema10 = df.iloc[i]["ema10"]

            if pd.isna(close) or pd.isna(ema10):
                break

            if close < ema10:
                count += 1
            else:
                break

        return count

    @classmethod
    def detect_exit(
        cls,
        df: pd.DataFrame,
        end_index: int,
    ) -> bool:
        """
        Exit after five consecutive completed daily closes
        below EMA10.
        """

        count = cls.count_ema10_below(
            df,
            end_index,
        )

        return count >= cls.EXIT_CONSECUTIVE_CANDLES

    def generate_signal(
        self,
        df: pd.DataFrame,
        index: Optional[int] = None,
        in_position: bool = False,
    ) -> Optional[WEMA5Signal]:
        """
        Generate a signal from a completed candle.

        BUY:
            Williams crosses upward through -55.

        SELL:
            In position AND five consecutive closes are below EMA10.
        """

        if df is None or df.empty:
            return None

        data = self.add_indicators(df)

        if index is None:
            index = len(data) - 1

        if index < 1:
            return None

        if index >= len(data):
            raise IndexError(
                f"index {index} is outside DataFrame."
            )

        current = data.iloc[index]
        previous = data.iloc[index - 1]

        timestamp = None

        if "date" in data.columns:
            timestamp = str(current["date"])

        current_close = float(current["close"])

        # ---------------------------------------------------------
        # EXIT
        # ---------------------------------------------------------

        if in_position:

            below_count = self.count_ema10_below(
                data,
                index,
            )

            if below_count >= self.EXIT_CONSECUTIVE_CANDLES:

                return WEMA5Signal(
                    action="SELL",
                    symbol=self.symbol,
                    price=current_close,
                    reason=(
                        f"{below_count} consecutive closes "
                        f"below EMA10"
                    ),
                    timestamp=timestamp,
                )

        # ---------------------------------------------------------
        # ENTRY
        # ---------------------------------------------------------

        previous_williams = previous["williams_r"]
        current_williams = current["williams_r"]

        if self.detect_entry(
            previous_williams,
            current_williams,
        ):

            return WEMA5Signal(
                action="BUY",
                symbol=self.symbol,
                price=current_close,
                reason=(
                    f"Williams %R crossed upward through "
                    f"{self.ENTRY_LEVEL:.0f} "
                    f"({previous_williams:.2f} → "
                    f"{current_williams:.2f})"
                ),
                timestamp=timestamp,
            )

        return None