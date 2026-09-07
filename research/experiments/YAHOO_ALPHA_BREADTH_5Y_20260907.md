# Yahoo Alpha Breadth Research — 5Y Daily — 2026-09-07

## Purpose

Research-only cross-symbol evidence for the Alpha library. This report does **not** promote any strategy to live execution. A `PASS` below means only that the model passed the current cross-symbol breadth gate for the specified forward horizon and market-regime routing.

## Dataset

- Source: Yahoo Finance via `yfinance`
- Period: 5 years
- Interval: 1 day
- Adjusted OHLC: enabled
- Yahoo repair: enabled
- Benchmark / regime context: SPY
- Additional benchmarks downloaded: QQQ, IWM
- Equity universe: 30 diversified liquid US stocks
- Total downloaded symbols: 33
- Download errors: 0
- Rows per symbol: 1,255
- Date range: 2021-09-07 through 2026-09-04
- Signal timing: completed signal bar
- Assumed execution: next-bar open
- Repeated same-direction conditions: de-duplicated into independent episodes
- Forward horizons: 3, 5, 10 sessions

## Breadth gate

Current gate requires, among other checks:

- at least 10 symbols with the minimum sample count,
- at least 10 samples per qualifying symbol,
- positive signed-return breadth >= 60%,
- median symbol signed return > 0%,
- median symbol hit rate >= 50%.

## Regime-fit results

| Alpha | Intended regimes | 3D | 5D | 10D | Current research reading |
|---|---|---:|---:|---:|---|
| WilliamsAlpha | BULL, SIDEWAYS | PASS | PASS | PASS | Strongest and broadest evidence in this run |
| MomentumAlpha | BULL | FAIL | FAIL | FAIL | No broad edge demonstrated |
| TrendAlpha | BULL, BEAR | FAIL | FAIL | FAIL | Needs redesign / more selective conditions |
| BreakoutAlpha | BULL, HIGH_VOLATILITY | PASS | FAIL | PASS | Promising, especially 10 sessions |
| VolumeAlpha | BULL, SIDEWAYS, HIGH_VOLATILITY | PASS | FAIL | FAIL | Weak standalone edge; useful mainly as confirmation candidate |
| MeanReversionAlpha | SIDEWAYS | FAIL | PASS | FAIL | Promising but horizon-specific |
| VolatilityExpansionAlpha | BULL, HIGH_VOLATILITY | FAIL | FAIL | FAIL | Insufficient / inconsistent evidence |

### WilliamsAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 3,782 | 80.0% | +0.214% | 53.5% | PASS |
| 5 | 3,775 | 86.7% | +0.329% | 55.1% | PASS |
| 10 | 3,759 | 83.3% | +0.693% | 56.9% | PASS |

### MomentumAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 2,689 | 50.0% | -0.002% | 50.6% | FAIL |
| 5 | 2,686 | 40.0% | -0.051% | 49.7% | FAIL |
| 10 | 2,667 | 43.3% | -0.063% | 52.3% | FAIL |

### TrendAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 2,446 | 50.0% | -0.020% | 48.9% | FAIL |
| 5 | 2,445 | 56.7% | +0.055% | 49.4% | FAIL |
| 10 | 2,427 | 40.0% | -0.145% | 51.8% | FAIL |

### BreakoutAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 1,708 | 60.0% | +0.148% | 53.3% | PASS |
| 5 | 1,706 | 53.3% | +0.045% | 52.7% | FAIL |
| 10 | 1,695 | 66.7% | +0.252% | 52.1% | PASS |

### VolumeAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 3,388 | 60.0% | +0.024% | 50.7% | PASS |
| 5 | 3,374 | 50.0% | -0.002% | 50.0% | FAIL |
| 10 | 3,364 | 56.7% | +0.098% | 52.1% | FAIL |

### MeanReversionAlpha

| Horizon | Samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---|
| 3 | 708 | 56.7% | +0.119% | 50.0% | FAIL |
| 5 | 702 | 63.3% | +0.160% | 50.1% | PASS |
| 10 | 702 | 53.3% | +0.120% | 50.9% | FAIL |

### VolatilityExpansionAlpha

| Horizon | Samples | Symbols with >=10 samples | Positive breadth | Median signed return | Median hit rate | Gate |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 211 | 15 | 46.7% | -0.068% | 50.0% | FAIL |
| 5 | 211 | 15 | 53.3% | +0.071% | 50.0% | FAIL |
| 10 | 210 | 15 | 53.3% | +0.012% | 53.3% | FAIL |

## Interpretation

1. **WilliamsAlpha is the lead candidate.** It passed all tested horizons with broad positive participation across the 30-stock universe. The 10-session horizon has the largest median edge, while the 5-session horizon has the widest positive breadth.
2. **BreakoutAlpha deserves further validation**, especially around the 10-session horizon and only in its intended BULL / HIGH_VOLATILITY regimes.
3. **MeanReversionAlpha remains research-only.** The earlier strong NVDA result was not purely a one-symbol artifact: the five-year matrix shows positive breadth at 5 sessions, but the edge is modest and horizon-specific.
4. **VolumeAlpha should not be treated as a primary standalone strategy yet.** Its 3-session pass is marginal; it is more likely to be valuable as a confirmation / quality feature inside Signal Fusion.
5. **MomentumAlpha and TrendAlpha, in their current rule forms, did not demonstrate enough cross-symbol edge.** They should not receive higher weights merely because their names represent common strategy families.
6. **VolatilityExpansionAlpha remains unproven** and has materially fewer qualifying observations.

## Next research gates before promotion

A Breadth PASS is necessary but not sufficient. Before any research model can be promoted toward execution it should still pass:

- temporal stability / walk-forward testing,
- out-of-sample validation,
- normal-market vs event-driven attribution,
- transaction-cost and slippage sensitivity,
- drawdown / adverse excursion controls,
- concentration tests,
- shadow comparison against the current baseline.

Raw Yahoo market CSV files remain local / artifact-only and are not committed to the repository.
