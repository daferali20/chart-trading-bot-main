from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from collections.abc import Iterable

from app.data.providers import YahooDataProvider


@dataclass(frozen=True)
class YahooDatasetEntry:
    symbol: str
    rows: int
    start: str
    end: str
    path: str


@dataclass(frozen=True)
class YahooDatasetBuildReport:
    generated_at: str
    period: str
    interval: str
    output_dir: str
    entries: tuple[YahooDatasetEntry, ...]
    errors: dict[str, str]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["entries"] = [asdict(item) for item in self.entries]
        return payload

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return destination


class YahooDatasetBuilder:
    """Download canonical OHLCV research datasets from Yahoo Finance.

    Downloads are stored under ``data/`` by default, which this repository
    ignores. This keeps licensed/raw market data out of source control while
    still allowing repeatable local research.
    """

    def __init__(
        self,
        provider: YahooDataProvider,
        *,
        output_dir: str | Path,
        retries: int = 2,
        retry_delay_seconds: float = 1.5,
    ) -> None:
        self.provider = provider
        self.output_dir = Path(output_dir)
        self.retries = max(0, int(retries))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    @staticmethod
    def _clean_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        output: list[str] = []
        for raw in symbols:
            symbol = str(raw).strip().upper()
            if not symbol or symbol.startswith("#") or symbol in seen:
                continue
            seen.add(symbol)
            output.append(symbol)
        return tuple(output)

    @staticmethod
    def _filename(symbol: str) -> str:
        return symbol.replace("/", "-").replace("^", "INDEX_") + ".csv"

    async def _fetch(self, symbol: str):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await self.provider.historical_bars(symbol)
            except Exception as exc:  # provider/network failures are recorded
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))
        assert last_error is not None
        raise last_error

    async def build(self, symbols: Iterable[str]) -> YahooDatasetBuildReport:
        cleaned = self._clean_symbols(symbols)
        if not cleaned:
            raise ValueError("At least one Yahoo symbol is required")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        entries: list[YahooDatasetEntry] = []
        errors: dict[str, str] = {}

        # Intentionally sequential. Yahoo can throttle bursty clients, and
        # reproducible research matters more than shaving seconds off downloads.
        for symbol in cleaned:
            try:
                frame = await self._fetch(symbol)
                destination = self.output_dir / self._filename(symbol)
                frame.to_csv(destination, index=False)
                entries.append(
                    YahooDatasetEntry(
                        symbol=symbol,
                        rows=len(frame),
                        start=str(frame.iloc[0]["date"]),
                        end=str(frame.iloc[-1]["date"]),
                        path=str(destination),
                    )
                )
            except Exception as exc:
                errors[symbol] = f"{type(exc).__name__}: {exc}"

        return YahooDatasetBuildReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            period=self.provider.period,
            interval=self.provider.interval,
            output_dir=str(self.output_dir),
            entries=tuple(entries),
            errors=errors,
        )
