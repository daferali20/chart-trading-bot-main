from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

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


HistoryLoader = Callable[..., pd.DataFrame]


class YahooDataProvider:
    """Read-only Yahoo Finance provider for research/backtests.

    This provider deliberately does not expose quotes, orders or broker state.
    It uses adjusted OHLC by default so stock splits/dividends do not create
    artificial price jumps in long-horizon research. Yahoo remains a research
    source only; IBKR stays the execution/live-market source.
    """

    SESSION_INTERVALS = {"1d", "5d", "1wk", "1mo", "3mo"}

    def __init__(
        self,
        *,
        period: str = "5y",
        interval: str = "1d",
        auto_adjust: bool = True,
        repair: bool = True,
        prepost: bool = False,
        timeout: float = 20.0,
        history_loader: HistoryLoader | None = None,
    ) -> None:
        self.period = str(period)
        self.interval = str(interval)
        self.auto_adjust = bool(auto_adjust)
        self.repair = bool(repair)
        self.prepost = bool(prepost)
        self.timeout = float(timeout)
        self._history_loader = history_loader

    @staticmethod
    def _reset_time_index(raw: pd.DataFrame) -> pd.DataFrame:
        frame = raw.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            # Ticker.history normally returns flat columns, but keep this
            # defensive path for injected/download-like loaders.
            flattened = []
            known = {"date", "datetime", "open", "high", "low", "close", "volume"}
            for column in frame.columns:
                parts = [str(part) for part in column if str(part) not in {"", "None"}]
                selected = next(
                    (part for part in parts if part.strip().lower() in known),
                    parts[0] if parts else "",
                )
                flattened.append(selected)
            frame.columns = flattened

        lower = {str(column).strip().lower() for column in frame.columns}
        if not ({"date", "datetime", "timestamp", "time"} & lower):
            frame = frame.reset_index()
        return frame

    def _normalize_session_dates(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.interval.lower() not in self.SESSION_INTERVALS or "date" not in frame.columns:
            return frame

        out = frame.copy()
        dates = out["date"]
        if isinstance(dates.dtype, pd.DatetimeTZDtype):
            # Daily/weekly/monthly Yahoo bars represent market sessions. Keep
            # the exchange-calendar date itself instead of converting midnight
            # New York to UTC, which can complicate CSV parsing across DST.
            out["date"] = dates.dt.tz_localize(None)
        return out

    def _load_sync(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Yahoo symbol is required")

        if self._history_loader is not None:
            raw = self._history_loader(
                symbol,
                period=self.period,
                interval=self.interval,
                auto_adjust=self.auto_adjust,
                repair=self.repair,
                prepost=self.prepost,
                timeout=self.timeout,
            )
        else:
            try:
                import yfinance as yf
            except ImportError as exc:  # pragma: no cover - guarded by requirements
                raise RuntimeError(
                    "yfinance is not installed. Run: pip install -r requirements.txt"
                ) from exc

            ticker = yf.Ticker(symbol)
            raw = ticker.history(
                period=self.period,
                interval=self.interval,
                auto_adjust=self.auto_adjust,
                repair=self.repair,
                prepost=self.prepost,
                actions=False,
                timeout=self.timeout,
                raise_errors=True,
            )

        if raw is None or raw.empty:
            raise RuntimeError(
                f"Yahoo Finance returned no historical bars for {symbol} "
                f"({self.period}, {self.interval})"
            )

        raw = self._reset_time_index(raw)
        normalized = DEFAULT_DATA_NORMALIZER.normalize(
            raw,
            require_open=True,
            require_volume=True,
            preserve_extra=False,
        )
        normalized = self._normalize_session_dates(normalized)
        if normalized.empty:
            raise RuntimeError(f"Yahoo historical bars normalized to empty for {symbol}")
        return normalized

    async def historical_bars(self, symbol: str) -> pd.DataFrame:
        # yfinance is synchronous; keep network I/O off the async event loop.
        return await asyncio.to_thread(self._load_sync, symbol)
