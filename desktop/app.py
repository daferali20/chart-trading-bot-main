from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)

from app.config import settings
from app.ui_worker import ScannerWorker


STYLE = """
QMainWindow,QWidget { background:#070d18; color:#e6edf7; font-family:'Segoe UI'; font-size:10pt; }
QFrame#Side { background:#0a1220; border-right:1px solid #1c2b42; }
QFrame#Top,QFrame#Panel,QFrame#Metric { background:#0d1727; border:1px solid #1c2b42; border-radius:10px; }
QLabel#Brand { color:#f8fafc; font-size:20pt; font-weight:900; }
QLabel#Sub { color:#64748b; font-size:8pt; }
QLabel#Title { color:#f8fafc; font-size:16pt; font-weight:850; }
QLabel#Section { color:#dbeafe; font-size:10pt; font-weight:850; }
QLabel#MT { color:#7890ad; font-size:8pt; font-weight:750; }
QLabel#MV { color:#f8fafc; font-size:15pt; font-weight:900; }
QLabel#Muted { color:#8da0b8; }
QLabel#StatusValue { color:#dbeafe; font-weight:750; }
QLabel#Good { color:#34d399; font-weight:850; }
QLabel#Warn { color:#fbbf24; font-weight:850; }
QLabel#Bad { color:#fb7185; font-weight:850; }
QLabel#Blue { color:#60a5fa; font-weight:850; }
QPushButton { background:#142238; color:#dbeafe; border:1px solid #293a57; border-radius:7px; padding:8px 12px; }
QPushButton:hover { background:#1b2d49; }
QPushButton#Primary { background:#2563eb; color:white; border:1px solid #3b82f6; font-weight:850; }
QPushButton#Stop { background:#431827; color:#fecaca; font-weight:850; }
QPushButton#Emergency { background:#5b0b12; color:#fecaca; font-weight:900; border:1px solid #8f1d2a; }
QPushButton#Nav { text-align:left; background:transparent; border:0; color:#8da0b8; padding:10px 12px; }
QPushButton#Nav:hover,QPushButton#Nav:checked { background:#17243a; color:#f8fafc; }
QLineEdit,QComboBox { background:#091321; color:#e6edf7; border:1px solid #293a57; border-radius:6px; padding:7px; }
QTableWidget { background:#091321; alternate-background-color:#0d192b; gridline-color:#1b2940; border:0; selection-background-color:#1d4ed8; }
QHeaderView::section { background:#0e1929; color:#8fa4bd; border:0; padding:8px; font-weight:750; }
QPlainTextEdit { background:#060b13; color:#9aacbf; border:0; font-family:Consolas; font-size:9pt; }
QProgressBar { background:#091321; border:1px solid #293a57; border-radius:5px; text-align:center; color:#cbd5e1; min-height:10px; }
QProgressBar::chunk { background:#2563eb; border-radius:4px; }
"""


def lab(text='', name='Muted'):
    x = QLabel(str(text))
    x.setObjectName(name)
    return x


def panel(title):
    f = QFrame()
    f.setObjectName('Panel')
    l = QVBoxLayout(f)
    l.setContentsMargins(14, 12, 14, 12)
    l.setSpacing(8)
    l.addWidget(lab(title, 'Section'))
    return f, l


class Metric(QFrame):
    def __init__(self, title, value='—', sub=''):
        super().__init__()
        self.setObjectName('Metric')
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 9, 12, 9)
        l.setSpacing(2)
        l.addWidget(lab(title, 'MT'))
        self.value = lab(value, 'MV')
        self.sub = lab(sub, 'Muted')
        l.addWidget(self.value)
        l.addWidget(self.sub)


