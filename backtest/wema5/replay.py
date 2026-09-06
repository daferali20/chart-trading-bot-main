from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import DEFAULT_DATA_NORMALIZER
from app.strategy.wema5.strategy import WEMA5Strategy


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    raw = pd.read_csv(path)
    data = DEFAULT_DATA_NORMALIZER.normalize(
        raw,
        require_open=True,
        require_volume=True,
        preserve_extra=False,
    )
    data = data[data["volume"] > 0].reset_index(drop=True)
    return data


def _trade_metrics(trades: list[dict]) -> dict:
    returns = [float(trade["return"]) for trade in trades]
    if not returns:
        return {
            "closed_trades": 0,
            "win_rate": 0.0,
            "compound_return": 0.0,
            "average_trade": 0.0,
            "profit_factor": 0.0,
        }

    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]

    compound = 1.0
    for value in returns:
        compound *= 1.0 + value

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else float("inf")
    )

    return {
        "closed_trades": len(returns),
        "win_rate": len(wins) / len(returns),
        "compound_return": compound - 1.0,
        "average_trade": sum(returns) / len(returns),
        "profit_factor": profit_factor,
    }


def replay(
    symbol: str,
    df: pd.DataFrame,
    days: int = 30,
) -> dict:
    """Replay WEMA5_BASELINE_v1 with next-bar-open execution.

    Signals are evaluated on completed candles. Both BUY and SELL orders are
    executed on the NEXT candle open. A final SELL signal with no following
    candle cannot be executed and therefore leaves the position open.
    """

    if len(df) < 30:
        raise ValueError(f"{symbol}: not enough candles.")

    data = WEMA5Strategy.add_indicators(df)
    start_index = max(1, len(data) - days)
    strategy = WEMA5Strategy(symbol.upper())

    in_position = False
    entry_price: float | None = None
    entry_date = None
    entry_signal_date = None
    trades: list[dict] = []

    for index in range(start_index, len(data)):
        signal = strategy.generate_signal(
            data,
            index=index,
            in_position=in_position,
        )
        if signal is None:
            continue

        next_index = index + 1

        if signal.action == "BUY" and not in_position:
            # No next bar means the signal is not executable in this replay.
            if next_index >= len(data):
                continue

            entry_signal_date = data.iloc[index]["date"]
            entry_date = data.iloc[next_index]["date"]
            entry_price = float(data.iloc[next_index]["open"])
            in_position = True
            continue

        if signal.action == "SELL" and in_position:
            if next_index >= len(data):
                continue

            exit_signal_date = data.iloc[index]["date"]
            execution_date = data.iloc[next_index]["date"]
            exit_price = float(data.iloc[next_index]["open"])
            trade_return = (exit_price / float(entry_price)) - 1.0

            trades.append(
                {
                    "symbol": symbol.upper(),
                    "entry_signal_date": entry_signal_date,
                    "entry_date": entry_date,
                    "entry_price": float(entry_price),
                    "exit_signal_date": exit_signal_date,
                    "execution_date": execution_date,
                    "exit_price": exit_price,
                    "return": trade_return,
                }
            )

            in_position = False
            entry_price = None
            entry_date = None
            entry_signal_date = None

    open_position = None
    if in_position and entry_price is not None:
        final_price = float(data.iloc[-1]["close"])
        open_position = {
            "symbol": symbol.upper(),
            "entry_signal_date": entry_signal_date,
            "entry_date": entry_date,
            "entry_price": float(entry_price),
            "final_date": data.iloc[-1]["date"],
            "final_price": final_price,
            "unrealized_return": (final_price / float(entry_price)) - 1.0,
        }

    return {
        "strategy": WEMA5Strategy.NAME,
        "symbol": symbol.upper(),
        "test_candles": len(data) - start_index,
        "trades": trades,
        "open_position": open_position,
        "metrics": _trade_metrics(trades),
    }


def run_replay(
    symbol: str,
    csv_path: Path,
    days: int = 30,
) -> dict:
    result = replay(symbol, load_csv(csv_path), days=days)

    print()
    print("=" * 70)
    print(f"WEMA5 BASELINE v1 — {symbol.upper()}")
    print("=" * 70)
    print(f"Test candles : {result['test_candles']}")
    print(f"Closed trades: {result['metrics']['closed_trades']}")

    metrics = result["metrics"]
    if metrics["closed_trades"]:
        print(f"Win rate       : {metrics['win_rate'] * 100:.2f}%")
        print(f"Compound return: {metrics['compound_return'] * 100:.2f}%")
        print(f"Average trade  : {metrics['average_trade'] * 100:.2f}%")
        if metrics["profit_factor"] == float("inf"):
            print("Profit factor  : INF")
        else:
            print(f"Profit factor  : {metrics['profit_factor']:.2f}")

    for number, trade in enumerate(result["trades"], start=1):
        print(
            f"{number:02d}. signal {trade['entry_signal_date'].date()} "
            f"→ BUY {trade['entry_date'].date()} @ {trade['entry_price']:.2f} "
            f"→ SELL {trade['execution_date'].date()} @ {trade['exit_price']:.2f} "
            f"| {trade['return'] * 100:.2f}%"
        )

    if result["open_position"]:
        position = result["open_position"]
        print(
            f"OPEN: BUY {position['entry_date'].date()} @ {position['entry_price']:.2f} "
            f"→ final {position['final_date'].date()} @ {position['final_price']:.2f} "
            f"| {position['unrealized_return'] * 100:.2f}%"
        )

    return result


def main() -> None:
    data_dir = PROJECT_ROOT / "data" / "backtest"
    tests = [
        ("SPY", data_dir / "SPY_1d.csv"),
        ("AAPL", data_dir / "AAPL_1d.csv"),
        ("AMD", data_dir / "AMD_1d.csv"),
    ]

    for days in (7, 14, 30, 60):
        print()
        print("#" * 80)
        print(f"WEMA5 SHORT REPLAY — LAST {days} DAYS")
        print("#" * 80)
        for symbol, path in tests:
            run_replay(symbol=symbol, csv_path=path, days=days)


if __name__ == "__main__":
    main()
