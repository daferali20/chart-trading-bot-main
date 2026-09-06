from __future__ import annotations
from app.strategy.signal import Signal
from app.tradingview.store import TradingViewSignalStore


class TradingViewBridge:
    def __init__(self, order_manager, store: TradingViewSignalStore | None = None):
        self.orders = order_manager
        self.store = store or TradingViewSignalStore()

    async def process_pending(self, limit: int = 50):
        processed = 0
        submitted = 0
        for row in self.store.pending(limit):
            signal_id, symbol, action, price, stop, target, score, message = row
            action = str(action).upper()
            if action == "HOLD":
                self.store.mark_processed(signal_id)
                processed += 1
                continue
            if action != "BUY" or price is None or stop is None:
                # Unsupported/invalid execution intent stays visible in the queue.
                continue
            reasons = tuple(x.strip() for x in (message or "TradingView alert").split("|") if x.strip())
            signal = Signal(action="BUY", score=int(score or 0), reasons=reasons or ("TradingView alert",), entry=float(price), stop=float(stop), target=float(target) if target is not None else None)
            record = await self.orders.submit_signal(symbol, signal, source="tradingview")
            if record is not None:
                self.store.mark_processed(signal_id)
                processed += 1
                submitted += 1
        return processed, submitted
