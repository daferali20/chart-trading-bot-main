from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from app.config import settings
from .intelligence_cockpit import MainWindow as BaseCockpit, STYLE as BASE_STYLE


STYLE = BASE_STYLE + r"""
/* Final cockpit polish based on the live Windows screenshot. */
QLabel { background: transparent; }
QFrame#Top { background:#091827; }
QFrame#Panel { background:#0a1a2b; }
QFrame#Metric { background:#0b1b2d; }
QFrame#DecisionBox { background:#0c2236; }
QTableWidget { border-radius:8px; }
QHeaderView::section { padding:6px 7px; }
"""


class MainWindow(BaseCockpit):
    """Final presentation layer for the live intelligence cockpit.

    TradingView remains available from the sidebar as an optional integration,
    so the redundant top-bar button is hidden. Live v2/regime context is shown
    alongside the execution-facing chart decision without changing which signal
    the order manager uses.
    """

    def _topbar(self):
        top = super()._topbar()
        if hasattr(self, "tv_btn"):
            self.tv_btn.hide()
        self.search.setFixedWidth(132)
        self.symbol.setFixedWidth(72)
        self.timeframe.setFixedWidth(78)
        if hasattr(self, "data_source"):
            self.data_source.setFixedWidth(84)
        return top

    def on_scan(self, data):
        super().on_scan(data)
        context = (data or {}).get("context") or {}
        advanced = context.get("advanced_signal") or {}
        legacy_signal = (data or {}).get("signal")
        legacy_action = str(getattr(legacy_signal, "action", "HOLD") or "HOLD").upper()
        data_source = str(context.get("data_source") or "IBKR").upper()
        market_source = str(context.get("market_data_source") or "IBKR").upper()
        fallback_active = data_source != "IBKR"

        source_label = "YAHOO FALLBACK" if fallback_active else "IBKR"
        if advanced:
            v2_action = str(advanced.get("action") or "HOLD").upper()
            v2_score = advanced.get("score")
            try:
                score_text = f"{float(v2_score):.1f}"
            except Exception:
                score_text = str(v2_score or "—")
            self.v2_meta.setText(
                f"{settings.timeframe}  •  {source_label}  •  execution {legacy_action}  •  v2 {v2_action} {score_text}"
            )
            self.m_conf.sub.setText("Signal v2 ensemble")

            expected = advanced.get("expected_pct")
            if expected is not None:
                try:
                    self.v2_move.value.setText(f"{float(expected):+.2f}%")
                    self.v2_move.sub.setText("V2 expected move")
                except Exception:
                    pass

            horizon = advanced.get("horizon")
            if horizon:
                self.v2_horizon.setText(f"V2 horizon: {horizon}")

        if fallback_active:
            self.m_sig.sub.setText("Yahoo fallback • analysis only")
            self.m_gate.value.setText("DATA FALLBACK")
            self.m_gate.sub.setText("Yahoo data • IBKR execution blocked")
        elif not getattr(settings, "auto_execution_enabled", False):
            self.m_gate.value.setText("ANALYSIS ONLY")
            self.m_gate.sub.setText("Auto Execution OFF")

        regime_confidence = context.get("regime_confidence")
        regime = str(context.get("market_regime") or "—").upper()
        if regime != "—" and regime_confidence is not None:
            regime_source = "Yahoo fallback" if market_source != "IBKR" else "IBKR/SPY"
            try:
                self.m_regime.sub.setText(
                    f"{regime_source} • {float(regime_confidence):.0f}% confidence"
                )
            except Exception:
                self.m_regime.sub.setText(f"{regime_source} market regime")

        if not settings.news_shadow_enabled:
            # News remains visibly optional instead of looking broken or absent.
            for row in range(self.v2_strategy.rowCount()):
                item = self.v2_strategy.item(row, 0)
                if item and item.text() == "News":
                    self.v2_strategy.setItem(row, 1, QTableWidgetItem("OFF"))
                    self.v2_strategy.setItem(row, 2, QTableWidgetItem("—"))
                    self.v2_strategy.setItem(row, 3, QTableWidgetItem("—"))
                    self.v2_strategy.setItem(row, 4, QTableWidgetItem("optional"))
                    break
            if self.v2_shadow.rowCount() > 3:
                self.v2_shadow.setItem(3, 1, QTableWidgetItem("OFF"))
                self.v2_shadow.setItem(3, 3, QTableWidgetItem("optional"))

        self.opportunity_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
