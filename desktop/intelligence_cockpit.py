from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import settings
from . import dashboard as legacy
from .dashboard_v2 import MainWindow as PremiumDashboard, STYLE as PREMIUM_STYLE


STYLE = PREMIUM_STYLE + r"""
/* Screenshot polish layer: presentation only, no trading logic changes. */
QLabel#Brand { font-size:19pt; font-weight:900; letter-spacing:0px; }
QFrame#Panel { border-radius:11px; }
QFrame#Metric { border-radius:9px; }
QLabel#Section { font-size:9.5pt; font-weight:900; }
QLabel#CockpitSub { color:#7890ad; font-size:8pt; }
QLabel#HeroGood { color:#34d399; font-size:27pt; font-weight:950; }
QLabel#HeroBad { color:#fb7185; font-size:27pt; font-weight:950; }
QLabel#HeroWarn { color:#fbbf24; font-size:27pt; font-weight:950; }
QTableWidget { outline:0; }
QScrollBar:vertical { width:8px; background:#081321; margin:0; }
QScrollBar::handle:vertical { background:#29445f; min-height:24px; border-radius:4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
"""


class MainWindow(PremiumDashboard):
    """Final premium cockpit with stable integration-state handling.

    This layer intentionally changes presentation only. Broker/scanner/risk
    behavior remains inherited from the proven dashboard/controller stack.
    """

    def _data_source_changed(self, value):
        # The legacy dashboard reused ``self.data_source`` both for the
        # QComboBox widget and for its string value. Keep the widget intact and
        # store the selected value separately so changing to IBKR cannot destroy
        # the UI control during construction.
        self.selected_data_source = str(value)
        self._log(f"DATA SOURCE | {self.selected_data_source}")
        if self.selected_data_source == "TradingView":
            self._log("TradingView selected | optional alerts enter through webhook queue")
        else:
            self._log("IBKR selected | primary broker scanner/data path")

    def _sidebar(self):
        side = super()._sidebar()
        side.setFixedWidth(182)
        for label in side.findChildren(QLabel):
            if label.objectName() == "Brand":
                label.setText("AI TRADER")
                label.setMinimumWidth(150)
        return side

    def _topbar(self):
        top = super()._topbar()

        # Recover horizontal breathing room without removing any control.
        self.search.setFixedWidth(120)
        self.symbol.setFixedWidth(70)
        self.timeframe.setFixedWidth(76)
        if isinstance(self.data_source, QComboBox):
            self.data_source.setFixedWidth(82)

        self.tv_btn.setText("TV")
        self.tv_btn.setToolTip("TradingView optional connection/status")
        self.tv_btn.setFixedWidth(42)
        self.connect_btn.setMinimumWidth(88)
        self.start_btn.setMinimumWidth(88)
        self.pause_btn.setFixedWidth(55)
        self.disconnect_btn.setMinimumWidth(72)
        self.auto_exec_btn.setMinimumWidth(126)
        return top

    @staticmethod
    def _clean_panel(title: str, subtitle: str = ""):
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(legacy.lab(title, "Section"))
        header.addStretch(1)
        if subtitle:
            sub = legacy.lab(subtitle, "CockpitSub")
            header.addWidget(sub)
        layout.addLayout(header)
        return frame, layout

    def _dashboard_page(self):
        # Build the legacy page off-screen first so every legacy attribute used
        # by broker/order handlers continues to exist.
        self._legacy_dashboard = legacy.MainWindow._dashboard_page(self)

        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        top = QGridLayout()
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(8)
        top.addWidget(self._decision_card(), 0, 0, 1, 5)
        top.addWidget(self._strategy_card(), 0, 5, 1, 4)
        top.addWidget(self._news_card(), 0, 9, 1, 3)
        root.addLayout(top, 3)

        middle = QGridLayout()
        middle.setHorizontalSpacing(8)
        middle.addWidget(self._portfolio_risk_card(), 0, 0, 1, 4)
        middle.addWidget(self._shadow_card(), 0, 4, 1, 5)
        middle.addWidget(self._quick_card(), 0, 9, 1, 3)
        root.addLayout(middle, 2)

        opportunities, ol = self._clean_panel("OPPORTUNITIES & WATCHLIST", "scanner ranking")
        self.opportunity_table = self._table([
            "#", "Symbol", "Signal", "Regime", "Score", "Confidence",
            "News", "Risk", "Status", "Last Update",
        ])
        self.opportunity_table.verticalHeader().setDefaultSectionSize(25)
        self.opportunity_table.setMinimumHeight(190)
        ol.addWidget(self.opportunity_table)
        root.addWidget(opportunities, 2)
        return page

    def _decision_card(self):
        frame, layout = self._clean_panel("FINAL DECISION", "signal engine")

        head = QHBoxLayout()
        head.setSpacing(8)
        self.v2_symbol = legacy.lab("—", "Title")
        self.v2_meta = legacy.lab("Waiting for scanner", "Muted")
        head.addWidget(self.v2_symbol)
        head.addWidget(self.v2_meta)
        head.addStretch(1)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        box = QFrame()
        box.setObjectName("DecisionBox")
        box.setMinimumWidth(140)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 8, 12, 8)
        self.v2_action = QLabel("WAIT")
        self.v2_action.setObjectName("HeroWarn")
        self.v2_bias = legacy.lab("NO ACTIVE SIGNAL", "Muted")
        bl.addWidget(self.v2_action)
        bl.addWidget(self.v2_bias)
        row.addWidget(box, 2)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(6)
        self.v2_score = legacy.Metric("SCORE", "—", "Fusion score")
        self.v2_conf = legacy.Metric("CONFIDENCE", "—", "Model agreement")
        self.v2_move = legacy.Metric("EXPECTED MOVE", "—", "Target-derived")
        metrics.addWidget(self.v2_score, 0, 0)
        metrics.addWidget(self.v2_conf, 0, 1)
        metrics.addWidget(self.v2_move, 0, 2)
        holder = QWidget()
        holder.setLayout(metrics)
        row.addWidget(holder, 5)
        layout.addLayout(row)

        foot = QHBoxLayout()
        self.v2_horizon = legacy.lab("Horizon: —", "Muted")
        self.v2_reason = legacy.lab("Waiting for a completed analysis cycle.", "Muted")
        self.v2_reason.setWordWrap(True)
        foot.addWidget(self.v2_horizon, 1)
        foot.addWidget(self.v2_reason, 4)
        layout.addLayout(foot)
        return frame

    def _strategy_card(self):
        frame, layout = self._clean_panel("STRATEGY VOTES", "multi-alpha fusion")
        self.v2_strategy = self._table(["Strategy", "Signal", "Confidence", "Weight", "Contribution"])
        self.v2_strategy.verticalHeader().setDefaultSectionSize(25)
        self.v2_strategy.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for name in ["Williams", "Breakout", "Momentum", "Trend", "Volume", "News", "Adaptive"]:
            r = self.v2_strategy.rowCount()
            self.v2_strategy.insertRow(r)
            for c, value in enumerate([name, "—", "—", "—", "—"]):
                self.v2_strategy.setItem(r, c, QTableWidgetItem(value))
        self.v2_strategy.setMinimumHeight(218)
        layout.addWidget(self.v2_strategy)
        return frame

    def _news_card(self):
        frame, layout = self._clean_panel("NEWS INTELLIGENCE", "SerpAPI optional")
        self.v2_headline = legacy.lab("No event loaded", "StatusValue")
        self.v2_headline.setWordWrap(True)
        layout.addWidget(self.v2_headline)
        self.v2_event = legacy.lab("EVENT: —", "Blue")
        layout.addWidget(self.v2_event)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        self.v2_impact = legacy.Metric("IMPACT", "—", "event strength")
        self.v2_up = legacy.Metric("BULLISH", "—", "probability")
        self.v2_neutral = legacy.Metric("NEUTRAL", "—", "probability")
        self.v2_down = legacy.Metric("BEARISH", "—", "probability")
        grid.addWidget(self.v2_impact, 0, 0, 1, 3)
        grid.addWidget(self.v2_up, 1, 0)
        grid.addWidget(self.v2_neutral, 1, 1)
        grid.addWidget(self.v2_down, 1, 2)
        layout.addLayout(grid)
        note = legacy.lab("News supports the decision; it never triggers execution alone.", "Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return frame

    def _portfolio_risk_card(self):
        frame, layout = self._clean_panel("RISK & PORTFOLIO", "fail-closed controls")
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        self.v2_positions = legacy.Metric("POSITIONS", "—", f"Max {settings.max_active_positions}")
        self.v2_open = legacy.Metric("OPEN ORDERS", "—", f"Max {settings.max_open_orders}")
        self.v2_exec = legacy.Metric("EXECUTED", "—", f"Max {settings.max_executed_orders}")
        self.v2_account = legacy.Metric("NET LIQUIDATION", "—", "IBKR")
        for i, metric in enumerate([self.v2_positions, self.v2_open, self.v2_exec, self.v2_account]):
            grid.addWidget(metric, 0, i)
        layout.addLayout(grid)
        self.v2_risk_status = legacy.lab(
            "CORRELATION / SECTOR / DRAWDOWN: waiting for portfolio context", "Muted"
        )
        self.v2_risk_status.setWordWrap(True)
        layout.addWidget(self.v2_risk_status)
        return frame

    def _shadow_card(self):
        frame, layout = self._clean_panel("SHADOW / CALIBRATION", "research comparison")
        self.v2_shadow = self._table(["Model", "Signal", "Score", "Agreement"])
        self.v2_shadow.verticalHeader().setDefaultSectionSize(24)
        self.v2_shadow.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.v2_shadow.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for name in ["Legacy (v1)", "Signal v2", "Adaptive", "News-aware", "Calibrated"]:
            r = self.v2_shadow.rowCount()
            self.v2_shadow.insertRow(r)
            for c, value in enumerate([name, "WAIT", "—", "—"]):
                self.v2_shadow.setItem(r, c, QTableWidgetItem(value))
        self.v2_shadow.setFixedHeight(150)
        layout.addWidget(self.v2_shadow)
        self.v2_calibration = legacy.lab("Calibration: waiting for mature samples", "Muted")
        layout.addWidget(self.v2_calibration)
        return frame

    def _quick_card(self):
        frame, layout = self._clean_panel("QUICK SETTINGS", "current limits")
        self.v2_quick = self._table(["Setting", "Value"])
        self.v2_quick.horizontalHeader().setVisible(False)
        self.v2_quick.verticalHeader().setDefaultSectionSize(21)
        self.v2_quick.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.v2_quick.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rows = [
            ("Order Quantity", settings.fixed_quantity),
            ("Max Positions", settings.max_active_positions),
            ("Max Open Orders", settings.max_open_orders),
            ("Scope", settings.execution_count_scope),
            ("Risk / Trade", f"{settings.risk_per_trade * 100:.2f}%"),
            ("Reward / Risk", settings.reward_risk),
            ("News Shadow", "ON" if settings.news_shadow_enabled else "OFF"),
            ("Auto Execution", "ON" if getattr(settings, "auto_execution_enabled", False) else "OFF"),
        ]
        for key, value in rows:
            r = self.v2_quick.rowCount()
            self.v2_quick.insertRow(r)
            self.v2_quick.setItem(r, 0, QTableWidgetItem(str(key)))
            self.v2_quick.setItem(r, 1, QTableWidgetItem(str(value)))
        self.v2_quick.setFixedHeight(174)
        layout.addWidget(self.v2_quick)
        return frame

    def on_scan(self, data):
        super().on_scan(data)
        action = str(getattr(data.get("signal"), "action", "HOLD") or "HOLD").upper()
        self.v2_action.setObjectName(
            "HeroGood" if action == "BUY" else "HeroBad" if action == "SELL" else "HeroWarn"
        )
        self.v2_action.style().unpolish(self.v2_action)
        self.v2_action.style().polish(self.v2_action)
        self.v2_action.update()
