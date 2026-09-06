from pathlib import Path
from datetime import datetime
import sys

import pandas as pd
from ib_async import IB, Stock, util


# ============================================================
# SETTINGS
# ============================================================

IB_HOST = "127.0.0.1"
IB_PORT = 7497
IB_CLIENT_ID = 150

# الأسهم التي نريد تحميلها
SYMBOLS = [
    "SPY",
    "AAPL",
    "AMD",
    "NVDA",
]

# البيانات المطلوبة
DURATION = "1 Y"
BAR_SIZE = "1 day"

# TRADES مهم لأننا نريد OHLCV وحجم التداول
WHAT_TO_SHOW = "TRADES"

# ساعات السوق العادية فقط
USE_RTH = True

# مكان حفظ البيانات
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "backtest"

# ============================================================
# HELPERS
# ============================================================


def validate_dataframe(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """تنظيف وفحص بيانات السوق قبل حفظها."""

    if df is None or df.empty:
        raise ValueError(f"{symbol}: IBKR returned no data.")

    required_columns = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [c for c in required_columns if c not in df.columns]

    if missing:
        raise ValueError(
            f"{symbol}: Missing columns: {', '.join(missing)}"
        )

    out = df.copy()

    # تحويل التاريخ
    out["date"] = pd.to_datetime(out["date"], errors="coerce")

    # تحويل OHLCV إلى أرقام
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        out[column] = pd.to_numeric(
            out[column],
            errors="coerce",
        )

    # حذف الصفوف غير الصالحة
    out = out.dropna(
        subset=[
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    )

    # لا نريد بيانات بدون تداول
    out = out[out["volume"] > 0]

    # الترتيب الزمني
    out = out.sort_values("date")

    # إزالة التكرار
    out = out.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    if out.empty:
        raise ValueError(
            f"{symbol}: No valid traded bars after filtering."
        )

    return out


def fetch_symbol(ib: IB, symbol: str) -> pd.DataFrame:
    """جلب بيانات سهم واحد من IBKR."""

    print()
    print("=" * 70)
    print(f"Fetching {symbol}")
    print("=" * 70)

    contract = Stock(
        symbol,
        "SMART",
        "USD",
    )

    # التأكد من أن العقد معروف لـIBKR
    qualified = ib.qualifyContracts(contract)

    if not qualified:
        raise RuntimeError(
            f"{symbol}: IBKR could not qualify the contract."
        )

    contract = qualified[0]

    print(
        f"Contract: {contract.symbol} "
        f"| Exchange: {contract.exchange} "
        f"| Currency: {contract.currency}"
    )

    print(
        f"Request: {DURATION} | {BAR_SIZE} | "
        f"{WHAT_TO_SHOW} | RTH={USE_RTH}"
    )

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=DURATION,
        barSizeSetting=BAR_SIZE,
        whatToShow=WHAT_TO_SHOW,
        useRTH=USE_RTH,
        formatDate=1,
    )

    if not bars:
        raise RuntimeError(
            f"{symbol}: IBKR returned zero historical bars."
        )

    df = util.df(bars)

    df = validate_dataframe(
        df,
        symbol,
    )

    return df


def save_symbol(df: pd.DataFrame, symbol: str) -> Path:
    """حفظ بيانات السهم محليًا."""

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = DATA_DIR / f"{symbol}_1d.csv"

    df.to_csv(
        output_file,
        index=False,
    )

    return output_file


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    print("=" * 70)
    print("AI TRADER - IBKR HISTORICAL DATA DOWNLOADER")
    print("=" * 70)

    print(f"IBKR: {IB_HOST}:{IB_PORT}")
    print(f"Client ID: {IB_CLIENT_ID}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Duration: {DURATION}")
    print(f"Bar size: {BAR_SIZE}")
    print(f"Data type: {WHAT_TO_SHOW}")
    print(f"Regular Trading Hours: {USE_RTH}")
    print(f"Output: {DATA_DIR}")
    print()

    ib = IB()

    try:

        print("Connecting to IBKR...")

        ib.connect(
            IB_HOST,
            IB_PORT,
            clientId=IB_CLIENT_ID,
        )

        if not ib.isConnected():
            print("ERROR: Could not connect to IBKR.")
            return 1

        print("CONNECTED.")

        success = 0
        failed = 0

        for symbol in SYMBOLS:

            try:

                df = fetch_symbol(
                    ib,
                    symbol,
                )

                output_file = save_symbol(
                    df,
                    symbol,
                )

                first_date = df["date"].iloc[0]
                last_date = df["date"].iloc[-1]

                avg_volume = df["volume"].mean()

                print()
                print(f"{symbol}: SUCCESS")
                print(f"Rows: {len(df):,}")
                print(f"From: {first_date}")
                print(f"To:   {last_date}")
                print(f"Average volume: {avg_volume:,.0f}")
                print(f"Saved: {output_file}")

                success += 1

            except Exception as exc:

                failed += 1

                print()
                print(f"{symbol}: FAILED")
                print(f"Reason: {exc}")

        print()
        print("=" * 70)
        print("DOWNLOAD SUMMARY")
        print("=" * 70)

        print(f"Successful: {success}")
        print(f"Failed:     {failed}")
        print()

        if success > 0:

            print("Files saved in:")
            print(DATA_DIR)

            print()
            print("Available files:")

            for file in sorted(DATA_DIR.glob("*_1d.csv")):
                print(f"  - {file.name}")

        print()
        print(
            "Historical data download completed."
        )

        return 0 if failed == 0 else 2

    except Exception as exc:

        print()
        print("=" * 70)
        print("FATAL ERROR")
        print("=" * 70)
        print(exc)

        return 1

    finally:

        if ib.isConnected():
            print()
            print("Disconnecting from IBKR...")
            ib.disconnect()
            print("Disconnected.")


if __name__ == "__main__":
    sys.exit(main())