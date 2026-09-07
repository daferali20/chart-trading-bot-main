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
from app.strategy.adaptive_engine import DEFAULT_ADAPTIVE_SIGNAL_ENGINE
from app.strategy.chart_strategy import evaluate_chart
from app.strategy.signal_engine import DEFAULT_SIGNAL_ENGINE
from app.tradingview.bridge import TradingViewBridge


class IndependentScannerWorker(QObject):
    """Persistent IBKR worker. Connection, scanner start/pause and disconnect are separate controls.

    The legacy chart signal remains the execution-facing signal. Signal Engine v2,
    Market Regime and Adaptive analysis are attached as read-only intelligence
    context for the premium desktop cockpit and shadow comparison.
    """

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

    @staticmethod
    def _display_alpha_name(name: str) -> str:
        value = str(name or "")
        if value.endswith("Alpha"):
            value = value[:-5]
        aliases = {
            "Williams": "Williams",
            "Momentum": "Momentum",
            "Trend": "Trend",
            "Breakout": "Breakout",
            "Volume": "Volume",
            "MultiTimeframe": "MTF",
        }
        return aliases.get(value, value or "Alpha")

    @staticmethod
    def _ui_direction(direction) -> str:
        value = str(getattr(direction, "value", direction) or "NEUTRAL").upper()
        if value == "LONG":
            return "BUY"
        if value == "SHORT":
            return "SELL"
        return "HOLD"

    def _intelligence_context(self, legacy_signal, advanced, adaptive) -> dict:
        contribution_by_name = {
            str(item.get("name")): item
            for item in (advanced.contributions or ())
            if isinstance(item, dict)
        }
        votes: dict[str, dict] = {}
        for alpha in advanced.alphas:
            contribution = contribution_by_name.get(str(alpha.name), {})
            votes[self._display_alpha_name(alpha.name)] = {
                "signal": self._ui_direction(alpha.direction),
                "confidence": float(alpha.confidence),
                "weight": float(alpha.weight),
                "contribution": round(float(contribution.get("effective_vote", 0.0)), 4),
                "reason": str(alpha.reason or ""),
            }

        adaptive_insight = adaptive.insight
        votes["Adaptive"] = {
            "signal": str(adaptive_insight.action),
            "confidence": float(adaptive_insight.confidence),
            "weight": "REGIME",
            "contribution": len(adaptive.selected_model_names),
            "reason": ", ".join(adaptive.selected_model_names) or "No approved model selected",
        }

        legacy_action = str(getattr(legacy_signal, "action", "HOLD") or "HOLD").upper()
        legacy_score = float(getattr(legacy_signal, "score", 0.0) or 0.0)
        v2_agreement = legacy_action == str(advanced.action).upper()
        adaptive_agreement = str(adaptive_insight.action).upper() == str(advanced.action).upper()

        return {
            "market_regime": str(getattr(advanced.regime, "value", advanced.regime)),
            "regime_confidence": float(advanced.regime_confidence),
            "confidence": float(advanced.confidence),
            "quality": float(advanced.quality),
            "advanced_horizon": advanced.horizon,
            "advanced_expected_pct": advanced.expected_pct,
            "advanced_signal": {
                "action": str(advanced.action),
                "score": float(advanced.score),
                "confidence": float(advanced.confidence),
                "quality": float(advanced.quality),
                "expected_pct": advanced.expected_pct,
                "horizon": advanced.horizon,
                "reasons": list(advanced.reasons),
            },
            "alpha_votes": votes,
            "shadow": {
                "legacy": {
                    "signal": legacy_action,
                    "score": legacy_score,
                    "agreement": "BASELINE",
                },
                "v2": {
                    "signal": str(advanced.action),
                    "score": float(advanced.score),
                    "agreement": "YES" if v2_agreement else "NO",
                },
                "adaptive": {
                    "signal": str(adaptive_insight.action),
                    "score": float(adaptive_insight.score),
                    "agreement": "YES" if adaptive_agreement else "NO",
                },
            },
            "calibration_status": "waiting for mature samples",
        }

    async def analyze_symbol(self, symbol, market_df=None):
        async with self.semaphore:
            try:
                raw_df = await self.client.historical_bars(symbol)

                # Read-only intelligence stack. Nothing below this block can
                # submit an order; the legacy chart signal remains execution-facing.
                advanced = DEFAULT_SIGNAL_ENGINE.analyze(raw_df, market_df=market_df)
                adaptive = DEFAULT_ADAPTIVE_SIGNAL_ENGINE.analyze(raw_df, market_df=market_df)

                df = add_indicators(raw_df)
                df = add_chart_indicators(df)
                signal = evaluate_chart(df)
                context = chart_context(df)
                context.update(self._intelligence_context(signal, advanced, adaptive))

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

    async def _market_context(self):
        try:
            return await self.client.historical_bars(
                "SPY",
                duration=settings.history_duration,
                timeframe=settings.timeframe,
            )
        except Exception as exc:
            self.status.emit(f"MARKET REGIME | SPY benchmark unavailable | {exc}")
            return None

    async def _scan_once(self):
        gainers = await top_gainers(self.client.ib, settings.top_gainers_count)
        custom = load_watchlist(settings.watchlist_file)
        symbols = merge_candidates(gainers, custom)
        market_df = await self._market_context()
        results = await asyncio.gather(*(self.analyze_symbol(s, market_df=market_df) for s in symbols))
        for symbol, signal, context, chart_data, error in results:
            if error:
                self.error.emit(f"{symbol}: {error}")
                continue
            self.scan.emit({"symbol": symbol, "signal": signal, "context": context, "chart": chart_data})
            if signal.action != "BUY" or signal.stop is None:
                continue
            if not settings.auto_execution_enabled:
                self.status.emit(
                    f"AUTO EXECUTION OFF | {symbol} BUY kept inside bot | analysis only"
                )
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
                    if settings.auto_execution_enabled:
                        tv_processed, tv_submitted = await self.tv.process_pending()
                        if tv_processed or tv_submitted:
                            self.status.emit(
                                f"TradingView queue | processed={tv_processed} | submitted={tv_submitted}"
                            )
                    positions, open_orders, executed = await self._snapshot()
                    self.status.emit(
                        f"Portfolio verified | positions={len(positions)} | open orders={len(open_orders)} | executed={executed}/{settings.max_executed_orders}"
                    )
                    now = time.monotonic()
                    if self.scan_enabled.is_set() and now - last_scan >= self.interval:
                        mode = "PAPER EXECUTION" if settings.auto_execution_enabled else "ANALYSIS ONLY"
                        self.status.emit(f"Scanner running | analyzing watchlist | {mode}")
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
        mode = "PAPER EXECUTION" if settings.auto_execution_enabled else "ANALYSIS ONLY"
        self.status.emit(f"Scanner STARTED | {mode}")

    @Slot()
    def pause_scanning(self):
        self.scan_enabled.clear()
        self.status.emit("Scanner PAUSED")

    @Slot()
    def stop(self):
        self.scan_enabled.clear()
        self.running = False
