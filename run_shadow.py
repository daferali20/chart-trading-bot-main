from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.analysis.feature_engine import DEFAULT_FEATURE_ENGINE
from app.analysis.regime import DEFAULT_REGIME_ENGINE
from app.broker.ibkr import IBKRClient
from app.config import settings
from app.events.factory import build_serpapi_news_service
from app.shadow import DEFAULT_SHADOW_EVALUATOR
from app.shadow_news import DEFAULT_NEWS_SHADOW_EVALUATOR


def _optional_float(value) -> float | None:
    return None if pd.isna(value) else float(value)


async def _run_news_shadow(symbol: str, symbol_df, market_df) -> None:
    if not settings.news_shadow_enabled:
        print("News shadow: DISABLED")
        return

    if not settings.serpapi_api_key:
        print("News shadow: SKIPPED — SERPAPI_API_KEY is not configured")
        return

    try:
        features = DEFAULT_FEATURE_ENGINE.build(symbol_df)
        latest = features.iloc[-1]
        regime = DEFAULT_REGIME_ENGINE.classify(market_df).regime
        now = datetime.now(timezone.utc)
        lookback = timedelta(hours=max(1, int(settings.news_shadow_lookback_hours)))

        news_service = build_serpapi_news_service()
        news_result = await news_service.analyze(
            symbol,
            start=now - lookback,
            end=now,
            market_regime=regime,
            momentum20=_optional_float(latest.get("momentum20")),
            rvol=_optional_float(latest.get("rvol20")),
        )

        comparison = DEFAULT_NEWS_SHADOW_EVALUATOR.compare(
            symbol,
            symbol_df,
            forecasts=news_result.forecasts,
            market_df=market_df,
        )
        log_path = DEFAULT_NEWS_SHADOW_EVALUATOR.append_log(comparison)

        print()
        print("News-aware shadow:")
        print(
            f"  Technical: {comparison.technical_action} | "
            f"score={comparison.technical_score:.2f}"
        )
        if comparison.event_type is None:
            print("  Event: none in configured lookback")
        else:
            print(
                f"  Event: {comparison.event_type} | {comparison.event_direction} | "
                f"impact={comparison.event_impact_score:.1f} | "
                f"confidence={comparison.event_confidence:.1f}%"
            )
            print(
                f"  P(up)={comparison.probability_up:.1%} | "
                f"P(down)={comparison.probability_down:.1%}"
            )
        print(
            f"  Combined: {comparison.combined_action} | "
            f"score={comparison.combined_score:.2f} | "
            f"delta={comparison.score_delta:+.2f}"
        )
        print(f"  Decision changed: {'YES' if comparison.decision_changed else 'NO'}")
        print(f"  News shadow log: {log_path}")
    except Exception as exc:
        # News is deliberately non-critical in shadow mode. A provider outage,
        # quota error or malformed story must never disable technical analysis.
        print(f"News shadow: ERROR — {exc}")


async def main() -> None:
    client = IBKRClient()
    symbol = settings.symbol.upper()

    try:
        symbol_df = await client.historical_bars(symbol)
        market_df = symbol_df if symbol == "SPY" else await client.historical_bars("SPY")

        comparison = DEFAULT_SHADOW_EVALUATOR.compare(
            symbol,
            symbol_df,
            market_df=market_df,
        )
        log_path = DEFAULT_SHADOW_EVALUATOR.append_log(comparison)

        print(f"Symbol: {comparison.symbol}")
        print(
            "Legacy: "
            f"{comparison.legacy_action} | score={comparison.legacy_score:.2f}"
        )
        print(
            "Advanced: "
            f"{comparison.advanced_action} | "
            f"score={comparison.advanced_score:.2f} | "
            f"confidence={comparison.advanced_confidence:.2f}% | "
            f"quality={comparison.advanced_quality:.2f}%"
        )
        print(f"Market regime: {comparison.market_regime}")
        print(f"Agreement: {'YES' if comparison.agreement else 'NO'}")
        print(f"Score delta: {comparison.score_delta:+.2f}")
        print(f"Shadow log: {log_path}")

        await _run_news_shadow(symbol, symbol_df, market_df)
        print("NO ORDER WAS SENT — SHADOW MODE ONLY")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
