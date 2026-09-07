from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.broker.ibkr import IBKRClient
from app.config import settings
from app.research.outcomes import ForwardOutcomeEvaluator


LOG_SOURCES = (
    ("legacy", Path("logs/shadow_decisions.jsonl"), "legacy_action"),
    ("signal_v2", Path("logs/shadow_decisions.jsonl"), "advanced_action"),
    ("adaptive", Path("logs/adaptive_shadow_decisions.jsonl"), "adaptive_action"),
    ("news_aware", Path("logs/news_shadow_decisions.jsonl"), "combined_action"),
)


def _load_entries(path: Path, symbol: str) -> list[dict]:
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(item.get("symbol", "")).upper() == symbol.upper():
                entries.append(item)
    return entries


async def main() -> None:
    symbol = settings.symbol.upper()
    client = IBKRClient()
    evaluator = ForwardOutcomeEvaluator(horizons=(1, 3, 5))

    try:
        bars = await client.historical_bars(symbol)
        print("=" * 84)
        print(f"SHADOW OUTCOME REPORT — {symbol}")
        print("FORWARD HORIZONS: 1 / 3 / 5 BARS")
        print("RESEARCH ONLY — NO ORDERS SENT")
        print("=" * 84)

        any_results = False
        for label, path, action_key in LOG_SOURCES:
            outcomes = []
            for entry in _load_entries(path, symbol):
                observed_at = entry.get("observed_at")
                action = entry.get(action_key)
                if not observed_at or not action:
                    continue
                outcomes.extend(
                    evaluator.evaluate(
                        observed_at=observed_at,
                        action=action,
                        bars=bars,
                    )
                )

            summary = evaluator.summarize(outcomes)
            if summary.samples == 0:
                print(f"{label:12s}: no matured outcomes yet")
                continue

            any_results = True
            print(
                f"{label:12s}: samples={summary.samples:3d} | "
                f"hit={summary.hit_rate:6.1%} | "
                f"avg signed={summary.average_signed_return_pct:+7.3f}% | "
                f"median={summary.median_signed_return_pct:+7.3f}% | "
                f"avg MFE={summary.average_mfe_pct:+7.3f}% | "
                f"avg MAE={summary.average_mae_pct:+7.3f}%"
            )

        if not any_results:
            print()
            print(
                "No decisions have enough future bars yet. Keep collecting shadow "
                "decisions; the report will mature automatically as new bars arrive."
            )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
