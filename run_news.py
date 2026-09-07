from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from app.events.factory import build_serpapi_news_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research-only SerpAPI news/event analysis. No orders are sent."
    )
    parser.add_argument("symbol", help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--company", default="", help="Optional company name alias")
    parser.add_argument("--days", type=int, default=7, help="Recent-news lookback window")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper().strip()
    aliases = {symbol: args.company.strip()} if args.company.strip() else None
    service = build_serpapi_news_service(aliases=aliases)

    now = datetime.now(timezone.utc)
    result = await service.analyze(
        symbol,
        start=now - timedelta(days=max(1, args.days)),
        end=now,
    )

    print("=" * 80)
    print(f"NEWS INTELLIGENCE — {symbol}")
    print("RESEARCH ONLY — NO ORDERS SENT")
    print("=" * 80)
    print(f"Events: {len(result.events)}")
    print()

    print("News events:")
    for number, event in enumerate(result.events, start=1):
        print(f"{number:02d}. {event.published_at.isoformat()} | {event.source}")
        print(f"    {event.headline}")
        print(
            f"    type={event.event_type.value} "
            f"sentiment={event.sentiment:+.2f} "
            f"relevance={event.relevance:.2f}"
        )
        if event.url:
            print(f"    {event.url}")
        print()

    if result.forecasts:
        print("Ranked impact forecasts:")
        for number, forecast in enumerate(result.forecasts, start=1):
            print(
                f"{number:02d}. {forecast.event_type.value} | {forecast.direction} | "
                f"P(up)={forecast.probability_up:.1%} "
                f"P(down)={forecast.probability_down:.1%} "
                f"P(neutral)={forecast.probability_neutral:.1%} | "
                f"move={forecast.expected_move_low_pct:.1f}%–"
                f"{forecast.expected_move_high_pct:.1f}% | "
                f"impact={forecast.impact_score:.1f} | "
                f"confidence={forecast.confidence:.1f}%"
            )

        strongest = result.strongest
        print()
        print("Strongest event forecast:")
        print(
            f"  {strongest.event_type.value} | {strongest.direction} | "
            f"impact={strongest.impact_score:.1f} | confidence={strongest.confidence:.1f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())
