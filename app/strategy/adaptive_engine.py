from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.analysis.regime import DEFAULT_REGIME_ENGINE, MarketRegime, RegimeSnapshot
from app.strategy.breakout.alpha import BreakoutAlpha
from app.strategy.fusion import DEFAULT_FUSION_ENGINE, SignalDirection
from app.strategy.mean_reversion.alpha import MeanReversionAlpha
from app.strategy.momentum.alpha import MomentumAlpha
from app.strategy.mtf.alpha import MultiTimeframeAlpha
from app.strategy.selector import DEFAULT_STRATEGY_SELECTOR, StrategySelection
from app.strategy.signal_engine import SignalInsight
from app.strategy.trend.alpha import TrendAlpha
from app.strategy.volatility.alpha import VolatilityExpansionAlpha
from app.strategy.volume.alpha import VolumeAlpha
from app.strategy.wema5.alpha import WilliamsAlpha


@dataclass(frozen=True)
class AdaptiveSignalResult:
    insight: SignalInsight
    selection: StrategySelection
    selected_model_names: tuple[str, ...]
    research_models_included: bool


class AdaptiveSignalEngine:
    """Research-only signal engine that routes alpha families by market regime.

    The production DEFAULT_SIGNAL_ENGINE remains unchanged. Research models are
    excluded unless ``include_research=True`` is explicitly requested.
    """

    def __init__(
        self,
        *,
        include_research: bool = False,
        buy_score_threshold: float = 65.0,
        sell_score_threshold: float = 65.0,
    ) -> None:
        self.include_research = bool(include_research)
        self.buy_score_threshold = float(buy_score_threshold)
        self.sell_score_threshold = float(sell_score_threshold)
        self.models = {
            "WEMA5_BASELINE_v1": WilliamsAlpha(),
            "MomentumAlpha": MomentumAlpha(),
            "TrendAlpha": TrendAlpha(),
            "BreakoutAlpha": BreakoutAlpha(),
            "VolumeAlpha": VolumeAlpha(),
            "MeanReversionAlpha": MeanReversionAlpha(),
            "VolatilityExpansionAlpha": VolatilityExpansionAlpha(),
        }
        self.mtf_alpha = MultiTimeframeAlpha()

    def _action(self, direction: SignalDirection, score: float) -> str:
        if direction is SignalDirection.LONG and score >= self.buy_score_threshold:
            return "BUY"
        if direction is SignalDirection.SHORT and score >= self.sell_score_threshold:
            return "SELL"
        return "HOLD"

    def analyze(
        self,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> AdaptiveSignalResult:
        features = DEFAULT_FEATURE_ENGINE.build(df)
        entry = float(features.iloc[-1]["close"])

        if market_df is None:
            regime_snapshot = RegimeSnapshot(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                reasons=("Market benchmark not supplied",),
                metrics={},
            )
        else:
            regime_snapshot = DEFAULT_REGIME_ENGINE.classify(market_df)

        selection = DEFAULT_STRATEGY_SELECTOR.select(regime_snapshot.regime)
        selected_names = list(selection.active_names)
        if self.include_research:
            selected_names.extend(selection.research_names)

        alphas = []
        for name in selected_names:
            model = self.models.get(name)
            if model is not None:
                alphas.append(model.generate_alpha(features))

        if mtf_frames and "MultiTimeframeAlpha" in selected_names:
            alphas.append(self.mtf_alpha.generate_alpha(mtf_frames))

        fused = DEFAULT_FUSION_ENGINE.fuse(
            alphas,
            regime=regime_snapshot.regime,
        )
        action = self._action(fused.direction, fused.score)

        reasons = tuple(
            alpha.reason for alpha in alphas if alpha.reason
        ) + tuple(regime_snapshot.reasons)
        if not alphas:
            reasons = reasons + ("No approved alpha family selected for current regime",)

        insight = SignalInsight(
            action=action,
            direction=fused.direction,
            score=fused.score,
            confidence=fused.confidence,
            quality=fused.quality,
            expected_pct=fused.expected_pct,
            horizon=fused.horizon,
            regime=fused.regime,
            regime_confidence=regime_snapshot.confidence,
            entry=entry,
            alphas=tuple(alphas),
            contributions=fused.contributions,
            reasons=reasons,
        )

        actually_selected = tuple(
            name
            for name in selected_names
            if name in self.models or (name == "MultiTimeframeAlpha" and mtf_frames)
        )
        return AdaptiveSignalResult(
            insight=insight,
            selection=selection,
            selected_model_names=actually_selected,
            research_models_included=self.include_research,
        )


DEFAULT_ADAPTIVE_SIGNAL_ENGINE = AdaptiveSignalEngine()
