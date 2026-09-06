from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, Signal, Slot

from app.analysis.chart_engine import add_chart_indicators, chart_context
from app.analysis.indicators import add_indicators
from app.broker.ibkr import IBKRClient
from app.config import settings
from app.execution.order_manager import OrderManager
from app.scanner import load_watchlist, merge_candidates, top_gainers
from app.strategy.chart_strategy import evaluate_chart
from app.tradingview.bridge import TradingViewBridge


class ScannerWorker(QObject):
    status = Signal(str)
    scan = Signal(object)
    order = Signal(object)
    snapshot = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, interval=60):
        super().__init__()
        self.interval = interval
        self.running = False
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
                    "timestamps": [str(x) for x in df["timestamp"].tail(80).tolist()],
                    "open": [float(x) for x in df["open"].tail(80).tolist()],
                    "high": [float(x) for x in df["high"].tail(80).tolist()],
                    "low": [float(x) for x in df["low"].tail(80).tolist()],
                    "close": [float(x) for x in df["close"].tail(80).tolist()],
                    "volume": [float(x) for x in df["volume"].tail(80).tolist()],
                }
                return symbol, signal, context, chart_data, None
            except Exception as e:
                return symbol, None, None, None, str(e)

    async def _run(self):
        self.running = True
        try:
            await self.client.connect()
            while self.running:
                try:
                    await self.orders.refresh_all_statuses()
                    tv_processed, tv_submitted = await self.tv.process_pending()
                    if tv_processed or tv_submitted:
                        self.status.emit(
                            f"TradingView queue | processed={tv_processed} | submitted={tv_submitted}"
                        )

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
                    })
                    self.status.emit(
                        f"Portfolio verified | positions={len(positions)} | open orders={len(open_orders)} | executed={executed}/{settings.max_executed_orders}"
                    )

                    gainers = await top_gainers(self.client.ib, settings.top_gainers_count)
                    custom = load_watchlist(settings.watchlist_file)
                    symbols = merge_candidates(gainers, custom)
                    results = await asyncio.gather(*(self.analyze_symbol(s) for s in symbols))
                    for symbol, signal, context, chart_data, error in results:
                        if error:
                            self.error.emit(f"{symbol}: {error}")
                            continue
                        self.scan.emit({
                            "symbol": symbol,
                            "signal": signal,
                            "context": context,
                            "chart": chart_data,
                        })
                        if signal.action != "BUY" or signal.stop is None:
                            continue
                        record = await self.orders.submit_signal(symbol, signal, source="scanner")
                        if record:
                            self.order.emit(record)
                            self.status.emit(f"ORDER SUBMITTED | {symbol} | order={record.order_id}")
                        else:
                            _, reason = await self.orders.can_open_trade(symbol)
                            self.status.emit(f"{symbol} order kept inside bot | {reason}")
                    await asyncio.sleep(self.interval)
                except Exception as e:
                    self.error.emit(f"Scanner: {e}")
                    await asyncio.sleep(self.interval)
        finally:
            await self.client.disconnect()
            self.status.emit("Disconnected")
            self.finished.emit()

    @Slot()
    def stop(self):
        self.running = False
