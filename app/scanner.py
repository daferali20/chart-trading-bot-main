from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ib_async import ScannerSubscription


class _ScannerCancellationNoiseFilter(logging.Filter):
    """Hide only the expected scanner snapshot cancellation message.

    ``ib_async.reqScannerDataAsync`` creates a scanner subscription, waits for
    the snapshot to finish, and then explicitly cancels that subscription.
    TWS may report that normal cleanup as error 162.  It is not a failed market
    data request, so keep the console clean while preserving every other IBKR
    warning/error (including other error-162 messages).
    """

    _BENIGN_TEXT = "API scanner subscription cancelled"

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return self._BENIGN_TEXT.lower() not in message.lower()


def _install_scanner_noise_filter() -> None:
    marker = "_ai_trader_scanner_cancel_filter_installed"
    for logger_name in ("ib_async.wrapper", "ib_async.client"):
        logger = logging.getLogger(logger_name)
        if getattr(logger, marker, False):
            continue
        logger.addFilter(_ScannerCancellationNoiseFilter())
        setattr(logger, marker, True)


_install_scanner_noise_filter()


@dataclass(frozen=True)
class Candidate:
    symbol: str
    rank: int
    change_percent: float


def load_watchlist(path="watchlist.txt"):
    try:
        with open(path, encoding="utf-8") as f:
            return [
                x.strip().upper()
                for x in f
                if x.strip() and not x.lstrip().startswith("#")
            ]
    except FileNotFoundError:
        return []


async def top_gainers(ib, number=10):
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=max(number, 10),
        abovePrice=1.0,
        aboveVolume=100000,
    )
    rows = await ib.reqScannerDataAsync(sub)
    return [
        Candidate(r.contractDetails.contract.symbol, int(r.rank) + 1, 0.0)
        for r in rows[:number]
    ]


def merge_candidates(gainers: Iterable[Candidate], custom: Iterable[str]):
    result = []
    for candidate in gainers:
        if candidate.symbol not in result:
            result.append(candidate.symbol)
    for symbol in custom:
        if symbol not in result:
            result.append(symbol)
    return result
