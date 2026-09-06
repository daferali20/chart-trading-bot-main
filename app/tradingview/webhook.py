from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.tradingview.store import TradingViewSignalStore
from app.tradingview.status import utc_now

app = FastAPI(title="Chart Trading Bot - TradingView Webhook")
store = TradingViewSignalStore()


class TradingViewSignal(BaseModel):
    symbol: str
    action: str
    price: float | None = None
    stop: float | None = None
    target: float | None = None
    score: int = 0
    message: str | None = None


@app.get("/health")
async def health():
    status = store.status()
    return {
        "ok": True,
        "service": "tradingview-webhook",
        "enabled": settings.tradingview_webhook_enabled,
        "paper_trading": settings.paper_trading,
        "server_time": utc_now(),
        "last_received_at": status["last_received_at"],
        "pending": status["pending"],
    }


@app.get("/status")
async def status():
    return {
        "ok": True,
        "service": "tradingview-webhook",
        "enabled": settings.tradingview_webhook_enabled,
        "server_time": utc_now(),
        **store.status(),
    }


@app.post("/webhook/tradingview")
async def tradingview_webhook(
    payload: TradingViewSignal,
    x_webhook_token: str | None = Header(default=None),
):
    if not settings.tradingview_webhook_enabled:
        store.record_failure("TradingView webhook disabled")
        raise HTTPException(503, "TradingView webhook disabled")

    if settings.tradingview_webhook_token and x_webhook_token != settings.tradingview_webhook_token:
        store.record_failure("Invalid webhook token")
        raise HTTPException(401, "Invalid webhook token")

    action = payload.action.upper().strip()
    if action not in {"BUY", "SELL", "HOLD"}:
        store.record_failure("Invalid action")
        raise HTTPException(400, "Invalid action")

    symbol = payload.symbol.upper().strip()
    if not symbol:
        store.record_failure("Symbol is required")
        raise HTTPException(400, "Symbol is required")

    if action == "BUY" and (payload.stop is None or payload.price is None):
        store.record_failure("BUY requires price and stop")
        raise HTTPException(400, "BUY requires price and stop")

    signal_id = store.add(payload)
    return {
        "accepted": True,
        "queued": action in {"BUY", "SELL"},
        "signal_id": signal_id,
        "symbol": symbol,
        "action": action,
    }
