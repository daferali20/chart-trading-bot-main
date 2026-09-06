from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QThread, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QSplitter, QSizePolicy,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QListWidget, QDoubleSpinBox, QSpinBox
)

from app.config import settings
from app.ui_worker import ScannerWorker

try:
    from desktop.tradingview_window import TradingViewConnectionWindow
except ImportError:
    TradingViewConnectionWindow = None

STYLE = """
QMainWindow,QWidget { background:#070d18; color:#e6edf7; font-family:'Segoe UI'; font-size:10pt; }
QFrame#Side { background:#0a1220; border-right:1px solid #1c2b42; }
QFrame#Top,QFrame#Panel,QFrame#Metric { background:#0d1727; border:1px solid #1c2b42; border-radius:10px; }
QFrame#Panel { min-width:0px; }
QSplitter::handle { background:#16243a; }
QSplitter::handle:hover { background:#29476d; }
QTableWidget { font-size:9pt; }
QLabel#Brand { color:#f8fafc; font-size:20pt; font-weight:900; }
QLabel#Sub { color:#64748b; font-size:8pt; }
QLabel#Title { color:#f8fafc; font-size:17pt; font-weight:900; }
QLabel#Section { color:#dbeafe; font-size:10pt; font-weight:850; }
QLabel#MT { color:#7890ad; font-size:8pt; font-weight:750; }
QLabel#MV { color:#f8fafc; font-size:15pt; font-weight:900; }
QLabel#Muted { color:#8da0b8; }
QLabel#Good { color:#34d399; font-weight:850; }
QLabel#Warn { color:#fbbf24; font-weight:850; }
QLabel#Bad { color:#fb7185; font-weight:850; }
QLabel#Blue { color:#60a5fa; font-weight:850; }
QPushButton { background:#142238; color:#dbeafe; border:1px solid #293a57; border-radius:7px; padding:8px 12px; }
QPushButton:hover { background:#1b2d49; }
QPushButton:disabled { color:#52647c; background:#0e1827; }
QPushButton#Primary { background:#2563eb; color:white; border:1px solid #3b82f6; font-weight:850; }
QPushButton#Stop { background:#431827; color:#fecaca; font-weight:850; }
QPushButton#Emergency { background:#5b0b12; color:#fecaca; font-weight:900; border:1px solid #8f1d2a; }
QPushButton#Nav { text-align:left; background:transparent; border:0; color:#8da0b8; padding:10px 12px; }
QPushButton#Nav:hover,QPushButton#Nav:checked { background:#17243a; color:#f8fafc; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#091321; color:#e6edf7; border:1px solid #293a57; border-radius:6px; padding:7px; }
QTableWidget { background:#091321; alternate-background-color:#0d192b; gridline-color:#1b2940; border:0; selection-background-color:#1d4ed8; }
QHeaderView::section { background:#0e1929; color:#8fa4bd; border:0; padding:8px; font-weight:750; }
QProgressBar { background:#091321; border:1px solid #293a57; border-radius:5px; text-align:center; color:#cbd5e1; min-height:12px; }
QProgressBar::chunk { background:#2563eb; border-radius:4px; }
QListWidget { background:#091321; border:1px solid #1c2b42; border-radius:7px; }
QListWidget::item { padding:8px; }
QListWidget::item:selected { background:#1d4ed8; }
"""

def lab(text="", name="Muted"):
    x = QLabel(str(text)); x.setObjectName(name); return x

def panel(title):
    f=QFrame(); f.setObjectName("Panel"); l=QVBoxLayout(f); l.setContentsMargins(14,12,14,12); l.setSpacing(8); l.addWidget(lab(title,"Section")); return f,l

class Metric(QFrame):
    def __init__(self,title,value="—",sub=""):
        super().__init__(); self.setObjectName("Metric"); l=QVBoxLayout(self); l.setContentsMargins(12,9,12,9); l.setSpacing(2); l.addWidget(lab(title,"MT")); self.value=lab(value,"MV"); self.sub=lab(sub); l.addWidget(self.value); l.addWidget(self.sub)

