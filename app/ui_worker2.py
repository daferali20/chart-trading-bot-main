from __future__ import annotations

import asyncio
import threading
import time

import pandas as pd
from PySide6.QtCore import QObject, Signal, Slot

from app.analysis.chart_engine import add_chart_indicators, chart_context
from app.analysis.indicators import add_indicators
from app.broker.ibkr import IBKRClient
from app.config import settings
from app.data.providers import YahooDataProvider
from app.execution.order_manager import OrderManager
from app.scanner import load_watchlist, merge_candidates, top_gainers
from app.strategy.adaptive_engine import DEFAULT_ADAPTIVE_SIGNAL_ENGINE
from app.strategy.chart_strategy import evaluate_chart
from app.strategy.signal_engine import DEFAULT_SIGNAL_ENGINE
from app.tradingview.bridge import TradingViewBridge


def yahoo_fallback_spec(timeframe: str) -> tuple[str, str, str | None]:
    """Map the desktop timeframe to a Yahoo-compatible fallback request.

    Yahoo has no native 10-minute interval, so 5-minute bars are fetched and
    resampled to 10 minutes locally.  The requested periods are intentionally
    modest because this path is for temporary live-analysis continuity, not the
    long-horizon research datasets.
    """

    value = str(timeframe or "").strip().lower()
    mapping = {
        "1 min": ("7d", "1m", None),
        "5 mins": ("1mo", "5m", None),
        "10 mins": ("1mo", "5m", "10min"),
        "15 mins": ("1mo", "15m", None),
        "30 mins": ("1mo", "30m", None),
        "1 hour": ("3mo", "60m", None),
        "1 day": ("5y", "1d", None),
    }
    return mapping.get(value, ("1mo", "5m", "10min"))


def prepare_yahoo_live_frame(frame: pd.DataFrame, resample_rule: str | None = None) -> pd.DataFrame:
    """Convert normalized Yahoo bars to the live worker's timestamp schema."""

    if frame is None or frame.empty:
        raise ValueError("Yahoo fallback frame is empty")

    out = frame.copy()
    if "timestamp" not in out.columns:
        if "date" not in out.columns:
            raise ValueError("Yahoo fallback frame has no date/timestamp column")
        out = out.rename(columns={"date": "timestamp"})

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    out = out.sort_values("timestamp", kind="stable")

    if resample_rule:
        indexed = out.set_index("timestamp")
        out = (
            indexed.resample(resample_rule, label="left", closed="left")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )

    return out[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


class IndependentScannerWorker(QObject):
    """Persistent IBKR worker with safe Yahoo analysis fallback.

    IBKR remains the broker and preferred live-market source.  If IBKR cannot
    provide historical bars for a symbol, Yahoo may temporarily provide bars
    for analysis/Shadow continuity.  Any signal built from Yahoo fallback data
    is explicitly forbidden from reaching order submission.

    The legacy chart signal remains the execution-facing signal when the data
    source is IBKR. Signal Engine v2, Market Regime and Adaptive analysis are
    attached as read-only intelligence context for the premium cockpit.
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
        self._yahoo_providers: dict[tuple[str, str], YahooDataProvider] = {}

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

    @staticmethod
    def _short_error(exc: Exception, limit: int = 150) -> str:
        text = " ".join(str(exc).split())
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def _yahoo_provider(self) -> tuple[YahooDataProvider, str | None, str]:
        period, interval, resample_rule = yahoo_fallback_spec(settings.timeframe)
        key = (period, interval)
        provider = self._yahoo_providers.get(key)
        if provider is None:
            provider = YahooDataProvider(
                period=period,
                interval=interval,
                auto_adjust=True,
                repair=True,
                prepost=False,
                timeout=15.0,
            )
            self._yahoo_providers[key] = provider
        label = f"Yahoo {interval}" + (f"→{resample_rule}" if resample_rule else "")
        return provider, resample_rule, label

    async def _historical_with_fallback(self, symbol: str) -> tuple[pd.DataFrame, str, str | None]:
        try:
            frame = await self.client.historical_bars(symbol)
            return frame, "IBKR", None
        except Exception as ibkr_error:
            if not getattr(settings, "yahoo_fallback_enabled", True):
                raise

            provider, resample_rule, label = self._yahoo_provider()
            try:
                yahoo_frame = await provider.historical_bars(symbol)
                live_frame = prepare_yahoo_live_frame(yahoo_frame, resample_rule)
                if len(live_frame) < 60:
                    raise RuntimeError(f"only {len(live_frame)} usable bars returned")
                reason = self._short_error(ibkr_error)
                self.status.emit(
                    f"DATA FALLBACK | {symbol.upper()} | IBKR unavailable -> {label} | analysis only"
                )
                return live_frame, "YAHOO_FALLBACK", reason
            except Exception as yahoo_error:
                raise RuntimeError(
                    f"IBKR data failed ({self._short_error(ibkr_error)}); "
                    f"Yahoo fallback also failed ({self._short_error(yahoo_error)})"
                ) from yahoo_error

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

    async def analyze_symbol(self, symbol, market_df=None, market_source="IBKR"):
        async with self.semaphore:
            try:
                raw_df, data_source, fallback_reason = await self._historical_with_fallback(symbol)

                # Read-only intelligence stack. Nothing below this block can
                # submit an order; the legacy chart signal remains execution-facing.
                advanced = DEFAULT_SIGNAL_ENGINE.analyze(raw_df, market_df=market_df)
                adaptive = DEFAULT_ADAPTIVE_SIGNAL_ENGINE.analyze(raw_df, market_df=market_df)

                df = add_indicators(raw_df)
                df = add_chart_indicators(df)
                signal = evaluate_chart(df)
                context = chart_context(df)
                context.update(self._intelligence_context(signal, advanced, adaptive))
                context.update(
                    {
                        "data_source": data_source,
                        "market_data_source": market_source,
                        "execution_data_safe": data_source == "IBKR",
                        "data_fallback_reason": fallback_reason,
                    }
                )

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
            frame, source, _ = await self._historical_with_fallback("SPY")
            if source != "IBKR":
                self.status.emit("MARKET REGIME | SPY using Yahoo fallback temporarily")
            return frame, source
        except Exception as exc:
            self.status.emit(f"MARKET REGIME | SPY benchmark unavailable | {self._short_error(exc)}")
            return None, "UNAVAILABLE"

    async def _scan_once(self):
        custom = load_watchlist(settings.watchlist_file)
        try:
            gainers = await top_gainers(self.client.ib, settings.top_gainers_count)
        except Exception as exc:
            gainers = []
            self.status.emit(
                f"IBKR SCANNER FALLBACK | scanner unavailable | using watchlist | {self._short_error(exc)}"
            )

        symbols = merge_candidates(gainers, custom)
        if not symbols:
            symbols = [str(settings.symbol).upper()]
            self.status.emit("IBKR SCANNER FALLBACK | watchlist empty | using active symbol")

        market_df, market_source = await self._market_context()
        results = await asyncio.gather(
            *(self.analyze_symbol(s, market_df=market_df, market_source=market_source) for s in symbols)
        )

        for symbol, signal, context, chart_data, error in results:
            if error:
                self.error.emit(f"{symbol}: {error}")
                continue

            self.scan.emit({"symbol": symbol, "signal": signal, "context": context, "chart": chart_data})
            if signal.action != "BUY" or signal.stop is None:
                continue

            if (context or {}).get("data_source") != "IBKR":
                self.status.emit(
                    f"EXECUTION BLOCKED | {symbol} BUY uses Yahoo fallback data | analysis only until IBKR data returns"
                )
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
