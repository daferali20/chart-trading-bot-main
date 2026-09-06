from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.strategy.fusion import AlphaSignal


class AlphaModel(ABC):
    """Common contract for independent strategy/alpha modules."""

    name: str
    version: str
    required_features: tuple[str, ...] = ()

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("DataFrame is empty")
        if set(self.required_features).issubset(df.columns):
            return df
        return DEFAULT_FEATURE_ENGINE.build(df)

    @abstractmethod
    def generate_alpha(self, df: pd.DataFrame) -> AlphaSignal:
        raise NotImplementedError

    def parameters(self) -> Mapping[str, object]:
        return {}