class MarketChart(QWidget):
    """Native Qt chart: candles, EMA50 and volume."""
    def __init__(self):
        super().__init__()
        self.data = {}
        self.setMinimumHeight(320)

    def set_data(self, data):
        self.data = data or {}
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(12, 10, -12, -10)
        p.fillRect(r, QColor('#08111e'))
        p.setPen(QPen(QColor('#1a2940'), 1))
        chart_h = int(r.height() * 0.76)
        chart = r.adjusted(0, 0, 0, -(r.height() - chart_h))
        volume = r.adjusted(0, chart_h + 8, 0, 0)

        closes = list(self.data.get('close') or [])
        opens = list(self.data.get('open') or [])
        highs = list(self.data.get('high') or [])
        lows = list(self.data.get('low') or [])
        volumes = list(self.data.get('volume') or [])
        ema = list(self.data.get('ema50') or [])
        n = min(len(closes), len(opens), len(highs), len(lows))
        if n < 2:
            p.setPen(QPen(QColor('#70839d'), 1))
            p.drawText(r, Qt.AlignCenter, 'Waiting for historical market data')
            return

        closes, opens, highs, lows = closes[-90:], opens[-90:], highs[-90:], lows[-90:]
        volumes = volumes[-90:] if volumes else []
        ema = ema[-90:] if ema else []
        n = min(len(closes), len(opens), len(highs), len(lows))
        lo, hi = min(lows[:n]), max(highs[:n])
        span = hi - lo or 1.0

        def y(v):
            return int(chart.bottom() - (float(v) - lo) / span * (chart.height() - 20) - 10)

        for i in range(1, 5):
            yy = int(chart.top() + chart.height() * i / 5)
            p.drawLine(chart.left(), yy, chart.right(), yy)

        step = max(3, chart.width() / n)
        body_w = max(2, int(step * 0.55))
        for i in range(n):
            x = int(chart.left() + step * (i + 0.5))
            yo, yc = y(opens[i]), y(closes[i])
            yh, yl = y(highs[i]), y(lows[i])
            rising = closes[i] >= opens[i]
            c = QColor('#34d399' if rising else '#fb7185')
            p.setPen(QPen(c, 1))
            p.drawLine(x, yh, x, yl)
            top, bottom = min(yo, yc), max(yo, yc)
            p.fillRect(x - body_w // 2, top, body_w, max(2, bottom - top), c)

        if len(ema) >= n:
            pts = []
            for i, v in enumerate(ema[-n:]):
                try:
                    if v is None:
                        continue
                    x = int(chart.left() + step * (i + 0.5))
                    pts.append((x, y(float(v))))
                except (TypeError, ValueError):
                    pass
            if len(pts) > 1:
                p.setPen(QPen(QColor('#60a5fa'), 2))
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a[0], a[1], b[0], b[1])

        if volumes:
            vmax = max(volumes) or 1.0
            for i, v in enumerate(volumes[-n:]):
                x = int(volume.left() + step * (i + 0.5))
                h = int((float(v) / vmax) * max(8, volume.height() - 4))
                p.fillRect(x - body_w // 2, volume.bottom() - h, body_w, h, QColor('#28415f'))

        p.setPen(QPen(QColor('#8fa4bd'), 1))
        p.drawText(chart.left(), chart.top() + 14, f'HIGH {hi:.4f}')
        p.drawText(chart.left(), chart.bottom() - 2, f'LOW {lo:.4f}')
        p.drawText(chart.right() - 120, chart.top() + 14, f'LAST {closes[-1]:.4f}')
        p.drawText(volume.left(), volume.top() + 12, 'VOLUME')
        p.drawText(volume.right() - 90, volume.top() + 12, 'EMA50')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AI Trader — IBKR Paper')
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)
        self.thread = None
        self.worker = None
        self.emergency_active = False
        self.broker_live = False
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.clock)
        self.timer.start(1000)
        self.clock()

    def _build_ui(self):
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._sidebar())

        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(16, 14, 16, 10)
        main.setSpacing(10)
        main.addWidget(self._topbar())
        main.addWidget(self._metrics())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._dashboard_page())
        self.pages.addWidget(self._portfolio_page())
        self.pages.addWidget(self._orders_page())
        self.pages.addWidget(self._ai_page())
        self.pages.addWidget(self._risk_page())
        self.pages.addWidget(self._settings_page())
        main.addWidget(self.pages, 1)
        main.addLayout(self._footer())
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

    def _sidebar(self):
        s = QFrame()
        s.setObjectName('Side')
        s.setFixedWidth(190)
        l = QVBoxLayout(s)
        l.setContentsMargins(14, 20, 14, 16)
        l.setSpacing(4)
        l.addWidget(lab('AI TRADER', 'Brand'))
        l.addWidget(lab('AUTOMATED EQUITY DESK', 'Sub'))
        l.addSpacing(18)
        self.nav = []
        names = ['Dashboard', 'Markets', 'Watchlist', 'Portfolio', 'Orders', 'AI Signals', 'Risk Control', 'Settings']
        mapping = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}
        for i, name in enumerate(names):
            b = QPushButton(name)
            b.setObjectName('Nav')
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _, btn=b, idx=i: self._nav(btn, idx, mapping))
            self.nav.append(b)
            l.addWidget(b)
        l.addStretch(1)
        self.side_ibkr = lab('IBKR  OFFLINE', 'Bad')
        self.side_tv = lab('TRADINGVIEW  OFFLINE', 'Muted')
        l.addWidget(self.side_ibkr)
        l.addWidget(self.side_tv)
        l.addSpacing(8)
        emergency = QPushButton('■  EMERGENCY STOP')
        emergency.setObjectName('Emergency')
        emergency.clicked.connect(self.stop)
        l.addWidget(emergency)
        return s

    def _nav(self, button, index, mapping):
        for b in self.nav:
            b.setChecked(b is button)
        self.pages.setCurrentIndex(mapping[index])
        self.page_title.setText(button.text())

    def _topbar(self):
        f = QFrame()
        f.setObjectName('Top')
        l = QHBoxLayout(f)
        box = QVBoxLayout()
        self.page_title = lab('Dashboard', 'Title')
        self.clock_label = lab('', 'Muted')
        box.addWidget(self.page_title)
        box.addWidget(self.clock_label)
        l.addLayout(box)
        l.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search symbol…')
        self.search.setFixedWidth(180)
        self.search.returnPressed.connect(self._select_search_symbol)
        l.addWidget(self.search)
        self.symbol = QComboBox()
        self.symbol.setEditable(True)
        self.symbol.addItem(settings.symbol)
        l.addWidget(self.symbol)
        self.connect_btn = QPushButton('Connect & Start')
        self.connect_btn.setObjectName('Primary')
        self.stop_btn = QPushButton('Stop')
        self.stop_btn.setObjectName('Stop')
        self.stop_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        l.addWidget(self.connect_btn)
        l.addWidget(self.stop_btn)
        return f

    def _select_search_symbol(self):
        value = self.search.text().strip().upper()
        if not value:
            return
        if self.symbol.findText(value) < 0:
            self.symbol.addItem(value)
        self.symbol.setCurrentText(value)
        self.log_line(f'Selected symbol {value}')

    def _metrics(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(9)
        self.m_ibkr = Metric('IBKR', 'DISCONNECTED', 'No live broker data')
        self.m_pos = Metric('POSITIONS', '—', 'Waiting for broker')
        self.m_open = Metric('OPEN ORDERS', '—', 'Waiting for broker')
        self.m_exec = Metric('EXECUTED', f'0 / {settings.max_executed_orders}', f'Scope: {settings.execution_count_scope}')
        self.m_gate = Metric('EXECUTION GATE', 'WAITING', 'Fail-closed')
        self.m_sig = Metric('LATEST SIGNAL', '—', 'AI / chart engine')
        for i, widget in enumerate([self.m_ibkr, self.m_pos, self.m_open, self.m_exec, self.m_gate, self.m_sig]):
            g.addWidget(widget, 0, i)
        return w

    def _dashboard_page(self):
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._center())
        split.addWidget(self._right())
        split.setSizes([930, 390])
        return split

    def _center(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        p, pl = panel('MARKET VIEW')
        h = QHBoxLayout()
        self.chart_symbol = lab('—', 'Title')
        self.chart_price = lab('—', 'MV')
        self.chart_change = lab('NO DATA', 'Muted')
        h.addWidget(self.chart_symbol)
        h.addWidget(self.chart_price)
        h.addWidget(self.chart_change)
        h.addStretch(1)
        self.chart_state = lab('Waiting for market data', 'Muted')
        h.addWidget(self.chart_state)
        pl.addLayout(h)
        self.chart = MarketChart()
        pl.addWidget(self.chart, 1)
        grid = QGridLayout()
        self.ctx = {}
        for i, (title, key) in enumerate([
            ('EMA50', 'ema50'), ('Williams %R', 'williams_r'), ('MFI 14', 'mfi14'),
            ('Volume Ratio', 'volume_ratio'), ('Cloud Top', 'cloud_top'), ('Cloud Bottom', 'cloud_bottom')
        ]):
            m = Metric(title)
            self.ctx[key] = m.value
            grid.addWidget(m, i // 3, i % 3)
        pl.addLayout(grid)
        self.cloud = lab('Cloud: —', 'Muted')
        pl.addWidget(self.cloud)
        l.addWidget(p, 1)

        q, ql = panel('SCANNER & RISK')
        form = QFormLayout()
        self.interval = QComboBox()
        self.interval.addItems(['30', '60', '120', '300'])
        self.interval.setCurrentText(str(settings.scan_interval_seconds))
        self.qty = QLineEdit(str(settings.fixed_quantity))
        self.tp = QLineEdit(str(settings.take_profit_percent))
        form.addRow('Scan interval', self.interval)
        form.addRow('Order quantity', self.qty)
        form.addRow('Take profit (%)', self.tp)
        form.addRow('Limits', lab(
            f'Max executed {settings.max_executed_orders}  •  Max positions {settings.max_active_positions}  •  Max open orders {settings.max_open_orders}',
            'Muted'))
        ql.addLayout(form)
        l.addWidget(q)

        r, rl = panel('LIVE SCANNER RESULTS')
        self.scan_table = self._table(['Symbol', 'Signal', 'Score', 'Entry', 'Stop', 'Target', 'TP %', 'Status'])
        rl.addWidget(self.scan_table)
        l.addWidget(r, 1)
        return w

    def _right(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        p, pl = panel('EXECUTION GATE')
        self.gate = lab('WAITING — BROKER OFFLINE', 'Warn')
        self.gate.setMinimumHeight(28)
        pl.addWidget(self.gate)
        self.bar = QProgressBar()
        self.bar.setRange(0, settings.max_executed_orders)
        self.bar.setValue(0)
        pl.addWidget(self.bar)
        self.gate_detail = lab('No broker verification yet. Orders fail closed.', 'Muted')
        self.gate_detail.setWordWrap(True)
        pl.addWidget(self.gate_detail)
        l.addWidget(p)

        a, al = panel('LATEST AI ANALYSIS')
        self.analysis = {}
        for name in ['Signal', 'Score', 'Entry', 'Stop', 'Target', 'R:R', 'Reasons', 'Execution']:
            row = QHBoxLayout()
            row.addWidget(lab(name, 'Muted'))
            val = lab('—', 'StatusValue')
            val.setWordWrap(True)
            row.addWidget(val, 1)
            al.addLayout(row)
            self.analysis[name] = val
        l.addWidget(a)

        o, ol = panel('RECENT ORDERS')
        self.orders = self._table(['Time', 'Symbol', 'Action', 'Qty', 'Entry', 'Stop', 'Target', 'Status', 'ID'])
        ol.addWidget(self.orders)
        l.addWidget(o, 1)

        x, xl = panel('LIVE ACTIVITY')
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        xl.addWidget(self.log)
        l.addWidget(x, 1)
        return w

    def _portfolio_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g = QGridLayout()
        self.account = Metric('NET LIQUIDATION', '—', 'IBKR account')
        self.pc = Metric('ACTIVE POSITIONS', '—', f'Max {settings.max_active_positions}')
        self.po = Metric('OPEN ORDERS', '—', f'Max {settings.max_open_orders}')
        g.addWidget(self.account, 0, 0)
        g.addWidget(self.pc, 0, 1)
        g.addWidget(self.po, 0, 2)
        l.addLayout(g)
        q, ql = panel('LIVE POSITIONS')
        self.positions = self._table(['Symbol', 'Quantity', 'Broker'])
        ql.addWidget(self.positions)
        l.addWidget(q, 1)
        return w

    def _orders_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        p, pl = panel('ORDER MONITOR')
        self.all_orders = self._table(['Time', 'Symbol', 'Action', 'Qty', 'Entry', 'Stop', 'Target', 'Status', 'Filled', 'ID'])
        pl.addWidget(self.all_orders)
        l.addWidget(p, 1)
        return w

    def _ai_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        p, pl = panel('AI SIGNAL CENTER')
        self.ai_title = lab('No signal received', 'Title')
        self.ai_state = lab('WAITING', 'Warn')
        self.ai_reason = lab('Latest scanner/TradingView decision appears here.', 'Muted')
        self.ai_reason.setWordWrap(True)
        pl.addWidget(self.ai_title)
        pl.addWidget(self.ai_state)
        pl.addWidget(self.ai_reason)
        l.addWidget(p)
        q, ql = panel('SIGNAL CONTEXT')
        self.ai_table = self._table(['Indicator', 'Value'])
        ql.addWidget(self.ai_table)
        l.addWidget(q, 1)
        return w

    def _risk_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        p, pl = panel('RISK CONTROL')
        f = QFormLayout()
        vals = [
            ('Max executed', settings.max_executed_orders),
            ('Max positions', settings.max_active_positions),
            ('Max open orders', settings.max_open_orders),
            ('Risk / trade', f'{settings.risk_per_trade * 100:.2f}%'),
            ('Reward / Risk', settings.reward_risk),
            ('ATR stop', settings.atr_stop_mult),
            ('Execution scope', settings.execution_count_scope),
            ('Trading mode', 'PAPER ONLY'),
        ]
        for k, v in vals:
            f.addRow(k, lab(v, 'StatusValue'))
        pl.addLayout(f)
        l.addWidget(p)
        q, ql = panel('EXECUTION POLICY')
        ql.addWidget(lab('Every order is held until fresh IBKR Positions + Open Orders + Risk + Max Executed checks pass.', 'Muted'))
        self.risk_state = lab('WAITING FOR BROKER VERIFICATION', 'Warn')
        ql.addWidget(self.risk_state)
        l.addWidget(q)
        l.addStretch(1)
        return w

    def _settings_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        p, pl = panel('SYSTEM SETTINGS')
        f = QFormLayout()
        rows = [
            ('IBKR Host', settings.ib_host), ('IBKR Port', settings.ib_port),
            ('Client ID', settings.ib_client_id), ('Exchange', settings.exchange),
            ('Currency', settings.currency), ('Timeframe', settings.timeframe),
            ('TradingView', f'{settings.tradingview_webhook_host}:{settings.tradingview_webhook_port}'),
            ('Mode', 'PAPER ONLY'), ('Webhook Token', '••••••••'),
        ]
        for k, v in rows:
            f.addRow(k, lab(v, 'StatusValue'))
        pl.addLayout(f)
        pl.addWidget(lab('Live trading is disabled by design. IBKR execution remains paper-only.', 'Warn'))
        l.addWidget(p)
        l.addStretch(1)
        return w

    def _footer(self):
        l = QHBoxLayout()
        self.status = lab('Disconnected', 'Muted')
        l.addWidget(self.status)
        l.addStretch(1)
        l.addWidget(lab('PAPER MODE', 'Warn'))
        l.addSpacing(12)
        l.addWidget(lab(f'MAX {settings.max_executed_orders} ORDERS', 'Muted'))
        return l

    @staticmethod
    def _table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        return t

    def clock(self):
        self.clock_label.setText(datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))

    def log_line(self, text):
        self.log.appendPlainText(f'[{datetime.now().strftime("%H:%M:%S")}] {text}')
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def start(self):
        if self.thread and self.thread.isRunning():
            return
        if self.emergency_active:
            self.emergency_active = False
            self.log_line('Emergency stop reset — new scanner session allowed')
        try:
            qty = int(self.qty.text())
            tp = float(self.tp.text())
            interval = int(self.interval.currentText())
        except ValueError:
            self.status.setText('Invalid scanner settings')
            return
        if qty <= 0 or tp <= 0 or interval <= 0:
            self.status.setText('Values must be positive')
            return
        settings.fixed_quantity = qty
        settings.take_profit_percent = tp
        settings.scan_interval_seconds = interval
        self.thread = QThread(self)
        self.worker = ScannerWorker(interval)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.on_status)
        self.worker.scan.connect(self.on_scan)
        self.worker.order.connect(self.on_order)
        self.worker.snapshot.connect(self.on_snapshot)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.connect_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.qty.setEnabled(False)
        self.tp.setEnabled(False)
        self.interval.setEnabled(False)
        self.side_ibkr.setText('IBKR  CONNECTING')
        self.side_ibkr.setObjectName('Warn')
        self._refresh_style(self.side_ibkr)
        self.log_line('Scanner started — waiting for fresh IBKR verification')

    def stop(self):
        self.emergency_active = True
        if self.worker:
            self.worker.stop()
        self.stop_btn.setEnabled(False)
        self.connect_btn.setEnabled(True)
        self.qty.setEnabled(True)
        self.tp.setEnabled(True)
        self.interval.setEnabled(True)
        self.status.setText('Emergency stop active — no new scanner orders')
        self.log_line('EMERGENCY STOP — scanner stopped; new orders will not be sent')
        self.gate.setText('EMERGENCY STOP')
        self.m_gate.value.setText('STOPPED')
        self.m_gate.sub.setText('New submissions disabled')
        self._refresh_style(self.gate)
        self._refresh_style(self.m_gate.value)

    def on_snapshot(self, data):
        positions = data.get('positions') or []
        opens = data.get('open_orders') or []
        executed = int(data.get('executed') or 0)
        maximum = int(data.get('maximum') or settings.max_executed_orders)
        account = data.get('account_value')
        connected = bool(data.get('connected'))
        if not connected:
            self.disconnected()
            return

        self.broker_live = True
        self.m_ibkr.value.setText('CONNECTED')
        self.m_ibkr.sub.setText('Fresh broker snapshot')
        self.m_ibkr.value.setObjectName('Good')
        self.m_pos.value.setText(str(len(positions)))
        self.m_pos.sub.setText('LIVE • fresh snapshot')
        self.m_open.value.setText(str(len(opens)))
        self.m_open.sub.setText('LIVE • fresh snapshot')
        self.m_exec.value.setText(f'{executed} / {maximum}')
        self.m_exec.sub.setText(f'Scope: {settings.execution_count_scope}')
        self.bar.setMaximum(maximum)
        self.bar.setValue(min(executed, maximum))
        self.account.value.setText(f'${account:,.2f}' if account is not None else '—')
        self.account.sub.setText('IBKR Net Liquidation' if account is not None else 'Account value unavailable')
        self.pc.value.setText(f'{len(positions)} / {settings.max_active_positions}')
        self.po.value.setText(f'{len(opens)} / {settings.max_open_orders}')
        self.side_ibkr.setText('IBKR  CONNECTED')
        self.side_ibkr.setObjectName('Good')
        self._refresh_style(self.side_ibkr)
        self._refresh_style(self.m_ibkr.value)

        self.positions.setRowCount(0)
        for pos in positions:
            self._add_position(pos)
        self.all_orders.setRowCount(0)
        for trade in opens:
            self._add_trade(self.all_orders, trade)

        if len(positions) >= settings.max_active_positions:
            gate_reason = f'Position limit reached: {len(positions)}/{settings.max_active_positions}. New BUY orders stay inside bot.'
            gate_state = 'BLOCKED / POSITION LIMIT'
        elif len(opens) >= settings.max_open_orders:
            gate_reason = f'Open-order limit reached: {len(opens)}/{settings.max_open_orders}. New orders stay inside bot.'
            gate_state = 'BLOCKED / OPEN ORDER LIMIT'
        elif executed >= maximum:
            gate_reason = f'Executed-order limit reached: {executed}/{maximum}. New orders stay inside bot.'
            gate_state = 'BLOCKED / EXECUTED LIMIT'
        else:
            gate_reason = 'Fresh Positions + Open Orders verified. Individual signal and risk gates still required.'
            gate_state = 'VERIFIED'

        self.gate_detail.setText(
            f'{gate_reason}\nPositions {len(positions)}/{settings.max_active_positions}  •  '
            f'Open Orders {len(opens)}/{settings.max_open_orders}  •  Executed {executed}/{maximum}'
        )
        self.risk_state.setText('BROKER VERIFIED — EXECUTION MAY PROCEED IF ALL GATES PASS')
        self.risk_state.setObjectName('Good')
        if not self.emergency_active:
            self.gate.setText(gate_state)
            self.m_gate.value.setText('BLOCKED' if gate_state.startswith('BLOCKED') else 'VERIFIED')
            self.m_gate.sub.setText('Position/Open/Risk limits' if gate_state.startswith('BLOCKED') else 'Fresh broker snapshot')
            self._refresh_style(self.gate)
            self._refresh_style(self.m_gate.value)
        self._refresh_style(self.risk_state)

    def _add_position(self, pos):
        r = self.positions.rowCount()
        self.positions.insertRow(r)
        vals = [pos.get('symbol', ''), pos.get('quantity', ''), 'IBKR LIVE']
        for i, v in enumerate(vals):
            self.positions.setItem(r, i, QTableWidgetItem(str(v)))

    def _add_trade(self, table, trade):
        row = table.rowCount()
        table.insertRow(row)
        order = getattr(trade, 'order', None)
        status = getattr(getattr(trade, 'orderStatus', None), 'status', '') or 'UNKNOWN'
        filled = getattr(getattr(trade, 'orderStatus', None), 'filled', 0) or 0
        contract = getattr(trade, 'contract', None)
        vals = [
            'LIVE', getattr(contract, 'symbol', '') if contract else '',
            getattr(order, 'action', '') if order else '',
            getattr(order, 'totalQuantity', '') if order else '',
            getattr(order, 'lmtPrice', '') or '—', '—', '—', status,
            filled, getattr(order, 'orderId', '') if order else ''
        ]
        for i, value in enumerate(vals[:table.columnCount()]):
            table.setItem(row, i, QTableWidgetItem(str(value)))

    def on_status(self, text):
        self.status.setText(text)
        self.log_line(text)
        if 'TradingView queue' in text:
            self.side_tv.setText('TRADINGVIEW  ACTIVE')
            self.side_tv.setObjectName('Good')
            self._refresh_style(self.side_tv)
        if 'ORDER SUBMITTED' in text:
            self.gate.setText('ORDER SUBMITTED')
            self.gate.setObjectName('Good')
            self.m_gate.value.setText('SUBMITTED')
            self.analysis['Execution'].setText('ORDER SUBMITTED')
        elif 'kept inside bot' in text:
            self.gate.setText('BLOCKED / QUEUED')
            self.gate.setObjectName('Warn')
            self.m_gate.value.setText('BLOCKED')
            self.m_gate.sub.setText('Order held inside bot')
            self.gate_detail.setText(text + '\nNo IBKR submission was made.')
            self.analysis['Execution'].setText('HELD INSIDE BOT — NO IBKR SUBMISSION')
        elif 'Portfolio verified' in text and not self.emergency_active:
            if self.broker_live:
                self.m_gate.value.setText('VERIFIED')
                self.m_gate.sub.setText('Fresh broker snapshot')
        elif 'Disconnected' in text:
            self.disconnected()
        self._refresh_style(self.gate)
        self._refresh_style(self.m_gate.value)

    def disconnected(self):
        self.broker_live = False
        self.m_ibkr.value.setText('DISCONNECTED')
        self.m_ibkr.sub.setText('No live broker data')
        self.m_ibkr.value.setObjectName('Bad')
        self.m_pos.value.setText('—')
        self.m_pos.sub.setText('Waiting for broker')
        self.m_open.value.setText('—')
        self.m_open.sub.setText('Waiting for broker')
        self.m_exec.sub.setText('Broker snapshot unavailable')
        self.m_gate.value.setText('WAITING')
        self.m_gate.sub.setText('Fail-closed')
        self.gate.setText('WAITING — BROKER OFFLINE')
        self.gate_detail.setText('Broker disconnected. No order may be submitted until a fresh broker snapshot is available.')
        self.positions.setRowCount(0)
        self.all_orders.setRowCount(0)
        self.side_ibkr.setText('IBKR  OFFLINE')
        self.side_ibkr.setObjectName('Bad')
        self.risk_state.setText('WAITING FOR BROKER VERIFICATION')
        self.risk_state.setObjectName('Warn')
        self._refresh_style(self.side_ibkr)
        self._refresh_style(self.m_ibkr.value)
        self._refresh_style(self.gate)
        self._refresh_style(self.m_gate.value)
        self._refresh_style(self.risk_state)

    def on_error(self, text):
        self.status.setText('Error: ' + text)
        self.gate.setText('FAIL-CLOSED')
        self.m_gate.value.setText('FAIL-CLOSED')
        self.m_gate.sub.setText('Broker/engine error')
        self.gate_detail.setText(text + '\nNo order may be submitted from this failed cycle.')
        self.log_line('ERROR: ' + text)
        self._refresh_style(self.gate)
        self._refresh_style(self.m_gate.value)

    def on_scan(self, data):
        signal = data['signal']
        symbol = data['symbol']
        ctx = data.get('context') or {}
        chart = data.get('chart') or {}
        self.chart_symbol.setText(symbol)
        self.chart_price.setText(f'{signal.entry:.4f}')
        self.chart_state.setText(f'Signal: {signal.action}  •  Score: {signal.score}')
        self.chart_change.setText('LIVE ANALYSIS')
        chart_payload = dict(chart)
        chart_payload['ema50'] = chart.get('ema50') or []
        self.chart.set_data(chart_payload)
        self.m_sig.value.setText(signal.action)
        self.m_sig.sub.setText(f'{symbol} • score {signal.score}')

        target = signal.target
        rr = '—'
        if signal.stop is not None and target is not None and signal.entry != signal.stop:
            rr = f'1 : {abs(target - signal.entry) / abs(signal.entry - signal.stop):.2f}'
        reasons = ' • '.join(signal.reasons) if signal.reasons else '—'
        execution = 'SELL HELD — exit manager pending' if signal.action == 'SELL' else ('BUY CANDIDATE — pending gate' if signal.action == 'BUY' else 'HOLD — no execution')
        values = [
            ('Signal', signal.action), ('Score', signal.score), ('Entry', f'{signal.entry:.4f}'),
            ('Stop', f'{signal.stop:.4f}' if signal.stop is not None else '—'),
            ('Target', f'{target:.4f}' if target is not None else '—'), ('R:R', rr),
            ('Reasons', reasons), ('Execution', execution)
        ]
        for key, value in values:
            self.analysis[key].setText(str(value))

        self.ai_title.setText(f'{symbol} — {signal.action} — Score {signal.score}')
        self.ai_state.setText('BUY CANDIDATE' if signal.action == 'BUY' else ('SELL SIGNAL — HELD' if signal.action == 'SELL' else 'HOLD'))
        self.ai_state.setObjectName('Good' if signal.action == 'BUY' else ('Bad' if signal.action == 'SELL' else 'Warn'))
        self.ai_reason.setText(reasons)
        self.ai_table.setRowCount(0)
        for key, value in ctx.items():
            row = self.ai_table.rowCount()
            self.ai_table.insertRow(row)
            self.ai_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.ai_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self._refresh_style(self.ai_state)

        for key, widget in self.ctx.items():
            value = ctx.get(key)
            if value is None:
                widget.setText('—')
            elif isinstance(value, (int, float)):
                widget.setText(f'{value:.4f}')
            else:
                widget.setText(str(value))

        if ctx.get('above_cloud'):
            self.cloud.setText('Cloud: ABOVE — bullish structure')
            self.cloud.setObjectName('Good')
        elif ctx.get('below_cloud'):
            self.cloud.setText('Cloud: BELOW — bearish structure')
            self.cloud.setObjectName('Bad')
        else:
            self.cloud.setText('Cloud: —')
            self.cloud.setObjectName('Muted')
        self._refresh_style(self.cloud)

        row = next((i for i in range(self.scan_table.rowCount()) if self.scan_table.item(i, 0) and self.scan_table.item(i, 0).text() == symbol), -1)
        if row < 0:
            row = self.scan_table.rowCount()
            self.scan_table.insertRow(row)
        status = 'SELL HELD' if signal.action == 'SELL' else ('BUY CANDIDATE' if signal.action == 'BUY' else 'HOLD')
        vals = [
            symbol, signal.action, signal.score, f'{signal.entry:.4f}',
            f'{signal.stop:.4f}' if signal.stop is not None else '—',
            f'{signal.target:.4f}' if signal.target is not None else '—',
            f'{settings.take_profit_percent:.2f}%', status
        ]
        for i, value in enumerate(vals):
            self.scan_table.setItem(row, i, QTableWidgetItem(str(value)))

    def on_order(self, record):
        for table in (self.orders, self.all_orders):
            row = table.rowCount()
            table.insertRow(row)
            vals = [
                record.time, record.symbol, record.action, record.quantity,
                f'{record.entry_limit:.4f}',
                f'{record.stop:.4f}' if record.stop is not None else '—',
                f'{record.target:.4f}' if record.target is not None else '—',
                record.status, getattr(record, 'filled_quantity', 0), record.order_id
            ]
            for i, value in enumerate(vals[:table.columnCount()]):
                table.setItem(row, i, QTableWidgetItem(str(value)))
        self.log_line(f'ORDER {record.action} {record.symbol} qty={record.quantity} id={record.order_id}')

    @staticmethod
    def _refresh_style(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    run()
