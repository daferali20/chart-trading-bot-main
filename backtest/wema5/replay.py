from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Allow execution from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.strategy.wema5.strategy import WEMA5Strategy


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}"
        )

    df = pd.read_csv(path)

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    )

    df = df[df["volume"] > 0]

    df = (
        df.sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    return df


def run_replay(
    symbol: str,
    csv_path: Path,
    days: int = 30,
) -> None:

    df = load_csv(csv_path)

    if len(df) < 30:
        raise ValueError(
            f"{symbol}: not enough candles."
        )

    # IMPORTANT:
    # We calculate indicators using the complete dataset
    # but only replay the requested final window.
    #
    # This prevents the short test from losing indicator
    # history before the test window starts.

    data = WEMA5Strategy.add_indicators(df)

    start_index = max(
        1,
        len(data) - days,
    )

    strategy = WEMA5Strategy(symbol)

    in_position = False
    entry_price = None
    entry_date = None

    trades = []

    for index in range(
        start_index,
        len(data),
    ):

        signal = strategy.generate_signal(
            data,
            index=index,
            in_position=in_position,
        )

        if signal is None:
            continue

        # ---------------------------------------------------------
        # BUY
        # ---------------------------------------------------------

        if signal.action == "BUY" and not in_position:

            entry_price = float(
                data.iloc[index]["close"]
            )

            entry_date = data.iloc[index]["date"]

            in_position = True

            print(
                f"[BUY]  "
                f"{symbol} "
                f"{entry_date.date()} "
                f"signal_close={entry_price:.2f} "
                f"| {signal.reason}"
            )

        # ---------------------------------------------------------
        # SELL
        # ---------------------------------------------------------

        elif signal.action == "SELL" and in_position:

            exit_signal_price = float(
                data.iloc[index]["close"]
            )

            exit_date = data.iloc[index]["date"]

            # Baseline rule:
            # signal on completed candle,
            # execute next candle open.
            #
            # If there is no next candle, use final close
            # for the test result.

            next_index = index + 1

            if next_index < len(data):

                exit_price = float(
                    data.iloc[next_index]["open"]
                )

                execution_date = data.iloc[
                    next_index
                ]["date"]

            else:

                exit_price = float(
                    data.iloc[index]["close"]
                )

                execution_date = data.iloc[
                    index
                ]["date"]

            trade_return = (
                exit_price / entry_price
            ) - 1.0

            trades.append(
                {
                    "symbol": symbol,
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "signal_exit_date": exit_date,
                    "signal_exit_price": exit_signal_price,
                    "execution_date": execution_date,
                    "exit_price": exit_price,
                    "return": trade_return,
                }
            )

            print(
                f"[SELL] "
                f"{symbol} "
                f"{exit_date.date()} "
                f"signal_close={exit_signal_price:.2f} "
                f"→ execution={execution_date.date()} "
                f"open={exit_price:.2f} "
                f"| return={trade_return * 100:.2f}% "
                f"| {signal.reason}"
            )

            in_position = False
            entry_price = None
            entry_date = None

    # -------------------------------------------------------------
    # Open position at end of test
    # -------------------------------------------------------------

    if in_position and entry_price is not None:

        final_price = float(
            data.iloc[-1]["close"]
        )

        final_date = data.iloc[-1]["date"]

        unrealized_return = (
            final_price / entry_price
        ) - 1.0

        print(
            f"[OPEN] "
            f"{symbol} "
            f"entry={entry_price:.2f} "
            f"at {entry_date.date()} "
            f"→ final_close={final_price:.2f} "
            f"at {final_date.date()} "
            f"| unrealized={unrealized_return * 100:.2f}%"
        )

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------

    print()
    print("=" * 70)
    print(f"WEMA5 BASELINE v1 — {symbol}")
    print("=" * 70)

    print(f"Test candles : {len(data) - start_index}")
    print(f"Closed trades: {len(trades)}")

    if not trades:
        print("No closed trades in this window.")
        print()

        return

    returns = [
        trade["return"]
        for trade in trades
    ]

    wins = [
        value
        for value in returns
        if value > 0
    ]

    losses = [
        value
        for value in returns
        if value <= 0
    ]

    compound_return = 1.0

    for value in returns:
        compound_return *= 1.0 + value

    compound_return -= 1.0

    win_rate = (
        len(wins) / len(returns)
        if returns
        else 0.0
    )

    gross_profit = sum(wins)

    gross_loss = abs(sum(losses))

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else float("inf")
    )

    average_trade = (
        sum(returns) / len(returns)
    )

    print(
        f"Win rate      : {win_rate * 100:.2f}%"
    )

    print(
        f"Compound return: "
        f"{compound_return * 100:.2f}%"
    )

    print(
        f"Average trade : "
        f"{average_trade * 100:.2f}%"
    )

    if profit_factor == float("inf"):
        print("Profit factor : INF")
    else:
        print(
            f"Profit factor : "
            f"{profit_factor:.2f}"
        )

    print()
    print("Trades:")

    for number, trade in enumerate(
        trades,
        start=1,
    ):

        print(
            f"{number:02d}. "
            f"{trade['entry_date'].date()} "
            f"{trade['entry_price']:.2f}"
            f" → "
            f"{trade['execution_date'].date()} "
            f"{trade['exit_price']:.2f}"
            f" | "
            f"{trade['return'] * 100:.2f}%"
        )

    print()


def main() -> None:

    data_dir = (
        PROJECT_ROOT
        / "data"
        / "backtest"
    )

    tests = [
        ("SPY", data_dir / "SPY_1d.csv"),
        ("AAPL", data_dir / "AAPL_1d.csv"),
        ("AMD", data_dir / "AMD_1d.csv"),
    ]

    # Short windows to test.
    windows = [7, 14, 30, 60]

    for days in windows:

        print()
        print("#" * 80)
        print(f"WEMA5 SHORT REPLAY — LAST {days} DAYS")
        print("#" * 80)

        for symbol, path in tests:

            print()
            run_replay(
                symbol=symbol,
                csv_path=path,
                days=days,
            )


if __name__ == "__main__":
    main()