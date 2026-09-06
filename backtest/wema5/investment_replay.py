
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
import pandas as pd

from app.strategy.wema5.investment_strategy import (
    WEMA5InvestmentStrategy,
)


#ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data" / "backtest"

SYMBOLS = [
    "SPY",
    "AAPL",
    "AMD",
    "NVDA",
]


@dataclass
class Trade:
    symbol: str

    entry_signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float

    exit_signal_date: pd.Timestamp | None = None
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None

    return_pct: float | None = None


def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}_1d.csv"

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
            f"{symbol}: missing columns "
            f"{sorted(missing)}"
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
        ]
    )

    df = df.sort_values("date")
    df = df.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    df = df[df["volume"] > 0]

    return df.reset_index(drop=True)


def calculate_profit_factor(
    trades: list[Trade],
) -> float:
    winners = [
        t.return_pct
        for t in trades
        if t.return_pct is not None
        and t.return_pct > 0
    ]

    losers = [
        t.return_pct
        for t in trades
        if t.return_pct is not None
        and t.return_pct < 0
    ]

    gross_profit = sum(winners)

    gross_loss = abs(sum(losers))

    if gross_loss == 0:
        if gross_profit > 0:
            return float("inf")

        return 0.0

    return gross_profit / gross_loss


def calculate_compound_return(
    trades: list[Trade],
) -> float:
    equity = 1.0

    for trade in trades:
        if trade.return_pct is None:
            continue

        equity *= (
            1.0
            + trade.return_pct / 100.0
        )

    return (
        equity - 1.0
    ) * 100.0


def calculate_trade_drawdown(
    trades: list[Trade],
) -> float:
    """
    Trade-level drawdown.

    This is intentionally kept separate from a
    daily mark-to-market equity curve.
    """

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0

    for trade in trades:
        if trade.return_pct is None:
            continue

        equity *= (
            1.0
            + trade.return_pct / 100.0
        )

        peak = max(
            peak,
            equity,
        )

        drawdown = (
            equity - peak
        ) / peak * 100.0

        max_drawdown = min(
            max_drawdown,
            drawdown,
        )

    return max_drawdown


def backtest(
    symbol: str,
    df: pd.DataFrame,
) -> tuple[list[Trade], Trade | None]:

    strategy = WEMA5InvestmentStrategy()

    data = strategy.add_indicators(df)

    trades: list[Trade] = []

    open_trade: Trade | None = None

    # We need the NEXT candle for execution.
    for i in range(1, len(data) - 1):

        today = data.iloc[i]
        next_day = data.iloc[i + 1]

        # ---------------------------------------------------------
        # EXIT
        # ---------------------------------------------------------

        if open_trade is not None:

            if (
                not pd.isna(today["ma35"])
                and today["close"] < today["ma35"]
            ):

                exit_price = float(
                    next_day["open"]
                )

                open_trade.exit_signal_date = (
                    today["date"]
                )

                open_trade.exit_date = (
                    next_day["date"]
                )

                open_trade.exit_price = (
                    exit_price
                )

                open_trade.return_pct = (
                    (
                        exit_price
                        / open_trade.entry_price
                    )
                    - 1.0
                ) * 100.0

                trades.append(open_trade)

                open_trade = None

                # One position only.
                continue

        # ---------------------------------------------------------
        # ENTRY
        # ---------------------------------------------------------

        if open_trade is None:

            entry_condition = (
                bool(today["entry_condition"])
                if not pd.isna(
                    today["entry_condition"]
                )
                else False
            )

            if entry_condition:

                entry_price = float(
                    next_day["open"]
                )

                open_trade = Trade(
                    symbol=symbol,
                    entry_signal_date=(
                        today["date"]
                    ),
                    entry_date=(
                        next_day["date"]
                    ),
                    entry_price=(
                        entry_price
                    ),
                )

    return trades, open_trade


def print_trade(
    trade: Trade,
) -> None:

    if trade.exit_date is None:
        print(
            f"  OPEN  "
            f"{trade.entry_date.date()} "
            f"@ {trade.entry_price:.2f}"
        )

        return

    print(
        f"  TRADE "
        f"{trade.entry_date.date()} "
        f"@ {trade.entry_price:.2f} "
        f"-> "
        f"{trade.exit_date.date()} "
        f"@ {trade.exit_price:.2f} "
        f"| "
        f"{trade.return_pct:+.2f}%"
    )


def print_results(
    symbol: str,
    trades: list[Trade],
    open_trade: Trade | None,
) -> None:

    closed = [
        t
        for t in trades
        if t.return_pct is not None
    ]

    wins = [
        t
        for t in closed
        if t.return_pct > 0
    ]

    losses = [
        t
        for t in closed
        if t.return_pct < 0
    ]

    compound = calculate_compound_return(
        closed
    )

    avg_trade = (
        sum(
            t.return_pct
            for t in closed
        )
        / len(closed)
        if closed
        else 0.0
    )

    win_rate = (
        len(wins)
        / len(closed)
        * 100.0
        if closed
        else 0.0
    )

    profit_factor = (
        calculate_profit_factor(
            closed
        )
        if closed
        else 0.0
    )

    max_dd = (
        calculate_trade_drawdown(
            closed
        )
        if closed
        else 0.0
    )

    print()
    print("=" * 70)
    print(
        f"{symbol} — "
        f"WEMA5_INVESTMENT_v1"
    )
    print("=" * 70)

    print(
        f"Closed trades : {len(closed)}"
    )

    print(
        f"Win rate      : "
        f"{win_rate:.2f}%"
    )

    print(
        f"Compound      : "
        f"{compound:+.2f}%"
    )

    print(
        f"Avg trade     : "
        f"{avg_trade:+.2f}%"
    )

    if profit_factor == float("inf"):
        print(
            "Profit Factor : INF"
        )
    else:
        print(
            f"Profit Factor : "
            f"{profit_factor:.2f}"
        )

    print(
        f"Max DD        : "
        f"{max_dd:.2f}%"
    )

    if closed:
        largest_winner = max(
            t.return_pct
            for t in closed
        )

        largest_loser = min(
            t.return_pct
            for t in closed
        )

        print(
            f"Largest winner: "
            f"{largest_winner:+.2f}%"
        )

        print(
            f"Largest loser : "
            f"{largest_loser:+.2f}%"
        )

    print()
    print("Trades:")

    for trade in trades:
        print_trade(trade)

    if open_trade is not None:

        last_close = None

        # We don't have df here, so only show
        # entry information.
        print()
        print(
            "OPEN POSITION:"
        )

        print(
            f"  Entry date : "
            f"{open_trade.entry_date.date()}"
        )

        print(
            f"  Entry price: "
            f"{open_trade.entry_price:.2f}"
        )


def main() -> None:

    print()
    print(
        "WEMA5_INVESTMENT_v1"
    )

    print(
        "Williams -55 + MA35 + EMA10"
    )

    print(
        "Exit: daily close below MA35"
    )

    print()

    for symbol in SYMBOLS:

        try:

            df = load_data(symbol)

            print(
                f"{symbol}: "
                f"{len(df)} daily candles "
                f"loaded"
            )

            if len(df) < 60:
                print(
                    f"{symbol}: "
                    "not enough data"
                )
                continue

            trades, open_trade = backtest(
                symbol,
                df,
            )

            print_results(
                symbol,
                trades,
                open_trade,
            )

        except Exception as exc:

            print()
            print(
                f"{symbol}: ERROR"
            )

            print(
                str(exc)
            )


if __name__ == "__main__":
    main()