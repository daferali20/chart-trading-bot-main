from __future__ import annotations

from dataclasses import dataclass

from app.analysis.regime import MarketRegime
from app.strategy.catalog import STRATEGY_CATALOG, StrategyCatalogEntry


@dataclass(frozen=True)
class StrategySelection:
    regime: MarketRegime
    active: tuple[StrategyCatalogEntry, ...]
    research: tuple[StrategyCatalogEntry, ...]
    excluded: tuple[StrategyCatalogEntry, ...]

    @property
    def active_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.active)

    @property
    def research_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.research)


class StrategySelector:
    """Select strategy families whose declared regime fit matches the market.

    This selector does not claim that a matching strategy is profitable. It is
    a research-routing layer: ACTIVE_ANALYSIS/BASELINE entries may be used by
    analysis, while RESEARCH entries remain explicitly separated until they
    pass out-of-sample approval.
    """

    ACTIVE_STATUSES = {"ACTIVE_ANALYSIS", "BASELINE"}
    RESEARCH_STATUSES = {"RESEARCH", "PLANNED_RESEARCH"}

    def __init__(
        self,
        catalog: tuple[StrategyCatalogEntry, ...] = STRATEGY_CATALOG,
    ) -> None:
        self.catalog = tuple(catalog)

    def select(self, regime: MarketRegime) -> StrategySelection:
        if regime is MarketRegime.UNKNOWN:
            active = tuple(
                item
                for item in self.catalog
                if item.status in self.ACTIVE_STATUSES
            )
            research = tuple(
                item
                for item in self.catalog
                if item.status in self.RESEARCH_STATUSES
            )
            return StrategySelection(
                regime=regime,
                active=active,
                research=research,
                excluded=(),
            )

        regime_name = regime.value
        active: list[StrategyCatalogEntry] = []
        research: list[StrategyCatalogEntry] = []
        excluded: list[StrategyCatalogEntry] = []

        for item in self.catalog:
            if regime_name not in item.regime_fit:
                excluded.append(item)
                continue

            if item.status in self.ACTIVE_STATUSES:
                active.append(item)
            elif item.status in self.RESEARCH_STATUSES:
                research.append(item)
            else:
                excluded.append(item)

        return StrategySelection(
            regime=regime,
            active=tuple(active),
            research=tuple(research),
            excluded=tuple(excluded),
        )


DEFAULT_STRATEGY_SELECTOR = StrategySelector()
