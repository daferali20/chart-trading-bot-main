from __future__ import annotations

import asyncio
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

from app.analysis.chart_engine import add_chart_indicators, chart_context
from app.analysis.indicators import add_indicators
from app.broker.ibkr import IBKRClient
from app.config import settings
from app.execution.order_manager import OrderManager
from app.scanner import load_watchlist, merge_candidates, top_gainers
from app.strategy.chart_strategy import evaluate_chart
from app.tradingview.bridge import TradingViewBridge


class IndependentScannerWorker(QObject):
    """Persistent IBKR worker. Connection, scanner start/pause and disconnect are separate controls."""
    status = Signal(str)
    scan = Signal(object)
    order = Signal(object)
    snapshot = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, interval=60):
        super().__init__()
        self.interval = max(5, int(interval))
        self.running = False
        self.scan_enabled = threading.Event()
        self.client = IBKRClient()
        self.orders = OrderManager(self.client)
        self.tv = TradingViewBridge(self.orders)
        self.semaphore = asyncio.Semaphore(4)

    @Slot()
    def run(self):
        asyncio.run(self._run())

    async def analyze_symbol(self, symbol):
        async with self.semaphore:
            try:
                df = await self.client.historical_bars(symbol)
                df = add_indicators(df)
                df = add_chart_indicators(df)
                signal = evaluate_chart(df)
                context = chart_context(df)
                chart_data = {
                    "timestamps": [str(x) for x in df["timestamp"].tail(120).tolist()],
                    "open": [float(x) for x in df["open"].tail(120).tolist()],
                    "high": [float(x) for x in df["high"].tail(120).tolist()],
                    "low": [float(x) for x in df["low"].tail(120).tolist()],
                    "close": [float(x) for x in df["close"].tail(120).tolist()],
                    "volume": [float(x) for x in df["volume"].tail(120).tolist()],
                    "ema50": [float(x) if x == x else None for x in df["ema50_chart"].tail(120).tolist()],
                }
                return symbol, signal, context, chart_data, None
            except Exception as exc:
                return symbol, None, None, None, str(exc)

    async def _snapshot(self):
        positions = await self.client.portfolio_positions()
        open_orders = await self.client.open_orders()
        executed = self.orders.store.executed_count(settings.execution_count_scope)
        account_value = None
        try:
            account_value = await self.client.account_value()
        except Exception:
            pass
        self.snapshot.emit({
            "connected": True,
            "positions": positions,
            "open_orders": open_orders,
            "executed": executed,
            "maximum": settings.max_executed_orders,
            "account_value": account_value,
            "timestamp": time.time(),
        })
        return positions, open_orders, executed

    async def _scan_once(self):
        gainers = await top_gainers(self.client.ib, settings.top_gainers_count)
        custom = load_watchlist(settings.watchlist_file)
        symbols = merge_candidates(gainers, custom)
        results = await asyncio.gather(*(self.analyze_symbol(s) for s in symbols))
        for symbol, signal, context, chart_data, error in results:
            if error:
                self.error.emit(f"{symbol}: {error}")
                continue
            self.scan.emit({"symbol": symbol, "signal": signal, "context": context, "chart": chart_data})
            if signal.action != "BUY" or signal.stop is None:
                continue
            record = await self.orders.submit_signal(symbol, signal, source="scanner")
            if record:
                self.order.emit(record)
                self.status.emit(f"ORDER SUBMITTED | {symbol} | order={record.order_id}")
            else:
                _, reason = await self.orders.can_open_trade(symbol)
                self.status.emit(f"{symbol} order kept inside bot | {reason}")

    async def _run(self):
        self.running = True
        try:
            await self.client.connect()
            self.status.emit("IBKR CONNECTED | Paper trading")
            last_scan = 0.0
            while self.running:
                try:
                    await self.orders.refresh_all_statuses()
                    tv_processed, tv_submitted = await self.tv.process_pending()
                    if tv_processed or tv_submitted:
                        self.status.emit(f"TradingView queue | processed={tv_processed} | submitted={tv_submitted}")
                    positions, open_orders, executed = await self._snapshot()
                    self.status.emit(f"Portfolio verified | positions={len(positions)} | open orders={len(open_orders)} | executed={executed}/{settings.max_executed_orders}")
                    now = time.monotonic()
                    if self.scan_enabled.is_set() and now - last_scan >= self.interval:
                        self.status.emit("Scanner running | analyzing watchlist")
                        await self._scan_once()
                        last_scan = time.monotonic()
                    await asyncio.sleep(1.0)
                except Exception as exc:
                    self.error.emit(f"Worker: {exc}")
                    await asyncio.sleep(2.0)
        finally:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.running = False
            self.scan_enabled.clear()
            self.status.emit("IBKR DISCONNECTED")
            self.finished.emit()

    @Slot()
    def start_scanning(self):
        self.scan_enabled.set()
        self.status.emit("Scanner STARTED")

    @Slot()
    def pause_scanning(self):
        self.scan_enabled.clear()
        self.status.emit("Scanner PAUSED")

    @Slot()
    def stop(self):
        self.scan_enabled.clear()
        self.running = False
