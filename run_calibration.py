from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

from app.broker.ibkr import IBKRClient
from app.config import settings
from app.research.calibration import (
    DirectionalProbabilityCalibrator,
    ReliabilityCalibrator,
    build_snapshot,
)
from app.research.outcomes import ForwardOutcome, ForwardOutcomeEvaluator


ENGINE_SOURCES = (
    ("legacy", Path("logs/shadow_decisions.jsonl"), "legacy_action"),
    ("signal_v2", Path("logs/shadow_decisions.jsonl"), "advanced_action"),
    ("adaptive", Path("logs/adaptive_shadow_decisions.jsonl"), "adaptive_action"),
    ("news_aware", Path("logs/news_shadow_decisions.jsonl"), "combined_action"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a research-only calibration snapshot from matured shadow outcomes. "
            "No orders are sent."
        )
    )
    parser.add_argument("--symbol", default="", help="Ticker; defaults to SYMBOL from .env")
    parser.add_argument("--horizon", type=int, default=3, help="Forward horizon in bars")
    parser.add_argument("--min-samples", type=int, default=30, help="Minimum matured samples before any adjustment")
    parser.add_argument("--duration", default="30 D", help="IBKR history duration used for outcome matching")
    parser.add_argument("--timeframe", default="", help="Optional IBKR bar size override; defaults to TIMEFRAME")
    parser.add_argument("--validity-days", type=int, default=30, help="Days before learned calibration expires")
    parser.add_argument(
        "--output",
        default="logs/calibration/latest.json",
        help="Local calibration snapshot path",
    )
    return parser.parse_args()


def load_entries(path: Path, symbol: str) -> list[dict]:
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


def directional_action(direction: str | None) -> str | None:
    value = str(direction or "").upper()
    if value in {"LONG", "UP", "BUY"}:
        return "BUY"
    if value in {"SHORT", "DOWN", "SELL"}:
        return "SELL"
    return None


def matured_outcome(
    evaluator: ForwardOutcomeEvaluator,
    *,
    observed_at: str | None,
    action: str | None,
    bars,
) -> ForwardOutcome | None:
    if not observed_at or str(action or "").upper() not in {"BUY", "SELL"}:
        return None
    items = evaluator.evaluate(
        observed_at=observed_at,
        action=str(action).upper(),
        bars=bars,
    )
    return items[0] if items else None


def add_unique_outcome(
    bucket: dict[str, list[ForwardOutcome]],
    seen: set[tuple[str, str]],
    *,
    key: str,
    outcome: ForwardOutcome | None,
) -> None:
    if outcome is None:
        return
    token = (key, outcome.anchor_date)
    if token in seen:
        return
    seen.add(token)
    bucket[key].append(outcome)


