from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from app.config import settings
from app.execution.execution_gate import ExecutionGate
from app.execution.queue import OrderQueue
from app.risk.manager import validate_trade
from app.storage.order_store import OrderStore


@dataclass
class OrderRecord:
    time: str
    symbol: str
    action: str
    quantity: int
    market_price: float
    entry_limit: float
    stop: float | None
    target: float | None
    status: str
    order_id: str = ""
    source: str = "scanner"


class OrderManager:
    def __init__(self, broker):
        self.broker = broker
        self.records: list[OrderRecord] = []
        self.trades: dict[str, object] = {}
        self.last_signal_key: set[str] = set()
        self.pending_signals = {}
        self.queue = OrderQueue()
        self.store = OrderStore()
        self.gate = ExecutionGate(broker, self.store)

    async def can_open_trade(self, symbol):
        decision = await self.gate.check(symbol)
        return decision.allowed, decision.reason

    async def submit_signal(self, symbol, signal, source="scanner"):
        symbol = symbol.upper()
        if signal.action != "BUY" or signal.stop is None:
            return None
        entry = float(signal.entry)
        stop = float(signal.stop)
        target = float(signal.target) if signal.target is not None else round(entry + settings.reward_risk * (entry - stop), 2)
        key = f"{source}:{symbol}:{signal.action}:{entry:.6f}:{stop:.6f}:{target:.6f}"
        if key in self.last_signal_key:
            return None

        quantity = int(settings.fixed_quantity)
        if quantity <= 0:
            raise ValueError("FIXED_QUANTITY must be positive")

        entry_limit = round(entry - 0.10, 2)
        risk = validate_trade(
            entry_limit,
            stop,
            target,
            quantity,
            settings.paper_account_value,
            settings.risk_per_trade,
        )
        if not risk.allowed:
            self.pending_signals[symbol] = signal
            self.queue.put(symbol, signal, source)
            return None

        self.pending_signals[symbol] = signal
        self.queue.put(symbol, signal, source)

        async def sender():
            return await self.broker.place_limit_order(symbol, "BUY", quantity, entry_limit)

        trade, decision = await self.gate.authorize_and_send(symbol, sender)
        if trade is None:
            return None

        order_id = self.broker.order_id(trade)
        status = str(self.broker.order_status(trade) or "SUBMITTED").upper()
        record = OrderRecord(
            datetime.now().isoformat(timespec="seconds"),
            symbol,
            "BUY",
            quantity,
            entry,
            entry_limit,
            stop,
            target,
            status,
            order_id,
            source,
        )
        self.records.append(record)
        if order_id:
            self.trades[order_id] = trade
        self.store.record(
            order_id,
            symbol,
            "BUY",
            quantity,
            entry_limit,
            stop,
            target,
            status,
            source,
            self.broker.filled_quantity(trade),
        )
        self.last_signal_key.add(key)
        self.pending_signals.pop(symbol, None)
        self.queue.remove(symbol)
        return record

    async def refresh_status(self, record, trade):
        record.status = str(self.broker.order_status(trade) or record.status).upper()
        self.store.record(
            record.order_id,
            record.symbol,
            record.action,
            record.quantity,
            record.entry_limit,
            record.stop,
            record.target,
            record.status,
            record.source,
            self.broker.filled_quantity(trade),
        )
        return record

    async def refresh_all_statuses(self):
        for record in self.records:
            trade = self.trades.get(record.order_id)
            if trade is not None:
                await self.refresh_status(record, trade)
