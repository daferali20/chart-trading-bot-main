from __future__ import annotations

import pandas as pd
from app.config import settings

try:
    from ib_async import IB, Stock, MarketOrder, LimitOrder
except ImportError:
    IB = Stock = MarketOrder = LimitOrder = None


class IBKRClient:
    def __init__(self):
        self.ib = IB() if IB else None

    async def connect(self):
        if self.ib is None:
            raise RuntimeError("ib_async is not installed. Run: pip install -r requirements.txt")
        if settings.paper_trading and settings.ib_port not in (7497, 4002):
            raise RuntimeError(
                "Paper trading requires TWS port 7497 or IB Gateway port 4002. "
                f"Current port={settings.ib_port}"
            )
        if not self.ib.isConnected():
            await self.ib.connectAsync(
                settings.ib_host,
                settings.ib_port,
                clientId=settings.ib_client_id,
                timeout=10,
            )

    async def disconnect(self):
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

    async def account_value(self) -> float:
        await self.connect()
        values = await self.ib.accountSummaryAsync()
        for item in values:
            if item.tag == "NetLiquidation" and (not settings.account or item.account == settings.account):
                return float(item.value)
        raise RuntimeError("NetLiquidation was not available from IBKR")

    async def historical_bars(self, symbol: str | None = None):
        await self.connect()
        symbol = (symbol or settings.symbol).upper()
        contract = Stock(symbol, settings.exchange, settings.currency)
        qualified = await self.ib.qualifyContractsAsync(contract)
        if not qualified:
            raise RuntimeError(f"Contract not found: {symbol}")
        bars = await self.ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=settings.history_duration,
            barSizeSetting=settings.timeframe,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
            keepUpToDate=False,
        )
        if not bars:
            raise RuntimeError(f"IBKR returned no historical bars for {symbol}")
        df = pd.DataFrame([bar.__dict__ for bar in bars])
        if df.empty:
            raise RuntimeError(f"Historical data is empty for {symbol}")
        if "date" in df.columns:
            df = df.rename(columns={"date": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise RuntimeError(f"Missing IBKR columns: {missing}")
        return df[required].copy()

    async def current_position(self, symbol: str) -> float:
        await self.connect()
        for position in self.ib.positions():
            contract = getattr(position, "contract", None)
            psymbol = getattr(contract, "symbol", "") if contract else ""
            if psymbol.upper() == symbol.upper():
                return float(getattr(position, "position", 0) or 0)
        return 0.0

    async def portfolio_positions(self):
        await self.connect()
        result = []
        for position in self.ib.positions():
            quantity = float(getattr(position, "position", 0) or 0)
            contract = getattr(position, "contract", None)
            symbol = getattr(contract, "symbol", "") if contract else ""
            if symbol and quantity != 0:
                result.append({"symbol": symbol.upper(), "quantity": quantity})
        return result

    async def active_trade_count(self) -> int:
        positions = await self.portfolio_positions()
        open_orders = await self.open_orders()
        symbols = {p["symbol"].upper() for p in positions}
        for trade in open_orders:
            symbol = getattr(getattr(trade, "contract", None), "symbol", "")
            action = str(getattr(getattr(trade, "order", None), "action", ""))
            status = self.order_status(trade)
            if symbol and action.upper() == "BUY" and status not in {"Filled", "Cancelled", "Inactive", "ApiCancelled"}:
                symbols.add(symbol.upper())
        return len(symbols)

    async def market_price(self, symbol: str) -> float:
        await self.connect()
        contract = Stock(symbol.upper(), settings.exchange, settings.currency)
        qualified = await self.ib.qualifyContractsAsync(contract)
        if not qualified:
            raise RuntimeError(f"Contract not found: {symbol}")
        ticker = self.ib.reqMktData(contract, "", False, False)
        await self.ib.sleep(1)
        for price in (ticker.marketPrice(), ticker.last, ticker.close):
            if price is not None and not pd.isna(price):
                return float(price)
        raise RuntimeError(f"No market price available for {symbol}")

    async def place_market_order(self, symbol: str, action: str, quantity: int):
        if not settings.paper_trading:
            raise RuntimeError("Live trading is disabled by design in this version.")
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")
        await self.connect()
        contract = Stock(symbol.upper(), settings.exchange, settings.currency)
        qualified = await self.ib.qualifyContractsAsync(contract)
        if not qualified:
            raise RuntimeError(f"Contract not found: {symbol}")
        order = MarketOrder(action.upper(), int(quantity), transmit=True)
        return self.ib.placeOrder(contract, order)

    async def place_limit_order(self, symbol: str, action: str, quantity: int, limit_price: float):
        if not settings.paper_trading:
            raise RuntimeError("Live trading is disabled by design in this version.")
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if limit_price <= 0:
            raise ValueError("Limit price must be positive")
        await self.connect()
        contract = Stock(symbol.upper(), settings.exchange, settings.currency)
        qualified = await self.ib.qualifyContractsAsync(contract)
        if not qualified:
            raise RuntimeError(f"Contract not found: {symbol}")
        order = LimitOrder(action.upper(), int(quantity), float(limit_price), transmit=True)
        return self.ib.placeOrder(contract, order)

    async def cancel_order(self, trade):
        await self.connect()
        if trade is not None and getattr(trade, "order", None) is not None:
            self.ib.cancelOrder(trade.order)

    async def open_orders(self):
        await self.connect()
        return await self.ib.reqAllOpenOrdersAsync()

    def order_status(self, trade):
        if trade is None:
            return None
        status = getattr(trade, "orderStatus", None)
        return getattr(status, "status", None) if status else None

    def order_id(self, trade) -> str:
        order = getattr(trade, "order", None)
        oid = getattr(order, "orderId", None) if order else None
        return str(oid or "")

    def filled_quantity(self, trade) -> float:
        status = getattr(trade, "orderStatus", None)
        return float(getattr(status, "filled", 0) or 0) if status else 0.0
