from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from app.data.normalizer import DEFAULT_DATA_NORMALIZER


@runtime_checkable
class MarketDataProvider(Protocol):
    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        """Return historical market bars for one symbol."""


class IBKRDataProvider:
    """Read-only adapter around the existing IBKR client."""

    def __init__(self, client: object) -> None:
        if not hasattr(client, "historical_bars"):
            raise TypeError("IBKR client must provide historical_bars(symbol)")
        self.client = client

    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        raw = await self.client.historical_bars(symbol)
        return DEFAULT_DATA_NORMALIZER.normalize(
            raw,
            require_open=True,
            require_volume=True,
            preserve_extra=False,
        )


class CSVDataProvider:
    """Historical CSV provider for backtests/research without broker access."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _resolve(self, symbol: str) -> Path:
        symbol = symbol.upper()
        candidates = (
            self.root / f"{symbol}.csv",
            self.root / f"{symbol.lower()}.csv",
        )
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError(f"No CSV dataset found for {symbol} in {self.root}")

    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        raw = pd.read_csv(self._resolve(symbol))
        return DEFAULT_DATA_NORMALIZER.normalize(
            raw,
            require_open=True,
            require_volume=True,
            preserve_extra=False,
        )
