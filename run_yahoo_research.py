from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from app.data.providers import YahooDataProvider
from app.research.datasets.yahoo import YahooDatasetBuilder
from app.research.scoring.alpha_breadth import AlphaBreadthEvaluator, SymbolAlphaEvidence
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

MODEL_REGIME_FIT = {
    "williams": ("BULL", "SIDEWAYS"),
    "momentum": ("BULL",),
    "trend": ("BULL", "BEAR"),
    "breakout": ("BULL", "HIGH_VOLATILITY"),
    "volume": ("BULL", "SIDEWAYS", "HIGH_VOLATILITY"),
    "mean_reversion": ("SIDEWAYS",),
    "volatility": ("BULL", "HIGH_VOLATILITY"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Yahoo daily history and run cross-symbol Alpha research. "
            "Research only; no broker/execution imports or orders."
        )
    )
    parser.add_argument(
        "--universe",
        default="research/universes/us_research_30.txt",
        help="One ticker per line; # comments supported",
    )
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--period", default="5y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--extra-benchmarks", nargs="*", default=["QQQ", "IWM"])
    parser.add_argument("--horizons", nargs="+", type=int, default=[3, 5, 10])
    parser.add_argument(
        "--models",
        nargs="+",
        choices=tuple(MODEL_FACTORIES),
        default=list(MODEL_FACTORIES),
    )
    parser.add_argument("--min-symbols", type=int, default=10)
    parser.add_argument("--min-samples-per-symbol", type=int, default=10)
    parser.add_argument("--min-positive-breadth", type=float, default=0.60)
    parser.add_argument("--min-median-hit", type=float, default=0.50)
    parser.add_argument("--output-root", default="data/yahoo")
    parser.add_argument("--report", default="logs/yahoo_research/latest.json")
    return parser.parse_args()


def read_universe(path: str | Path) -> list[str]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Universe file not found: {source}")
    symbols: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        symbols.append(value.upper())
    return symbols


