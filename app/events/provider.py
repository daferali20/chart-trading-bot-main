from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.events.models import NewsEvent


@runtime_checkable
class NewsEventProvider(Protocol):
    async def events(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Sequence[NewsEvent]:
        """Return normalized events for one symbol.

        Concrete providers may use a news API, SEC filings, earnings calendars,
        FinBERT/LLM enrichment, or a historical research dataset.
        """
