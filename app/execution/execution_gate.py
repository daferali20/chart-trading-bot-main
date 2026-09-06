from __future__ import annotations
import asyncio
from dataclasses import dataclass
from app.config import settings
from app.storage.order_store import OrderStore
from app.execution.models import ExecutionDecision

@dataclass
class ExecutionGate:
    broker:object
    store:OrderStore
    def __post_init__(self): self._lock=asyncio.Lock()
    async def check(self,symbol):
        symbol=symbol.upper()
        positions=await self.broker.portfolio_positions();open_orders=await self.broker.open_orders()
        position_symbols={p["symbol"].upper() for p in positions if p.get("quantity",0)!=0}
        active_positions=len(position_symbols);active_open=[];open_symbols=set()
        for t in open_orders:
            c=getattr(t,"contract",None);s=getattr(c,"symbol","") if c else "";status=self.broker.order_status(t)
            if s and status not in ("Filled","Cancelled","ApiCancelled","Inactive"):
                open_symbols.add(s.upper());active_open.append(t)
        executed=self.store.executed_count(settings.execution_count_scope)
        if symbol in position_symbols:return ExecutionDecision(False,f"Position already exists: {symbol}",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
        if symbol in open_symbols:return ExecutionDecision(False,f"Open order already exists: {symbol}",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
        if executed>=settings.max_executed_orders:return ExecutionDecision(False,f"Executed-order limit reached: {executed}/{settings.max_executed_orders}",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
        if active_positions>=settings.max_active_positions:return ExecutionDecision(False,f"Active-position limit reached: {active_positions}/{settings.max_active_positions}",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
        if len(active_open)>=settings.max_open_orders:return ExecutionDecision(False,f"Open-order limit reached: {len(active_open)}/{settings.max_open_orders}",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
        return ExecutionDecision(True,"OK",tuple(positions),tuple(open_orders),executed,active_positions,len(active_open))
    async def authorize_and_send(self,symbol,sender):
        async with self._lock:
            first=await self.check(symbol)
            if not first.allowed:return None,first
            second=await self.check(symbol)
            if not second.allowed:return None,second
            return await sender(),second