class MarketChart(QWidget):
    def __init__(self):
        super().__init__(); self.data={}; self.zoom=1.0; self.offset=0; self.drag_start=None; self.setMinimumHeight(220); self.setMouseTracking(True)
    def set_data(self,data): self.data=data or {}; self.zoom=1.0; self.offset=0; self.update()
    def reset(self): self.zoom=1.0; self.offset=0; self.update()
    def _window(self):
        n=len(self.data.get("close") or []); visible=max(20,min(n,int(n/self.zoom))) if n else 0; max_start=max(0,n-visible); start=max(0,min(max_start,max_start-self.offset)); return start,visible
    def wheelEvent(self,event): self.zoom=max(0.6,min(6.0,self.zoom*(1.18 if event.angleDelta().y()>0 else 1/1.18))); self.update()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton: self.drag_start=event.position().toPoint()
    def mouseMoveEvent(self,event):
        if self.drag_start is not None and event.buttons() & Qt.LeftButton:
            dx=event.position().toPoint().x()-self.drag_start.x(); n=len(self.data.get("close") or []); _,visible=self._window(); px=max(3.0,(self.width()-40)/max(1,visible)); self.offset+=int(-dx/px); self.offset=max(0,min(max(0,n-visible),self.offset)); self.drag_start=event.position().toPoint(); self.update()
    def mouseReleaseEvent(self,event): self.drag_start=None
    def mouseDoubleClickEvent(self,event): self.reset()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing,False); r=self.rect().adjusted(10,8,-10,-8); p.fillRect(r,QColor("#08111e")); closes=list(self.data.get("close") or []); opens=list(self.data.get("open") or []); highs=list(self.data.get("high") or []); lows=list(self.data.get("low") or []); vols=list(self.data.get("volume") or []); ema=list(self.data.get("ema50") or []); n=min(map(len,(closes,opens,highs,lows))) if closes else 0
        if n<2: p.setPen(QColor("#70839d")); p.drawText(r,Qt.AlignCenter,"Waiting for historical market data"); return
        start,visible=self._window(); end=min(n,start+visible); opens,highs,lows,closes=opens[start:end],highs[start:end],lows[start:end],closes[start:end]; vols=vols[start:end] if vols else []; ema=ema[start:end] if len(ema)>=end else []; n=len(closes); lo=min(lows); hi=max(highs); span=hi-lo or 1.0; chart_h=int(r.height()*0.74); chart=r.adjusted(0,0,0,-(r.height()-chart_h)); volume=r.adjusted(0,chart_h+6,0,0)
        def y(v): return int(chart.bottom()-((float(v)-lo)/span)*(chart.height()-22)-11)
        p.setPen(QPen(QColor("#1a2940"),1))
        for i in range(1,5): yy=int(chart.top()+chart.height()*i/5); p.drawLine(chart.left(),yy,chart.right(),yy)
        step=max(4.0,chart.width()/n); body=max(2,int(step*.58))
        for i in range(n):
            x=int(chart.left()+step*(i+.5)); yo,yc,yh,yl=y(opens[i]),y(closes[i]),y(highs[i]),y(lows[i]); c=QColor("#34d399" if closes[i]>=opens[i] else "#fb7185"); p.setPen(QPen(c,1)); p.drawLine(x,yh,x,yl); p.fillRect(x-body//2,min(yo,yc),body,max(2,abs(yc-yo)),c)
        if len(ema)==n:
            pts=[]
            for i,v in enumerate(ema):
                if v is not None: pts.append((int(chart.left()+step*(i+.5)),y(float(v))))
            p.setPen(QPen(QColor("#60a5fa"),2))
            for a,b in zip(pts,pts[1:]): p.drawLine(a[0],a[1],b[0],b[1])
        if vols:
            vmax=max(vols) or 1.0
            for i,v in enumerate(vols): x=int(volume.left()+step*(i+.5)); h=int((float(v)/vmax)*max(8,volume.height()-8)); p.fillRect(x-body//2,volume.bottom()-h,body,h,QColor("#28415f"))
        p.setPen(QColor("#8fa4bd")); p.drawText(chart.left(),chart.top()+14,f"HIGH {hi:.4f}"); p.drawText(chart.right()-115,chart.top()+14,f"LAST {closes[-1]:.4f}"); p.drawText(chart.left(),chart.bottom()-2,f"LOW {lo:.4f}"); p.drawText(volume.left(),volume.top()+12,"VOLUME"); p.drawText(volume.right()-75,volume.top()+12,"EMA50")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("AI Trader — IBKR Paper"); self.resize(1440,900); self.setMinimumSize(1180,760); self.thread=None; self.worker=None; self.broker_live=False; self.emergency_active=False; self.scan_cache={}; self.snapshot={}; self.tv_window=None; self.data_source="TradingView"; self._build_ui(); self.clock_timer=QTimer(self); self.clock_timer.timeout.connect(self.clock); self.clock_timer.start(1000); self.clock(); self.tv_timer=QTimer(self); self.tv_timer.timeout.connect(self.refresh_tradingview_status); self.tv_timer.start(1500); self.refresh_tradingview_status()
    def _build_ui(self):
        root=QWidget(); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0); outer.addWidget(self._sidebar()); content=QWidget(); main=QVBoxLayout(content); main.setContentsMargins(16,14,16,10); main.setSpacing(10); main.addWidget(self._topbar()); main.addWidget(self._metrics()); self.pages=QStackedWidget();
        for builder in (self._dashboard_page,self._markets_page,self._watchlist_page,self._portfolio_page,self._orders_page,self._ai_page,self._risk_page,self._settings_page): self.pages.addWidget(builder())
        main.addWidget(self.pages,1)
        footer_widget=self._footer()
        main.addWidget(footer_widget)
        outer.addWidget(content,1); self.setCentralWidget(root)
    def _sidebar(self):
        s=QFrame(); s.setObjectName("Side"); s.setFixedWidth(178); l=QVBoxLayout(s); l.setContentsMargins(14,20,14,16); l.setSpacing(4); l.addWidget(lab("AI TRADER","Brand")); l.addWidget(lab("AUTOMATED EQUITY DESK","Sub")); l.addSpacing(18); self.nav=[]
        for i,name in enumerate(["Dashboard","Markets","Watchlist","Portfolio","Orders","AI Signals","Risk Control","Settings"]): b=QPushButton(name); b.setObjectName("Nav"); b.setCheckable(True); b.setChecked(i==0); b.clicked.connect(lambda _,btn=b,idx=i:self._nav(btn,idx)); self.nav.append(b); l.addWidget(b)
        l.addStretch(1); self.side_ibkr=lab("IBKR  OFFLINE","Bad"); self.side_tv=lab("TRADINGVIEW  OFFLINE","Bad"); self.side_tv.mousePressEvent=lambda event:self.open_tradingview_window(); l.addWidget(self.side_ibkr); l.addWidget(self.side_tv); l.addSpacing(8); e=QPushButton("■  EMERGENCY STOP"); e.setObjectName("Emergency"); e.clicked.connect(self.emergency_stop); l.addWidget(e); return s
    def _nav(self,b,i):
        for x in self.nav: x.setChecked(x is b)
        self.pages.setCurrentIndex(i); self.page_title.setText(b.text());
        if i==2: self._reload_watchlist()
    def _topbar(self):
        f=QFrame(); f.setObjectName("Top"); l=QHBoxLayout(f); box=QVBoxLayout(); self.page_title=lab("Dashboard","Title"); self.clock_label=lab(""); box.addWidget(self.page_title); box.addWidget(self.clock_label); l.addLayout(box); l.addStretch(1); self.search=QLineEdit(); self.search.setPlaceholderText("Search symbol…"); self.search.setFixedWidth(150); self.search.returnPressed.connect(lambda:self._use_symbol(self.search.text())); l.addWidget(self.search); self.symbol=QComboBox(); self.symbol.setEditable(True); self.symbol.addItem(settings.symbol); self.symbol.setFixedWidth(82); self.symbol.currentTextChanged.connect(self._symbol_changed); l.addWidget(self.symbol); self.timeframe=QComboBox(); self.timeframe.addItems(["1 min","5 mins","10 mins","15 mins","30 mins","1 hour","1 day"]); self.timeframe.setCurrentText(settings.timeframe); self.timeframe.currentTextChanged.connect(lambda v:setattr(settings,"timeframe",v)); self.timeframe.setFixedWidth(82); l.addWidget(self.timeframe); self.data_source=QComboBox(); self.data_source.addItems(["TradingView","IBKR"]); self.data_source.setCurrentText("TradingView"); self.data_source.setToolTip("Choose the primary market-data / signal source"); self.data_source.setFixedWidth(102); self.data_source.currentTextChanged.connect(self._data_source_changed); l.addWidget(self.data_source); self.tv_btn=QPushButton("TradingView"); self.tv_btn.clicked.connect(self.open_tradingview_window); l.addWidget(self.tv_btn); self.connect_btn=QPushButton("Connect IBKR"); self.connect_btn.setObjectName("Primary"); self.connect_btn.clicked.connect(self.connect_ibkr); self.start_btn=QPushButton("Start Scanner"); self.start_btn.setEnabled(False); self.start_btn.clicked.connect(self.start_scanner); self.pause_btn=QPushButton("Pause"); self.pause_btn.setEnabled(False); self.pause_btn.clicked.connect(self.pause_scanner); self.disconnect_btn=QPushButton("Disconnect"); self.disconnect_btn.setEnabled(False); self.disconnect_btn.clicked.connect(self.disconnect_ibkr); [l.addWidget(x) for x in (self.connect_btn,self.start_btn,self.pause_btn,self.disconnect_btn)]; return f
    def _metrics(self):
        w=QWidget(); g=QGridLayout(w); g.setContentsMargins(0,0,0,0); g.setHorizontalSpacing(8); g.setVerticalSpacing(8); self.m_ibkr=Metric("IBKR","DISCONNECTED","No broker snapshot"); self.m_pos=Metric("POSITIONS","—","Waiting for broker"); self.m_open=Metric("OPEN ORDERS","—","Waiting for broker"); self.m_exec=Metric("EXECUTED",f"0 / {settings.max_executed_orders}",f"Scope: {settings.execution_count_scope}"); self.m_gate=Metric("EXECUTION GATE","WAITING","Fail-closed"); self.m_sig=Metric("LATEST SIGNAL","—","AI / chart engine"); [g.addWidget(x,0,i) for i,x in enumerate([self.m_ibkr,self.m_pos,self.m_open,self.m_exec,self.m_gate,self.m_sig])]; return w
    def _dashboard_page(self):
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        center = self._dashboard_center()
        right = self._dashboard_right()

        center.setMinimumWidth(620)
        right.setMinimumWidth(310)

        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 340])

        root.addWidget(splitter)
        return page

    def _dashboard_center(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        # Market View
        p, pl = panel("MARKET VIEW")
        p.setMinimumHeight(405)
        p.setMaximumHeight(455)

        h = QHBoxLayout()
        h.setSpacing(10)
        self.chart_symbol = lab("—", "Title")
        self.chart_price = lab("—", "MV")
        self.chart_change = lab("NO DATA")
        h.addWidget(self.chart_symbol)
        h.addWidget(self.chart_price)
        h.addWidget(self.chart_change)
        h.addStretch(1)
        hint = lab("Wheel: zoom  •  Drag: pan  •  Double click: reset", "MT")
        h.addWidget(hint)
        pl.addLayout(h)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        reset = QPushButton("Reset Chart")
        reset.clicked.connect(lambda: self.chart.reset())
        controls.addWidget(reset)
        self.chart_info = lab("Candles 120  •  EMA50  •  Volume", "MT")
        controls.addWidget(self.chart_info)
        controls.addStretch(1)
        pl.addLayout(controls)

        self.chart = MarketChart()
        self.chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pl.addWidget(self.chart, 1)

        self.ctx = {}
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        for i, (title, key) in enumerate([
            ("EMA50", "ema50"), ("Williams %R", "williams_r"),
            ("MFI 14", "mfi14"), ("Volume Ratio", "volume_ratio"),
            ("Cloud Top", "cloud_top"), ("Cloud Bottom", "cloud_bottom")
        ]):
            box = QFrame()
            box.setObjectName("Metric")
            box.setMinimumHeight(46)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(9, 5, 9, 5)
            bl.setSpacing(1)
            bl.addWidget(lab(title, "MT"))
            v = lab("—", "MV")
            v.setStyleSheet("font-size:12pt;")
            self.ctx[key] = v
            bl.addWidget(v)
            grid.addWidget(box, i // 3, i % 3)
        pl.addLayout(grid)
        self.cloud_label = lab("Cloud: —", "MT")
        pl.addWidget(self.cloud_label)

        l.addWidget(p)

        # Scanner / risk controls
        p2, p2l = panel("SCANNER & RISK")
        p2.setMinimumHeight(112)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self.interval = QComboBox()
        self.interval.addItems(["15", "30", "60", "120", "300"])
        self.interval.setCurrentText(str(settings.scan_interval_seconds))

        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1000000)
        self.quantity.setValue(settings.fixed_quantity)

        self.tp = QDoubleSpinBox()
        self.tp.setRange(.1, 500)
        self.tp.setDecimals(2)
        self.tp.setValue(settings.take_profit_percent)

        form.addWidget(lab("Scan interval (sec)", "MT"), 0, 0)
        form.addWidget(lab("Order quantity", "MT"), 0, 1)
        form.addWidget(lab("Take profit (%)", "MT"), 0, 2)
        form.addWidget(self.interval, 1, 0)
        form.addWidget(self.quantity, 1, 1)
        form.addWidget(self.tp, 1, 2)

        self.limit_info = lab(self._limits_text(), "MT")
        form.addWidget(lab("Limits", "MT"), 0, 3)
        form.addWidget(self.limit_info, 1, 3, 1, 2)
        p2l.addLayout(form)
        l.addWidget(p2)

        # Live scanner results
        p3, p3l = panel("LIVE SCANNER RESULTS")
        self.scan_table = self._table([
            "Symbol", "Signal", "Score", "Entry", "Stop",
            "Target", "TP %", "Status"
        ])
        self.scan_table.setMinimumHeight(150)
        self.scan_table.cellClicked.connect(
            lambda r, c: self._use_symbol(self.scan_table.item(r, 0).text())
            if self.scan_table.item(r, 0) else None
        )
        p3l.addWidget(self.scan_table)
        l.addWidget(p3, 1)

        return w

    def _dashboard_right(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        p, pl = panel("EXECUTION GATE")
        p.setMinimumHeight(145)
        self.gate_status = lab("WAITING", "Warn")
        self.gate_reason = lab("Connect IBKR before any execution decision.")
        self.gate_reason.setWordWrap(True)
        self.gate_progress = QProgressBar()
        self.gate_progress.setRange(0, settings.max_active_positions)
        self.gate_progress.setValue(0)
        pl.addWidget(self.gate_status)
        pl.addWidget(self.gate_progress)
        pl.addWidget(self.gate_reason)
        self.gate_stats = lab("Positions —  •  Open Orders —  •  Executed 0/7", "MT")
        pl.addWidget(self.gate_stats)
        l.addWidget(p)

        p, pl = panel("LATEST AI ANALYSIS")
        p.setMinimumHeight(205)
        self.ai_fields = {}
        for title, key in [
            ("Signal", "signal"), ("Score", "score"), ("Entry", "entry"),
            ("Stop", "stop"), ("Target", "target"), ("R:R", "rr"),
            ("Reasons", "reasons"), ("Execution", "execution")
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            label = lab(title, "MT")
            label.setFixedWidth(58)
            row.addWidget(label)
            v = lab("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(v, 1)
            self.ai_fields[key] = v
            pl.addLayout(row)
        l.addWidget(p, 2)

        p, pl = panel("RECENT ORDERS")
        self.recent_orders = self._table([
            "Time", "Symbol", "Action", "Qty", "Entry",
            "Stop", "Target", "Status"
        ])
        self.recent_orders.setMinimumHeight(125)
        pl.addWidget(self.recent_orders)
        l.addWidget(p, 2)

        p, pl = panel("LIVE ACTIVITY")
        self.activity = QTextEditCompat()
        self.activity.setMinimumHeight(110)
        pl.addWidget(self.activity)
        l.addWidget(p, 2)

        return w

    def _markets_page(self):
        page=QWidget(); l=QVBoxLayout(page); p,pl=panel("MARKETS / SCANNER"); row=QHBoxLayout(); row.addWidget(lab("Symbol","MT")); self.market_symbol=QLineEdit(settings.symbol); row.addWidget(self.market_symbol); b=QPushButton("Use Symbol"); b.clicked.connect(lambda:self._use_symbol(self.market_symbol.text())); row.addWidget(b); row.addStretch(1); pl.addLayout(row); self.market_table=self._table(["Symbol","Signal","Score","Entry","Stop","Target","Status"]); pl.addWidget(self.market_table); l.addWidget(p); return page
    def _watchlist_page(self):
        page=QWidget(); l=QHBoxLayout(page); p,pl=panel("WATCHLIST"); self.watch_list=QListWidget(); pl.addWidget(self.watch_list,1); row=QHBoxLayout(); self.watch_input=QLineEdit(); self.watch_input.setPlaceholderText("Ticker"); a=QPushButton("Add"); d=QPushButton("Remove"); s=QPushButton("Save Watchlist"); a.clicked.connect(self._watch_add); d.clicked.connect(self._watch_remove); s.clicked.connect(self._watch_save); row.addWidget(self.watch_input); row.addWidget(a); row.addWidget(d); row.addWidget(s); pl.addLayout(row); l.addWidget(p,1); p2,p2l=panel("WATCHLIST RULES"); p2l.addWidget(lab("One ticker per line. Double-click a ticker to load its latest analysis.")); p2l.addWidget(lab("Scanner merges watchlist symbols with top gainers.")); p2l.addStretch(1); l.addWidget(p2,1); self.watch_list.itemDoubleClicked.connect(lambda item:self._use_symbol(item.text())); self._reload_watchlist(); return page
    def _portfolio_page(self):
        page=QWidget(); l=QVBoxLayout(page); g=QGridLayout(); self.p_account=Metric("NET LIQUIDATION","—","IBKR"); self.p_positions=Metric("POSITIONS","—","Active"); self.p_open=Metric("OPEN ORDERS","—","Broker"); self.p_executed=Metric("EXECUTED","0/7",settings.execution_count_scope); [g.addWidget(x,0,i) for i,x in enumerate([self.p_account,self.p_positions,self.p_open,self.p_executed])]; l.addLayout(g); p,pl=panel("POSITIONS"); self.positions_table=self._table(["Symbol","Quantity","Side","Source"]); pl.addWidget(self.positions_table); l.addWidget(p,1); return page
    def _orders_page(self):
        page=QWidget(); l=QVBoxLayout(page); p,pl=panel("ORDER MONITOR"); self.orders_full=self._table(["Time","Symbol","Action","Qty","Entry","Stop","Target","Status","Order ID"]); pl.addWidget(self.orders_full); l.addWidget(p,1); return page
    def _ai_page(self):
        page=QWidget(); l=QVBoxLayout(page); p,pl=panel("AI SIGNAL CENTER"); self.ai_history=self._table(["Time","Symbol","Signal","Score","Entry","Stop","Target","Execution"]); pl.addWidget(self.ai_history); l.addWidget(p,1); return page
    def _risk_page(self):
        page=QWidget(); l=QVBoxLayout(page); g=QGridLayout(); self.risk_pos=Metric("ACTIVE POSITIONS","0/7","Hard gate"); self.risk_open=Metric("OPEN ORDERS","0/7","Hard gate"); self.risk_exec=Metric("EXECUTED","0/7",settings.execution_count_scope); self.risk_fraction=Metric("RISK / TRADE",f"{settings.risk_per_trade*100:.2f}%","Configured"); self.risk_rr=Metric("REWARD / RISK",f"{settings.reward_risk:.2f}","Configured"); [g.addWidget(x,0,i) for i,x in enumerate([self.risk_pos,self.risk_open,self.risk_exec,self.risk_fraction,self.risk_rr])]; l.addLayout(g); p,pl=panel("EXECUTION SAFETY"); pl.addWidget(lab("Every new order must pass fresh Positions + Open Orders + Risk + Max Executed checks.")); pl.addWidget(lab("If any check fails, the order stays inside the bot and is not submitted to IBKR.")); self.risk_gate=lab("GATE: WAITING","Warn"); pl.addWidget(self.risk_gate); l.addWidget(p); return page
    def _settings_page(self):
        page=QWidget(); l=QVBoxLayout(page); p,pl=panel("IBKR CONNECTION"); f=QFormLayout(); self.s_host=QLineEdit(settings.ib_host); self.s_port=QSpinBox(); self.s_port.setRange(1,65535); self.s_port.setValue(settings.ib_port); self.s_client=QSpinBox(); self.s_client.setRange(1,100000); self.s_client.setValue(settings.ib_client_id); f.addRow("Host",self.s_host); f.addRow("Port",self.s_port); f.addRow("Client ID",self.s_client); pl.addLayout(f); l.addWidget(p); p,pl=panel("TRADING / LIMITS"); f=QFormLayout(); self.s_qty=QSpinBox(); self.s_qty.setRange(1,1000000); self.s_qty.setValue(settings.fixed_quantity); self.s_max=QSpinBox(); self.s_max.setRange(1,100); self.s_max.setValue(settings.max_executed_orders); self.s_pos=QSpinBox(); self.s_pos.setRange(1,100); self.s_pos.setValue(settings.max_active_positions); self.s_open=QSpinBox(); self.s_open.setRange(1,100); self.s_open.setValue(settings.max_open_orders); self.s_scope=QComboBox(); self.s_scope.addItems(["DAY","ALL"]); self.s_scope.setCurrentText(settings.execution_count_scope); f.addRow("Order quantity",self.s_qty); f.addRow("Max executed",self.s_max); f.addRow("Max positions",self.s_pos); f.addRow("Max open orders",self.s_open); f.addRow("Execution count scope",self.s_scope); pl.addLayout(f); l.addWidget(p); p,pl=panel("RISK"); f=QFormLayout(); self.s_risk=QDoubleSpinBox(); self.s_risk.setRange(.01,100); self.s_risk.setDecimals(2); self.s_risk.setValue(settings.risk_per_trade*100); self.s_rr=QDoubleSpinBox(); self.s_rr.setRange(.1,20); self.s_rr.setDecimals(2); self.s_rr.setValue(settings.reward_risk); f.addRow("Risk / trade (%)",self.s_risk); f.addRow("Reward / Risk",self.s_rr); pl.addLayout(f); l.addWidget(p); b=QPushButton("SAVE SETTINGS TO .ENV"); b.setObjectName("Primary"); b.clicked.connect(self._save_settings); l.addWidget(b); l.addStretch(1); return page
    def _footer(self):
        w=QWidget(); l=QHBoxLayout(w); l.setContentsMargins(0,0,0,0); self.footer_status=lab("Disconnected"); l.addWidget(self.footer_status); l.addStretch(1); l.addWidget(lab("PAPER MODE","Warn")); l.addWidget(lab(f"MAX {settings.max_executed_orders} ORDERS")); return w
    def _table(self,headers):
        t=QTableWidget(0,len(headers)); t.setHorizontalHeaderLabels(headers); t.setAlternatingRowColors(True); t.setSelectionBehavior(QTableWidget.SelectRows); t.verticalHeader().setVisible(False); t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); return t
    def clock(self): self.clock_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    def _limits_text(self): return f"Max executed {settings.max_executed_orders}  •  Max positions {settings.max_active_positions}  •  Max open orders {settings.max_open_orders}"
    def _symbol_changed(self,v): self._show_cached_symbol(v)
    def _use_symbol(self,value):
        value=(value or "").strip().upper()
        if not value:return
        self.symbol.blockSignals(True)
        if self.symbol.findText(value)<0:self.symbol.addItem(value)
        self.symbol.setCurrentText(value); self.symbol.blockSignals(False); self.search.setText(value); self.market_symbol.setText(value); self._show_cached_symbol(value)
    def _show_cached_symbol(self,value):
        d=self.scan_cache.get((value or "").upper())
        if d:self.on_scan(d)
    def _data_source_changed(self, value):
        self.data_source = value
        self._log(f"DATA SOURCE | {value}")
        if value == "TradingView":
            self._log("TradingView selected | alerts enter through webhook queue")
        else:
            self._log("IBKR selected | broker scanner/data path")

    def open_tradingview_window(self):
        if TradingViewConnectionWindow is None:
            QMessageBox.warning(self, "TradingView", "desktop/tradingview_window.py was not found.")
            return
        if self.tv_window is None:
            self.tv_window = TradingViewConnectionWindow()
        self.tv_window.show()
        self.tv_window.raise_()
        self.tv_window.activateWindow()
        self.refresh_tradingview_status()

    def refresh_tradingview_status(self):
        url = "http://127.0.0.1:8000/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Trader/1.0"})
            with urllib.request.urlopen(req, timeout=0.8) as response:
                data = response.read().decode("utf-8", errors="ignore")
                if response.status == 200 and '"ok"' in data and 'true' in data.lower():
                    self.side_tv.setText("TRADINGVIEW  ONLINE")
                    self.side_tv.setObjectName("Good")
                    self.tv_btn.setText("TradingView ONLINE")
                else:
                    raise RuntimeError("health response not ready")
        except Exception:
            self.side_tv.setText("TRADINGVIEW  OFFLINE")
            self.side_tv.setObjectName("Bad")
            self.tv_btn.setText("TradingView")
        self.side_tv.style().unpolish(self.side_tv); self.side_tv.style().polish(self.side_tv)

    def connect_ibkr(self):
        if self.thread and self.thread.isRunning():return
        settings.ib_host=self.s_host.text().strip(); settings.ib_port=self.s_port.value(); settings.ib_client_id=self.s_client.value(); self.emergency_active=False
        self.thread=QThread(self); self.worker=ScannerWorker(int(self.interval.currentText())); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.status.connect(self.on_status); self.worker.scan.connect(self.on_scan); self.worker.order.connect(self.on_order); self.worker.snapshot.connect(self.on_snapshot); self.worker.error.connect(self.on_error); self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self._thread_finished); self.thread.start(); self.connect_btn.setEnabled(False); self.disconnect_btn.setEnabled(True); self.footer_status.setText("Connecting to IBKR…")
    def _thread_finished(self):
        if self.thread:self.thread.deleteLater()
        self.thread=None; self.worker=None; self.broker_live=False; self.connect_btn.setEnabled(True); self.start_btn.setEnabled(False); self.pause_btn.setEnabled(False); self.disconnect_btn.setEnabled(False); self.side_ibkr.setText("IBKR  OFFLINE"); self.side_ibkr.setObjectName("Bad"); self.side_ibkr.style().unpolish(self.side_ibkr); self.side_ibkr.style().polish(self.side_ibkr); self._clear_broker_metrics(); self.footer_status.setText("Disconnected")
    def start_scanner(self):
        if not self.worker or not self.thread or not self.thread.isRunning(): self._log("Connect to IBKR first."); return
        settings.fixed_quantity=self.quantity.value(); settings.take_profit_percent=self.tp.value(); settings.scan_interval_seconds=int(self.interval.currentText()); self.worker.interval=max(5,settings.scan_interval_seconds); self.worker.start_scanning(); self.start_btn.setEnabled(False); self.pause_btn.setEnabled(True); self._log("Scanner STARTED")
    def pause_scanner(self):
        if self.worker:self.worker.pause_scanning()
        self.start_btn.setEnabled(True); self.pause_btn.setEnabled(False); self._log("Scanner PAUSED")
    def disconnect_ibkr(self):
        if self.worker:self.worker.stop()
        self._log("Disconnect requested")
    def emergency_stop(self):
        self.emergency_active=True
        if self.worker:self.worker.stop()
        self.start_btn.setEnabled(False); self.pause_btn.setEnabled(False); self.gate_status.setText("EMERGENCY STOP"); self.gate_reason.setText("All new execution is stopped. Reconnect manually to resume."); self.risk_gate.setText("GATE: EMERGENCY STOP"); self._log("EMERGENCY STOP | new execution disabled")
    def on_status(self,text):
        self.footer_status.setText(text); self._log(text); u=text.upper()
        if "IBKR CONNECTED" in u:
            self.broker_live=True; self.side_ibkr.setText("IBKR  CONNECTED"); self.side_ibkr.setObjectName("Good"); self.side_ibkr.style().unpolish(self.side_ibkr); self.side_ibkr.style().polish(self.side_ibkr); self.m_ibkr.value.setText("CONNECTED"); self.m_ibkr.sub.setText("Fresh broker snapshot"); self.start_btn.setEnabled(not self.emergency_active)
        elif "DISCONNECTED" in u:self.broker_live=False; self._clear_broker_metrics()
        if "ORDER SUBMITTED" in u:self.gate_status.setText("SUBMITTED")
        elif "KEPT INSIDE BOT" in u:self.gate_status.setText("BLOCKED / QUEUED")
    def on_error(self,text): self.footer_status.setText("ERROR: "+text); self._log("ERROR | "+text); self.gate_status.setText("FAIL-CLOSED"); self.gate_reason.setText(text)
    def on_snapshot(self,data):
        self.snapshot=data or {}; pos=self.snapshot.get("positions") or []; opens=self.snapshot.get("open_orders") or []; exe=int(self.snapshot.get("executed") or 0); mx=int(self.snapshot.get("maximum") or settings.max_executed_orders); account=self.snapshot.get("account_value"); self.m_pos.value.setText(str(len(pos))); self.m_pos.sub.setText("LIVE • fresh snapshot"); self.m_open.value.setText(str(len(opens))); self.m_open.sub.setText("LIVE • fresh snapshot"); self.m_exec.value.setText(f"{exe} / {mx}"); self.m_exec.sub.setText(f"Scope: {settings.execution_count_scope}"); self.gate_progress.setRange(0,max(1,settings.max_active_positions)); self.gate_progress.setValue(min(len(pos),settings.max_active_positions)); self.gate_stats.setText(f"Positions {len(pos)}/{settings.max_active_positions}  •  Open Orders {len(opens)}/{settings.max_open_orders}  •  Executed {exe}/{mx}")
        if self.emergency_active:self.gate_status.setText("EMERGENCY STOP")
        elif len(pos)>=settings.max_active_positions:self.gate_status.setText("BLOCKED"); self.gate_reason.setText("Active-position limit reached. Orders remain inside bot.")
        elif len(opens)>=settings.max_open_orders:self.gate_status.setText("BLOCKED"); self.gate_reason.setText("Open-order limit reached. Orders remain inside bot.")
        elif exe>=mx:self.gate_status.setText("BLOCKED"); self.gate_reason.setText("Executed-order limit reached. Orders remain inside bot.")
        else:self.gate_status.setText("VERIFIED"); self.gate_reason.setText("Fresh Positions + Open Orders + Risk + Max Executed checks available.")
        self.risk_pos.value.setText(f"{len(pos)} / {settings.max_active_positions}"); self.risk_open.value.setText(f"{len(opens)} / {settings.max_open_orders}"); self.risk_exec.value.setText(f"{exe} / {mx}"); self.p_positions.value.setText(f"{len(pos)} / {settings.max_active_positions}"); self.p_open.value.setText(f"{len(opens)} / {settings.max_open_orders}"); self.p_executed.value.setText(f"{exe} / {mx}"); self.p_account.value.setText("—" if account is None else f"${float(account):,.2f}"); self.p_account.sub.setText("IBKR Net Liquidation" if account is not None else "Waiting for broker"); self.positions_table.setRowCount(0)
        for x in pos:
            row=self.positions_table.rowCount(); self.positions_table.insertRow(row); q=float(x.get("quantity") or 0); vals=[str(x.get("symbol","")),str(x.get("quantity","")),"LONG" if q>0 else "SHORT","IBKR live"]
            for c,v in enumerate(vals):self.positions_table.setItem(row,c,QTableWidgetItem(v))
        self.risk_gate.setText("GATE: "+self.gate_status.text())
    def _clear_broker_metrics(self):
        self.m_ibkr.value.setText("DISCONNECTED"); self.m_ibkr.sub.setText("No broker snapshot"); self.m_pos.value.setText("—"); self.m_pos.sub.setText("Waiting for broker"); self.m_open.value.setText("—"); self.m_open.sub.setText("Waiting for broker"); self.p_positions.value.setText("—"); self.p_open.value.setText("—"); self.p_account.value.setText("—"); self.positions_table.setRowCount(0); self.gate_progress.setValue(0); self.gate_stats.setText("Broker offline • no live position/order snapshot"); self.gate_status.setText("WAITING"); self.gate_reason.setText("Connect IBKR before any execution decision."); self.risk_gate.setText("GATE: WAITING")
    def on_scan(self,data):
        symbol=str(data.get("symbol"," ")).strip().upper(); signal=data.get("signal"); context=data.get("context") or {}; chart=data.get("chart") or {}
        if not symbol or signal is None:return
        self.scan_cache[symbol]=data; self._use_symbol_without_reentry(symbol); self.chart_symbol.setText(symbol); self.chart_price.setText(f"{float(signal.entry):.4f}"); self.chart_change.setText(str(signal.action)); self.chart.set_data(chart); self.chart_info.setText(f"Candles {len(chart.get('close') or [])}  •  Wheel zoom  •  Drag pan  •  EMA50")
        for k,v in self.ctx.items(): value=context.get(k); v.setText("—" if value is None else f"{float(value):.4f}")
        self.cloud_label.setText("Cloud: BELOW — bearish structure" if context.get("below_cloud") else "Cloud: ABOVE — bullish structure" if context.get("above_cloud") else "Cloud: NEUTRAL"); self.ai_fields["signal"].setText(str(signal.action)); self.ai_fields["score"].setText(str(signal.score)); self.ai_fields["entry"].setText(f"{signal.entry:.4f}"); self.ai_fields["stop"].setText(f"{signal.stop:.4f}" if signal.stop is not None else "—"); self.ai_fields["target"].setText(f"{signal.target:.4f}" if signal.target is not None else "—")
        if signal.stop and signal.target: risk=abs(signal.entry-signal.stop); reward=abs(signal.target-signal.entry); self.ai_fields["rr"].setText(f"1 : {reward/risk:.2f}" if risk else "—")
        else:self.ai_fields["rr"].setText("—")
        self.ai_fields["reasons"].setText(" • ".join(signal.reasons)); execution="BUY CANDIDATE — gate required" if signal.action=="BUY" else "SELL HELD — exit manager pending" if signal.action=="SELL" else "HOLD — no execution"; self.ai_fields["execution"].setText(execution); self.m_sig.value.setText(str(signal.action)); self.m_sig.sub.setText(f"{symbol} • score {signal.score}"); self._upsert_scan(self.scan_table,data); self._upsert_scan(self.market_table,data); self._add_ai_history(symbol,signal,execution)
    def _use_symbol_without_reentry(self,s):
        if self.symbol.currentText().upper()!=s:
            self.symbol.blockSignals(True)
            if self.symbol.findText(s)<0:self.symbol.addItem(s)
            self.symbol.setCurrentText(s); self.symbol.blockSignals(False)
    def _upsert_scan(self,table,data):
        symbol=str(data["symbol"]); signal=data["signal"]; status="BUY CANDIDATE" if signal.action=="BUY" else "SELL HELD" if signal.action=="SELL" else "HOLD"; row=next((r for r in range(table.rowCount()) if table.item(r,0) and table.item(r,0).text()==symbol),-1)
        if row<0:row=table.rowCount(); table.insertRow(row)
        vals=[symbol,str(signal.action),str(signal.score),f"{signal.entry:.4f}",f"{signal.stop:.4f}" if signal.stop else "—",f"{signal.target:.4f}" if signal.target else "—",f"{settings.take_profit_percent:.2f}%",status]
        for c,v in enumerate(vals):table.setItem(row,c,QTableWidgetItem(v))
    def _add_ai_history(self,symbol,signal,execution):
        self.ai_history.insertRow(0); vals=[datetime.now().strftime("%H:%M:%S"),symbol,str(signal.action),str(signal.score),f"{signal.entry:.4f}",f"{signal.stop:.4f}" if signal.stop else "—",f"{signal.target:.4f}" if signal.target else "—",execution]
        for c,v in enumerate(vals):self.ai_history.setItem(0,c,QTableWidgetItem(v))
        while self.ai_history.rowCount()>100:self.ai_history.removeRow(100)
    def on_order(self,r):
        vals=[r.time,r.symbol,r.action,str(r.quantity),f"{r.entry_limit:.4f}",f"{r.stop:.4f}" if r.stop else "—",f"{r.target:.4f}" if r.target else "—",r.status]; self.recent_orders.insertRow(0)
        for c,v in enumerate(vals):self.recent_orders.setItem(0,c,QTableWidgetItem(v))
        self.orders_full.insertRow(self.orders_full.rowCount());
        for c,v in enumerate(vals+[str(r.order_id)]):self.orders_full.setItem(self.orders_full.rowCount()-1,c,QTableWidgetItem(v))
    def _reload_watchlist(self):
        self.watch_list.clear(); path=Path(settings.watchlist_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines(): s=line.strip().upper();
            # intentionally handled below for compatibility with existing watchlist file
            for line in path.read_text(encoding="utf-8").splitlines():
                s=line.strip().upper()
                if s and not s.startswith("#"):self.watch_list.addItem(s)
    def _watch_add(self):
        s=self.watch_input.text().strip().upper()
        if s and not any(self.watch_list.item(i).text()==s for i in range(self.watch_list.count())):self.watch_list.addItem(s)
        self.watch_input.clear()
    def _watch_remove(self):
        if self.watch_list.currentRow()>=0:self.watch_list.takeItem(self.watch_list.currentRow())
    def _watch_save(self):
        vals=[self.watch_list.item(i).text().strip().upper() for i in range(self.watch_list.count())]; Path(settings.watchlist_file).write_text("\n".join(vals)+("\n" if vals else ""),encoding="utf-8"); self._log(f"Watchlist saved | {len(vals)} symbols")
    def _save_settings(self):
        values={"IB_HOST":self.s_host.text().strip(),"IB_PORT":str(self.s_port.value()),"IB_CLIENT_ID":str(self.s_client.value()),"FIXED_QUANTITY":str(self.s_qty.value()),"MAX_EXECUTED_ORDERS":str(self.s_max.value()),"MAX_ACTIVE_POSITIONS":str(self.s_pos.value()),"MAX_OPEN_ORDERS":str(self.s_open.value()),"EXECUTION_COUNT_SCOPE":self.s_scope.currentText(),"RISK_PER_TRADE":str(self.s_risk.value()/100),"REWARD_RISK":str(self.s_rr.value())}; path=Path(".env"); existing={}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):k,v=line.split("=",1); existing[k.strip()]=v.strip()
        existing.update(values); path.write_text("\n".join(f"{k}={v}" for k,v in existing.items())+"\n",encoding="utf-8"); settings.ib_host=values["IB_HOST"]; settings.ib_port=int(values["IB_PORT"]); settings.ib_client_id=int(values["IB_CLIENT_ID"]); settings.fixed_quantity=int(values["FIXED_QUANTITY"]); settings.max_executed_orders=int(values["MAX_EXECUTED_ORDERS"]); settings.max_active_positions=int(values["MAX_ACTIVE_POSITIONS"]); settings.max_open_orders=int(values["MAX_OPEN_ORDERS"]); settings.execution_count_scope=values["EXECUTION_COUNT_SCOPE"]; settings.risk_per_trade=float(values["RISK_PER_TRADE"]); settings.reward_risk=float(values["REWARD_RISK"]); self.limit_info.setText(self._limits_text()); self._log("Settings saved to .env"); QMessageBox.information(self,"Settings","Settings saved. Reconnect IBKR to apply connection changes.")
    def _log(self,text):
        if hasattr(self,"activity"): self.activity.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
    def closeEvent(self,event):
        if self.worker:self.worker.stop()
        if self.thread and self.thread.isRunning():self.thread.quit(); self.thread.wait(4000)
        if hasattr(self,"tv_timer"): self.tv_timer.stop()
        if self.tv_window is not None: self.tv_window.close()
        event.accept()

class QTextEditCompat(QFrame):
    def __init__(self):
        super().__init__(); self.setObjectName("Panel"); self._edit=__import__('PySide6.QtWidgets',fromlist=['QPlainTextEdit']).QPlainTextEdit(); self._edit.setReadOnly(True); l=QVBoxLayout(self); l.setContentsMargins(0,0,0,0); l.addWidget(self._edit)
    def appendPlainText(self,text): self._edit.appendPlainText(text)

def run():
    app=QApplication(sys.argv); app.setStyle("Fusion"); app.setStyleSheet(STYLE); w=MainWindow(); w.show(); return app.exec()
if __name__=="__main__": run()