async def main() -> None:
    args = parse_args()
    symbol = (args.symbol or settings.symbol).upper().strip()
    horizon = max(1, int(args.horizon))
    minimum_samples = max(1, int(args.min_samples))

    client = IBKRClient()
    evaluator = ForwardOutcomeEvaluator(horizons=(horizon,))
    reliability = ReliabilityCalibrator(minimum_samples=minimum_samples)
    probability = DirectionalProbabilityCalibrator(minimum_samples=minimum_samples)

    try:
        bars = await client.historical_bars(
            symbol,
            duration=args.duration,
            timeframe=(args.timeframe.strip() or None),
        )

        engine_outcomes: dict[str, list[ForwardOutcome]] = defaultdict(list)
        alpha_outcomes: dict[str, list[ForwardOutcome]] = defaultdict(list)
        event_samples: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        training_boundaries: list[str] = []

        engine_seen: set[tuple[str, str]] = set()
        alpha_seen: set[tuple[str, str]] = set()
        event_seen: set[tuple[str, str]] = set()

        for label, path, action_key in ENGINE_SOURCES:
            for entry in load_entries(path, symbol):
                result = matured_outcome(
                    evaluator,
                    observed_at=entry.get("observed_at"),
                    action=entry.get(action_key),
                    bars=bars,
                )
                if result is not None:
                    training_boundaries.append(result.future_date)
                add_unique_outcome(
                    engine_outcomes,
                    engine_seen,
                    key=label,
                    outcome=result,
                )

        for entry in load_entries(Path("logs/adaptive_shadow_decisions.jsonl"), symbol):
            regime = str(entry.get("market_regime") or "UNKNOWN").upper()
            for alpha in entry.get("alpha_signals") or ():
                if not isinstance(alpha, dict):
                    continue
                name = str(alpha.get("name") or "").strip()
                action = directional_action(alpha.get("direction"))
                if not name or action is None:
                    continue
                key = f"{name}|{regime}"
                result = matured_outcome(
                    evaluator,
                    observed_at=entry.get("observed_at"),
                    action=action,
                    bars=bars,
                )
                if result is not None:
                    training_boundaries.append(result.future_date)
                add_unique_outcome(
                    alpha_outcomes,
                    alpha_seen,
                    key=key,
                    outcome=result,
                )

        for entry in load_entries(Path("logs/news_shadow_decisions.jsonl"), symbol):
            event_type = str(entry.get("event_type") or "").upper().strip()
            event_direction = str(entry.get("event_direction") or "").upper().strip()
            action = directional_action(event_direction)
            if not event_type or action is None:
                continue

            if action == "BUY":
                predicted = entry.get("probability_up")
            else:
                predicted = entry.get("probability_down")
            if predicted is None:
                continue

            result = matured_outcome(
                evaluator,
                observed_at=entry.get("observed_at"),
                action=action,
                bars=bars,
            )
            if result is None:
                continue
            training_boundaries.append(result.future_date)

            token = (event_type, result.anchor_date)
            if token in event_seen:
                continue
            event_seen.add(token)
            event_samples[event_type].append((float(predicted), result.correct_direction))

        engine_estimates = tuple(
            reliability.estimate(key, values)
            for key, values in sorted(engine_outcomes.items())
        )
        alpha_estimates = tuple(
            reliability.estimate(key, values)
            for key, values in sorted(alpha_outcomes.items())
        )
        event_estimates = tuple(
            probability.estimate(key, values)
            for key, values in sorted(event_samples.items())
        )

        training_end_at = max(training_boundaries) if training_boundaries else None
        snapshot = build_snapshot(
            horizon_bars=horizon,
            minimum_samples=minimum_samples,
            alpha_estimates=alpha_estimates,
            event_estimates=event_estimates,
            engine_estimates=engine_estimates,
            training_end_at=training_end_at,
            source_symbol=symbol,
            validity_days=max(1, int(args.validity_days)),
        )
        output = snapshot.save(args.output)

        print("=" * 92)
        print(f"RESEARCH CALIBRATION — {symbol}")
        print(f"HORIZON={horizon} bars | MIN_SAMPLES={minimum_samples}")
        print("NO ORDERS SENT — CALIBRATION STATE IS RESEARCH-ONLY")
        print("=" * 92)

        print("\nEngine reliability:")
        if not engine_estimates:
            print("  no matured engine outcomes")
        for item in engine_estimates:
            status = "ELIGIBLE" if item.eligible else "WAIT"
            print(
                f"  {item.key:14s} {status:8s} n={item.samples:3d} "
                f"hit={item.hit_rate:6.1%} post={item.posterior_hit_rate:6.1%} "
                f"avg={item.average_signed_return_pct:+7.3f}% "
                f"weight={item.weight_multiplier:.3f}"
            )

        print("\nAlpha reliability by regime:")
        if not alpha_estimates:
            print("  no per-alpha matured outcomes yet; collect new adaptive shadow logs")
        for item in alpha_estimates:
            status = "ELIGIBLE" if item.eligible else "WAIT"
            print(
                f"  {item.key:34s} {status:8s} n={item.samples:3d} "
                f"hit={item.hit_rate:6.1%} avg={item.average_signed_return_pct:+7.3f}% "
                f"weight={item.weight_multiplier:.3f}"
            )

        print("\nEvent probability calibration:")
        if not event_estimates:
            print("  no matured directional event outcomes")
        for item in event_estimates:
            status = "ELIGIBLE" if item.eligible else "WAIT"
            print(
                f"  {item.key:18s} {status:8s} n={item.samples:3d} "
                f"pred={item.mean_predicted_probability:6.1%} "
                f"actual={item.empirical_hit_rate:6.1%} "
                f"offset={item.probability_offset:+.3f}"
            )

        print(f"\nTraining data ends: {snapshot.training_end_at or 'NO MATURED OUTCOMES'}")
        print(f"Snapshot expires:   {snapshot.valid_until}")
        print(f"Calibration snapshot: {output}")
        if not snapshot.alpha_weights and not snapshot.event_probability_offsets:
            print(
                "No learned alpha/news adjustment is active yet. This is expected "
                "until the minimum number of unique matured market bars is reached."
            )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
