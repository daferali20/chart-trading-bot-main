import asyncio

from app.broker.ibkr import IBKRClient
from app.execution.execution_gate import ExecutionGate
from app.storage.order_store import OrderStore
from app.config import settings


async def main():
    print("=" * 60)
    print("AI TRADER - READ ONLY GATE CHECK")
    print("NO ORDER WILL BE SENT")
    print("=" * 60)

    broker = IBKRClient()
    store = OrderStore()
    gate = ExecutionGate(broker, store)

    try:
        # ---------------------------------------------------------
        # 1. CONNECTION
        # ---------------------------------------------------------
        print("\n--- IBKR CONNECTION ---")

        await broker.connect()

        print("IBKR = CONNECTED")

        # ---------------------------------------------------------
        # 2. POSITIONS
        # ---------------------------------------------------------
        print("\n--- IBKR POSITIONS ---")

        positions = await broker.portfolio_positions()

        print(f"POSITIONS = {len(positions)}")

        if positions:
            for position in positions:
                print(position)
        else:
            print("No active positions.")

        # ---------------------------------------------------------
        # 3. OPEN ORDERS
        # ---------------------------------------------------------
        print("\n--- IBKR OPEN ORDERS ---")

        open_orders = await broker.open_orders()

        print(f"OPEN ORDERS RAW = {len(open_orders)}")

        active_open_orders = []

        for trade in open_orders:
            contract = getattr(trade, "contract", None)

            symbol = (
                getattr(contract, "symbol", "")
                if contract
                else ""
            )

            status = broker.order_status(trade)
            order_id = broker.order_id(trade)

            print(
                f"SYMBOL={symbol} "
                f"STATUS={status} "
                f"ORDER_ID={order_id}"
            )

            if status not in (
                "Filled",
                "Cancelled",
                "ApiCancelled",
                "Inactive",
            ):
                active_open_orders.append(trade)

        print(
            f"ACTIVE OPEN ORDERS = "
            f"{len(active_open_orders)}"
        )

        # ---------------------------------------------------------
        # 4. EXECUTED COUNT
        # ---------------------------------------------------------
        print("\n--- EXECUTION COUNT ---")

        executed = store.executed_count(
            settings.execution_count_scope
        )

        print(
            f"EXECUTED "
            f"({settings.execution_count_scope}) = "
            f"{executed}"
        )

        # ---------------------------------------------------------
        # 5. LIMITS
        # ---------------------------------------------------------
        print("\n--- LIMITS ---")

        print(
            f"MAX EXECUTED ORDERS = "
            f"{settings.max_executed_orders}"
        )

        print(
            f"MAX ACTIVE POSITIONS = "
            f"{settings.max_active_positions}"
        )

        print(
            f"MAX OPEN ORDERS = "
            f"{settings.max_open_orders}"
        )

        print(
            f"EXECUTION COUNT SCOPE = "
            f"{settings.execution_count_scope}"
        )

        print(
            f"PAPER TRADING = "
            f"{settings.paper_trading}"
        )

        # ---------------------------------------------------------
        # 6. AAPL POSITION
        # ---------------------------------------------------------
        print("\n--- AAPL POSITION ---")

        aapl_position = await broker.current_position("AAPL")

        print(
            f"AAPL POSITION QUANTITY = "
            f"{aapl_position}"
        )

        # ---------------------------------------------------------
        # 7. EXECUTION GATE
        # ---------------------------------------------------------
        print("\n--- EXECUTION GATE: AAPL ---")

        decision = await gate.check("AAPL")

        print(
            f"ALLOWED = "
            f"{decision.allowed}"
        )

        print(
            f"REASON = "
            f"{decision.reason}"
        )

        print(
            f"ACTIVE POSITIONS = "
            f"{decision.active_positions}"
        )

        # ExecutionDecision stores the raw open-order collection.
        print(
            f"OPEN ORDERS IN DECISION = "
            f"{len(decision.open_orders)}"
        )

        # ---------------------------------------------------------
        # 8. EXECUTED COUNT
        # ---------------------------------------------------------
        #
        # ExecutionDecision does not expose an "executed"
        # attribute. We already calculated the value directly
        # from OrderStore above.
        #
        print(
            f"EXECUTED COUNT = "
            f"{executed}"
        )

        # ---------------------------------------------------------
        # 9. FINAL SAFETY RESULT
        # ---------------------------------------------------------
        print("\n--- FINAL RESULT ---")

        if decision.allowed:
            print("GATE STATUS = ALLOWED")
            print(
                "NO ORDER WAS SENT BY THIS TEST."
            )
        else:
            print("GATE STATUS = BLOCKED")
            print(
                f"BLOCK REASON = "
                f"{decision.reason}"
            )

        print("\n" + "=" * 60)
        print("READ ONLY CHECK COMPLETE")
        print("NO ORDER WAS SENT")
        print("=" * 60)

    except Exception as exc:
        print("\n" + "=" * 60)
        print("ERROR")
        print("=" * 60)
        print(f"TYPE = {type(exc).__name__}")
        print(f"MESSAGE = {exc}")

    finally:
        try:
            await broker.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())