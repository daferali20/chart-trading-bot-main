from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from app.research.validation.alpha_forward import AlphaForwardValidator
from app.strategy.breakout.alpha import BreakoutAlpha
from app.strategy.mean_reversion.alpha import MeanReversionAlpha
from app.strategy.momentum.alpha import MomentumAlpha
from app.strategy.trend.alpha import TrendAlpha
from app.strategy.volatility.alpha import VolatilityExpansionAlpha
from app.strategy.volume.alpha import VolumeAlpha
from app.strategy.wema5.alpha import WilliamsAlpha


MODEL_FACTORIES = {
    "williams": WilliamsAlpha,
    "momentum": MomentumAlpha,
    "trend": TrendAlpha,
    "breakout": BreakoutAlpha,
    "volume": VolumeAlpha,
    "mean_reversion": MeanReversionAlpha,
    "volatility": VolatilityExpansionAlpha,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Research-only forward edge validation for Alpha models. "
            "Signals execute at next-bar open; no orders are sent."
        )
    )
    parser.add_argument("csv", help="Historical OHLCV CSV path")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["mean_reversion", "volatility"],
        choices=tuple(MODEL_FACTORIES),
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=[1, 3, 5, 10],
        help="Forward bars to evaluate",
    )
    parser.add_argument(
        "--count-repeated-signals",
        action="store_true",
        help="Count every directional bar instead of independent signal episodes",
    )
    parser.add_argument("--json", default="", help="Optional JSON report path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = pd.read_csv(args.csv)
    validator = AlphaForwardValidator(
        horizons=args.horizons,
        deduplicate_episodes=not args.count_repeated_signals,
    )

    reports = []
    print("=" * 106)
    print(f"ALPHA FORWARD RESEARCH — {Path(args.csv).name}")
    print("NEXT-BAR OPEN EXECUTION | RESEARCH ONLY | NO ORDERS SENT")
    print("=" * 106)

    for model_key in args.models:
        model = MODEL_FACTORIES[model_key]()
        result = validator.validate(model, data)
        report = {
            "model": model.name,
            "raw_directional_signals": result.raw_directional_signals,
            "independent_signal_episodes": result.independent_signal_episodes,
            "summaries": [asdict(item) for item in result.summaries],
        }
        reports.append(report)

        print()
        print(
            f"{model.name}: raw={result.raw_directional_signals} | "
            f"independent episodes={result.independent_signal_episodes}"
        )
        print(
            f"{'H':>4} {'N':>5} {'LONG':>5} {'SHORT':>5} "
            f"{'HIT':>8} {'AVG':>10} {'MEDIAN':>10} {'MFE':>10} {'MAE':>10}"
        )
        for item in result.summaries:
            print(
                f"{item.horizon_bars:>4d} {item.samples:>5d} "
                f"{item.long_samples:>5d} {item.short_samples:>5d} "
                f"{item.hit_rate:>7.1%} "
                f"{item.average_signed_return_pct:>+9.3f}% "
                f"{item.median_signed_return_pct:>+9.3f}% "
                f"{item.average_mfe_pct:>+9.3f}% "
                f"{item.average_mae_pct:>+9.3f}%"
            )

    if args.json:
        destination = Path(args.json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(reports, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {destination}")


if __name__ == "__main__":
    main()
