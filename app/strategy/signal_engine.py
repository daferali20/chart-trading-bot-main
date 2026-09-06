from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.analysis.regime import DEFAULT_REGIME_ENGINE, MarketRegime, RegimeSnapshot
from app.strategy.breakout.alpha import BreakoutAlpha
from app.strategy.fusion import (
    AlphaSignal,
    DEFAULT_FUSION_ENGINE,
    FusionResult,
    SignalDirection,
)
from app.strategy.momentum.alpha import MomentumAlpha
from app.strategy.mtf.alpha import MultiTimeframeAlpha
from app.strategy.trend.alpha import TrendAlpha
from app.strategy.volume.alpha import VolumeAlpha
from app.strategy.wema5.alpha import WilliamsAlpha


@dataclass(frozen=True)
class SignalInsight:
    action: str
    direction: SignalDirection
    score: float
    confidence: float
    quality: float
    expected_pct: float | None
    horizon: str | None
    regime: MarketRegime
    regime_confidence: float
    entry: float
    alphas: tuple[AlphaSignal, ...]
    contributions: tuple[dict, ...]
    reasons: tuple[str, ...]


class SignalEngine:
    """Advanced analysis pipeline for one symbol.

    DATA -> FEATURES -> ALPHAS -> MARKET REGIME -> SIGNAL FUSION

    This class deliberately stops before Portfolio, Risk and Execution.
    """

    def __init__(
        self,
        *,
        buy_score_threshold: float = 65.0,
        sell_score_threshold: float = 65.0,
    ) -> None:
        self.buy_score_threshold = float(buy_score_threshold)
        self.sell_score_threshold = float(sell_score_threshold)
        self.alpha_models = (
            WilliamsAlpha(),
            MomentumAlpha(),
            TrendAlpha(),
            BreakoutAlpha(),
            VolumeAlpha(),
        )
        self.mtf_alpha = MultiTimeframeAlpha()

    def analyze(
        self,
        df: pd.DataFrame,
        *,
        market_df: pd.DataFrame | None = None,
        mtf_frames: Mapping[str, pd.DataFrame] | None = None,
    ) -> SignalInsight:
        features = DEFAULT_FEATURE_ENGINE.build(df)
        entry = float(features.iloc[-1]["close"])

        alphas: list[AlphaSignal] = [
            model.generate_alpha(features)
            for model in self.alpha_models
        ]
        if mtf_frames:
            alphas.append(self.mtf_alpha.generate_alpha(mtf_frames))

        if market_df is None:
            regime_snapshot = RegimeSnapshot(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                reasons=("Market benchmark not supplied",),
                metrics={},
            )
        else:
            regime_snapshot = DEFAULT_REGIME_ENGINE.classify(market_df)

        fused: FusionResult = DEFAULT_FUSION_ENGINE.fuse(
            alphas,
            regime=regime_snapshot.regime,
        )

        if fused.direction is SignalDirection.LONG and fused.score >= self.buy_score_threshold:
            action = "BUY"
        elif fused.direction is SignalDirection.SHORT and fused.score >= self.sell_score_threshold:
            action = "SELL"
        else:
            action = "HOLD"

        reasons = tuple(
            signal.reason
            for signal in alphas
            if signal.reason
        ) + tuple(regime_snapshot.reasons)

        return SignalInsight(
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


DEFAULT_SIGNAL_ENGINE = SignalEngine()
