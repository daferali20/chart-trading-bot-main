from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from app.research.scoring.alpha_breadth import (
    AlphaBreadthEvaluator,
    SymbolAlphaEvidence,
)
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


def parse_symbol_file(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "Symbol files must be SYMBOL=path.csv, e.g. AAPL=data/AAPL.csv"
        )
    symbol, path = value.split("=", 1)
    symbol = symbol.strip().upper()
    file_path = Path(path.strip())
    if not symbol or not str(file_path):
        raise argparse.ArgumentTypeError("Invalid SYMBOL=path.csv value")
    return symbol, file_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-symbol Alpha evidence matrix. Research-only; signals use "
            "next-bar open and independent episodes by default."
        )
    )
    parser.add_argument(
        "symbol_files",
        nargs="+",
        type=parse_symbol_file,
        help="One or more SYMBOL=path.csv inputs",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODEL_FACTORIES),
        choices=tuple(MODEL_FACTORIES),
    )
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--market-csv", default="")
    parser.add_argument("--regimes", nargs="+", default=None)
    parser.add_argument("--min-symbols", type=int, default=5)
    parser.add_argument("--min-samples-per-symbol", type=int, default=10)
    parser.add_argument("--min-positive-breadth", type=float, default=0.60)
    parser.add_argument("--min-median-hit", type=float, default=0.50)
    parser.add_argument("--json", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.regimes and not args.market_csv:
        raise SystemExit("--regimes requires --market-csv")

    horizon = max(1, int(args.horizon))
    validator = AlphaForwardValidator(horizons=(horizon,), deduplicate_episodes=True)

    regime_by_date = None
    if args.market_csv:
        regime_by_date = validator.build_regime_timeline(pd.read_csv(args.market_csv))
    allowed_regimes = (
        None if not args.regimes else tuple(value.upper() for value in args.regimes)
    )

    breadth_evaluator = AlphaBreadthEvaluator(
        minimum_symbols=max(1, int(args.min_symbols)),
        minimum_samples_per_symbol=max(1, int(args.min_samples_per_symbol)),
        minimum_positive_breadth=float(args.min_positive_breadth),
        minimum_median_hit_rate=float(args.min_median_hit),
    )

    symbol_data = {
        symbol: pd.read_csv(path)
        for symbol, path in args.symbol_files
    }
    reports = []

    print("=" * 118)
    print("CROSS-SYMBOL ALPHA EVIDENCE MATRIX")
    print(f"HORIZON={horizon} bars | NEXT-BAR OPEN | INDEPENDENT EPISODES")
    if args.market_csv:
        print(f"BENCHMARK={Path(args.market_csv).name}")
    if allowed_regimes:
        print(f"REGIME FILTER={', '.join(allowed_regimes)}")
    print("RESEARCH ONLY — NO ORDERS SENT")
    print("=" * 118)

    for model_key in args.models:
        model = MODEL_FACTORIES[model_key]()
        symbol_evidence = []
        symbol_rows = []

        for symbol, data in symbol_data.items():
            validation = validator.validate(
                model,
                data,
                regime_by_date=regime_by_date,
                allowed_regimes=allowed_regimes,
            )
            summary = validation.summaries[0]
            symbol_evidence.append(SymbolAlphaEvidence(symbol, summary))
            symbol_rows.append(
                {
                    "symbol": symbol,
                    "raw_signals": validation.raw_directional_signals,
                    "regime_eligible_signals": validation.regime_eligible_directional_signals,
                    "episodes": validation.independent_signal_episodes,
                    **asdict(summary),
                }
            )

        breadth = breadth_evaluator.evaluate(symbol_evidence)
        status = "PASS" if breadth.eligible else "MORE_EVIDENCE"
        report = {
            "model": model.name,
            "status": status,
            "symbols": symbol_rows,
            "breadth": asdict(breadth),
        }
        reports.append(report)

        print()
        print(
            f"{model.name} — {status} | "
            f"qualified_symbols={breadth.symbols_with_min_samples}/{breadth.symbols_tested} | "
            f"breadth={breadth.positive_breadth:.1%} | "
            f"median_return={breadth.median_symbol_signed_return_pct:+.3f}% | "
            f"median_hit={breadth.median_symbol_hit_rate:.1%}"
        )
        print(
            f"  {'SYMBOL':<8} {'N':>4} {'HIT':>8} {'AVG':>10} "
            f"{'MED':>10} {'MFE':>10} {'MAE':>10}"
        )
        for row in symbol_rows:
            print(
                f"  {row['symbol']:<8} {row['samples']:>4d} "
                f"{row['hit_rate']:>7.1%} "
                f"{row['average_signed_return_pct']:>+9.3f}% "
                f"{row['median_signed_return_pct']:>+9.3f}% "
                f"{row['average_mfe_pct']:>+9.3f}% "
                f"{row['average_mae_pct']:>+9.3f}%"
            )
        for reason in breadth.reasons:
            print(f"  - {reason}")

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
