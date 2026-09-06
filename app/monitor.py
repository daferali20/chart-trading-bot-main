from __future__ import annotations
import asyncio,logging
from app.broker.ibkr import IBKRClient
from app.analysis.indicators import add_indicators
from app.analysis.chart_engine import add_chart_indicators,chart_context
from app.strategy.chart_strategy import evaluate_chart
from app.execution.order_manager import OrderManager
log=logging.getLogger(__name__)

class MarketMonitor:
    def __init__(self,symbol,interval_seconds=60):
        self.symbol=symbol.upper();self.interval_seconds=interval_seconds;self.client=IBKRClient();self.orders=OrderManager(self.client);self.running=False;self.last_signal_bar=None
    async def scan_once(self):
        df=await self.client.historical_bars(self.symbol);df=add_indicators(df);df=add_chart_indicators(df);signal=evaluate_chart(df);context=chart_context(df)
        bar_time=df.iloc[-1].timestamp
        if signal.action=="BUY" and self.last_signal_bar!=bar_time:
            record=await self.orders.submit_signal(self.symbol,signal,source="monitor")
            if record:self.last_signal_bar=bar_time;log.warning("ORDER SUBMITTED THROUGH EXECUTION GATE | %s | %s",self.symbol,record.order_id)
            else:
                _,reason=await self.orders.can_open_trade(self.symbol);log.info("ORDER HELD/BLOCKED | %s | %s",self.symbol,reason)
        return signal,context
    async def run(self):
        self.running=True
        try:
            await self.client.connect()
            while self.running:
                try: await self.scan_once()
                except Exception: log.exception("Market scan failed for %s",self.symbol)
                await asyncio.sleep(self.interval_seconds)
        finally: await self.client.disconnect()
    def stop(self): self.running=False