def unique_symbols(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        symbol = str(raw).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def dataset_path_map(entries) -> dict[str, Path]:
    return {item.symbol.upper(): Path(item.path) for item in entries}


def breadth_payload(evidence) -> dict:
    return asdict(evidence)


async def main() -> None:
    args = parse_args()
    universe = unique_symbols(read_universe(args.universe) + list(args.symbols))
    benchmark = args.benchmark.upper()
    extra_benchmarks = unique_symbols(args.extra_benchmarks)
    fetch_symbols = unique_symbols([benchmark, *extra_benchmarks, *universe])

    dataset_dir = Path(args.output_root) / f"{args.period}_{args.interval}"
    provider = YahooDataProvider(
        period=args.period,
        interval=args.interval,
        auto_adjust=True,
        repair=True,
    )
    builder = YahooDatasetBuilder(provider, output_dir=dataset_dir, retries=2)

    print("=" * 112)
    print("YAHOO HISTORICAL RESEARCH")
    print(
        f"UNIVERSE={len(universe)} stocks | PERIOD={args.period} | "
        f"INTERVAL={args.interval} | BENCHMARK={benchmark}"
    )
    print("ADJUSTED OHLC + REPAIR | RESEARCH ONLY — NO ORDERS SENT")
    print("=" * 112)
    print(f"Downloading {len(fetch_symbols)} symbols...")

    build_report = await builder.build(fetch_symbols)
    manifest_path = dataset_dir / "manifest.json"
    build_report.save(manifest_path)
    paths = dataset_path_map(build_report.entries)

    print(
        f"Downloaded: {len(build_report.entries)} | "
        f"Errors: {len(build_report.errors)} | Manifest: {manifest_path}"
    )
    for symbol, error in sorted(build_report.errors.items()):
        print(f"  DOWNLOAD ERROR {symbol}: {error}")

    if benchmark not in paths:
        raise RuntimeError(f"Benchmark {benchmark} failed to download; regime research cannot continue")

    available_universe = [symbol for symbol in universe if symbol in paths]
    if len(available_universe) < args.min_symbols:
        raise RuntimeError(
            f"Only {len(available_universe)} universe symbols downloaded; "
            f"need at least {args.min_symbols}"
        )

    benchmark_data = pd.read_csv(paths[benchmark])
    validator = AlphaForwardValidator(
        horizons=args.horizons,
        deduplicate_episodes=True,
    )
    regime_timeline = validator.build_regime_timeline(benchmark_data)
    breadth_evaluator = AlphaBreadthEvaluator(
        minimum_symbols=args.min_symbols,
        minimum_samples_per_symbol=args.min_samples_per_symbol,
        minimum_positive_breadth=args.min_positive_breadth,
        minimum_median_hit_rate=args.min_median_hit,
    )

    report_models = []
    print()
    print("Running overall + regime-fit Alpha breadth validation...")

    for model_key in args.models:
        model = MODEL_FACTORIES[model_key]()
        fitted_regimes = MODEL_REGIME_FIT[model_key]
        overall_by_horizon = {h: [] for h in validator.horizons}
        fitted_by_horizon = {h: [] for h in validator.horizons}
        symbol_rows = []

        for symbol in available_universe:
            data = pd.read_csv(paths[symbol])
            overall = validator.validate(model, data)
            fitted = validator.validate(
                model,
                data,
                regime_by_date=regime_timeline,
                allowed_regimes=fitted_regimes,
            )

            overall_map = {item.horizon_bars: item for item in overall.summaries}
            fitted_map = {item.horizon_bars: item for item in fitted.summaries}
            for horizon in validator.horizons:
                overall_by_horizon[horizon].append(
                    SymbolAlphaEvidence(symbol, overall_map[horizon])
                )
                fitted_by_horizon[horizon].append(
                    SymbolAlphaEvidence(symbol, fitted_map[horizon])
                )

            symbol_rows.append(
                {
                    "symbol": symbol,
                    "overall_raw_signals": overall.raw_directional_signals,
                    "overall_episodes": overall.independent_signal_episodes,
                    "regime_eligible_signals": fitted.regime_eligible_directional_signals,
                    "regime_episodes": fitted.independent_signal_episodes,
                    "overall": [asdict(item) for item in overall.summaries],
                    "regime_fit": [asdict(item) for item in fitted.summaries],
                }
            )

        horizon_rows = []
        for horizon in validator.horizons:
            overall_breadth = breadth_evaluator.evaluate(overall_by_horizon[horizon])
            fitted_breadth = breadth_evaluator.evaluate(fitted_by_horizon[horizon])
            horizon_rows.append(
                {
                    "horizon_bars": horizon,
                    "overall": breadth_payload(overall_breadth),
                    "regime_fit": breadth_payload(fitted_breadth),
                }
            )

        preferred = max(
            horizon_rows,
            key=lambda row: (
                row["regime_fit"]["eligible"],
                row["regime_fit"]["positive_breadth"],
                row["regime_fit"]["median_symbol_signed_return_pct"],
            ),
        )
        status = "PASS" if preferred["regime_fit"]["eligible"] else "MORE_EVIDENCE"
        print(
            f"{model.name:<28} {status:<13} | "
            f"regimes={','.join(fitted_regimes):<24} | "
            f"best_h={preferred['horizon_bars']:>2} | "
            f"breadth={preferred['regime_fit']['positive_breadth']:.1%} | "
            f"median={preferred['regime_fit']['median_symbol_signed_return_pct']:+.3f}% | "
            f"hit={preferred['regime_fit']['median_symbol_hit_rate']:.1%}"
        )

        report_models.append(
            {
                "key": model_key,
                "model": model.name,
                "regime_fit": fitted_regimes,
                "status": status,
                "preferred_horizon_bars": preferred["horizon_bars"],
                "horizons": horizon_rows,
                "symbols": symbol_rows,
            }
        )

    report = {
        "source": "Yahoo Finance via yfinance",
        "period": args.period,
        "interval": args.interval,
        "adjusted_ohlc": True,
        "repair": True,
        "benchmark": benchmark,
        "extra_benchmarks": extra_benchmarks,
        "universe_requested": universe,
        "universe_available": available_universe,
        "download_errors": build_report.errors,
        "manifest": str(manifest_path),
        "models": report_models,
    }

    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nResearch report: {destination}")
    print("NO ORDER WAS SENT — YAHOO DATA IS RESEARCH-ONLY")


if __name__ == "__main__":
    asyncio.run(main())
