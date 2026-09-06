from __future__ import annotations

import asyncio

from app.broker.ibkr import IBKRClient
from app.config import settings
from app.shadow import DEFAULT_SHADOW_EVALUATOR


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
        print("NO ORDER WAS SENT — SHADOW MODE ONLY")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
