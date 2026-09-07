from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config import settings
from desktop import dashboard as legacy


STYLE = legacy.STYLE + r"""
QMainWindow,QWidget { background:#06101c; color:#e8f0fb; font-family:'Segoe UI'; }
QFrame#Side { background:#071321; border-right:1px solid #17314d; }
QFrame#Top,QFrame#Panel,QFrame#Metric { background:#0a1a2b; border:1px solid #1b3b5a; border-radius:12px; }
QFrame#Metric:hover,QFrame#Panel:hover { border-color:#2b5f89; }
QFrame#DecisionBox { background:#0b2032; border:1px solid #285474; border-radius:10px; }
QLabel#Brand { font-size:22pt; letter-spacing:1px; }
QLabel#Title { font-size:15pt; }
QLabel#Hero { color:#f7fbff; font-size:27pt; font-weight:950; }
QLabel#PillGood { color:#bafbdc; background:#0b3427; border:1px solid #1f8f68; border-radius:10px; padding:5px 10px; font-weight:900; }
QLabel#PillBlue { color:#cce6ff; background:#102b49; border:1px solid #2b6fa8; border-radius:10px; padding:5px 10px; font-weight:900; }
QPushButton#AutoOff { background:#3a1720; color:#ffbec9; border:1px solid #99394e; font-weight:900; }
QPushButton#AutoOn { background:#083627; color:#b9fbd9; border:1px solid #168b64; font-weight:900; }
QPushButton#Start { background:#063a2c; color:#b7ffda; border:1px solid #15996c; font-weight:900; }
QPushButton#Nav:checked { background:#0c3356; color:#fff; border-left:3px solid #1aa7ff; }
QTableWidget { background:#071522; alternate-background-color:#0a1b2a; gridline-color:#17334d; }
QHeaderView::section { background:#0b1d2d; color:#8eabc6; border-bottom:1px solid #21415d; }
QProgressBar::chunk { background:#21d994; }
"""


def _tone(widget: QLabel, name: str) -> None:
    widget.setObjectName(name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _panel(title: str, subtitle: str = ""):
    frame, layout = legacy.panel(title)
    if subtitle:
        header = QHBoxLayout()
        header.addStretch(1)
        header.addWidget(legacy.lab(subtitle, "Muted"))
        layout.insertLayout(1, header)
    return frame, layout


class MainWindow(legacy.MainWindow):
    """Premium dashboard layered on top of the proven desktop behavior.

    The original dashboard is still constructed off-screen so legacy scanner,
    broker, order and risk handlers keep every attribute they already use.
    This class only upgrades presentation and mirrors live state into the new
    intelligence cockpit.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Trader — IBKR Paper • Intelligence Cockpit")
        self.resize(1536, 960)
        self.setMinimumSize(1240, 780)
        self._sync_execution_ui()

    def _sidebar(self):
        side = legacy.MainWindow._sidebar(self)
        side.setFixedWidth(180)
        self.side_tv.setText("TRADINGVIEW  OPTIONAL")
        self.side_tv.setObjectName("Muted")
        return side

    def _topbar(self):
        top = legacy.MainWindow._topbar(self)
        layout = top.layout()
        if hasattr(self, "data_source") and isinstance(self.data_source, QComboBox):
            self.data_source.setCurrentText("IBKR")
            self.data_source.setToolTip("IBKR is the primary live market/broker source. TradingView is optional.")
        if hasattr(self, "start_btn"):
            self.start_btn.setObjectName("Start")
        layout.addSpacing(4)
        self.paper_pill = QLabel("PAPER MODE"); self.paper_pill.setObjectName("PillGood")
        self.shadow_pill = QLabel("SHADOW READY"); self.shadow_pill.setObjectName("PillBlue")
        self.auto_exec_btn = QPushButton(); self.auto_exec_btn.clicked.connect(self.toggle_auto_execution)
        layout.addWidget(self.paper_pill); layout.addWidget(self.shadow_pill); layout.addWidget(self.auto_exec_btn)
        return top

    def _metrics(self):
        wrapper = QWidget(); grid = QGridLayout(wrapper)
        grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(7); grid.setVerticalSpacing(7)
        self.m_ibkr = legacy.Metric("IBKR STATUS","DISCONNECTED","No broker snapshot")
        self.m_regime = legacy.Metric("MARKET REGIME","WAITING","Needs market context")
        self.m_sig = legacy.Metric("FINAL SIGNAL","—","No analysis yet")
        self.m_conf = legacy.Metric("CONFIDENCE","—","Signal quality")
        self.m_news = legacy.Metric("NEWS IMPACT","OPTIONAL","SerpAPI intelligence")
        self.m_gate = legacy.Metric("EXECUTION GATE","WAITING","Fail-closed")
        self.m_exposure = legacy.Metric("PORTFOLIO EXPOSURE","—","Waiting for broker")
        self.m_opportunity = legacy.Metric("LATEST OPPORTUNITY","—","Scanner waiting")
        for i, card in enumerate([self.m_ibkr,self.m_regime,self.m_sig,self.m_conf,self.m_news,self.m_gate,self.m_exposure,self.m_opportunity]):
            grid.addWidget(card,0,i)
        self.m_pos = legacy.Metric("POSITIONS")
        self.m_open = legacy.Metric("OPEN ORDERS")
        self.m_exec = legacy.Metric("EXECUTED",f"0 / {settings.max_executed_orders}")
        return wrapper

    def _dashboard_page(self):
        self._legacy_dashboard = legacy.MainWindow._dashboard_page(self)
        page = QWidget(); root = QVBoxLayout(page); root.setContentsMargins(0,0,0,0); root.setSpacing(8)

        top = QGridLayout(); top.setHorizontalSpacing(8); top.setVerticalSpacing(8)
        top.addWidget(self._decision_card(),0,0,1,5)
        top.addWidget(self._strategy_card(),0,5,1,4)
        top.addWidget(self._news_card(),0,9,1,3)
        root.addLayout(top,3)

        middle = QGridLayout(); middle.setHorizontalSpacing(8)
        middle.addWidget(self._portfolio_risk_card(),0,0,1,4)
        middle.addWidget(self._shadow_card(),0,4,1,5)
        middle.addWidget(self._quick_card(),0,9,1,3)
        root.addLayout(middle,2)

        opportunities, ol = _panel("OPPORTUNITIES & WATCHLIST","scanner ranking")
        self.opportunity_table = self._table(["#","Symbol","Signal","Regime","Score","Confidence","News","Risk","Status","Last Update"])
        self.opportunity_table.setMinimumHeight(220); ol.addWidget(self.opportunity_table)
        root.addWidget(opportunities,2)
        return page

    def _decision_card(self):
        frame, layout = _panel("FINAL DECISION","signal engine")
        head = QHBoxLayout(); self.v2_symbol = legacy.lab("—","Title"); self.v2_meta = legacy.lab("Waiting for scanner","Muted")
        head.addWidget(self.v2_symbol); head.addWidget(self.v2_meta); head.addStretch(1); layout.addLayout(head)
        row = QHBoxLayout(); box = QFrame(); box.setObjectName("DecisionBox"); bl = QVBoxLayout(box)
        self.v2_action = QLabel("WAIT"); self.v2_action.setObjectName("Hero"); self.v2_bias = legacy.lab("NO ACTIVE SIGNAL","Muted")
        bl.addWidget(self.v2_action); bl.addWidget(self.v2_bias); row.addWidget(box,2)
        metrics = QGridLayout(); self.v2_score=legacy.Metric("SCORE","—","Fusion score"); self.v2_conf=legacy.Metric("CONFIDENCE","—","Model agreement"); self.v2_move=legacy.Metric("EXPECTED MOVE","—","Target-derived")
        metrics.addWidget(self.v2_score,0,0); metrics.addWidget(self.v2_conf,0,1); metrics.addWidget(self.v2_move,0,2)
        holder=QWidget(); holder.setLayout(metrics); row.addWidget(holder,5); layout.addLayout(row)
        foot=QHBoxLayout(); self.v2_horizon=legacy.lab("Horizon: —","Muted"); self.v2_reason=legacy.lab("Waiting for a completed analysis cycle.","Muted"); self.v2_reason.setWordWrap(True)
        foot.addWidget(self.v2_horizon,1); foot.addWidget(self.v2_reason,4); layout.addLayout(foot)
        return frame

    def _strategy_card(self):
        frame, layout = _panel("STRATEGY VOTES","multi-alpha fusion")
        self.v2_strategy = self._table(["Strategy","Signal","Confidence","Weight","Contribution"])
        for name in ["Williams","Breakout","Momentum","Trend","Volume","News","Adaptive"]:
            r=self.v2_strategy.rowCount(); self.v2_strategy.insertRow(r)
            for c,v in enumerate([name,"—","—","—","—"]): self.v2_strategy.setItem(r,c,QTableWidgetItem(v))
        self.v2_strategy.setMinimumHeight(245); layout.addWidget(self.v2_strategy); return frame

    def _news_card(self):
        frame, layout = _panel("NEWS INTELLIGENCE","SerpAPI optional")
        self.v2_headline=legacy.lab("No event loaded","StatusValue"); self.v2_headline.setWordWrap(True); layout.addWidget(self.v2_headline)
        self.v2_event=legacy.lab("EVENT: —","Blue"); layout.addWidget(self.v2_event)
        grid=QGridLayout(); self.v2_impact=legacy.Metric("IMPACT","—","event strength"); self.v2_up=legacy.Metric("BULLISH","—","probability"); self.v2_neutral=legacy.Metric("NEUTRAL","—","probability"); self.v2_down=legacy.Metric("BEARISH","—","probability")
        grid.addWidget(self.v2_impact,0,0,1,3); grid.addWidget(self.v2_up,1,0); grid.addWidget(self.v2_neutral,1,1); grid.addWidget(self.v2_down,1,2); layout.addLayout(grid)
        layout.addWidget(legacy.lab("News is an additional factor, never the sole execution trigger.","Muted")); return frame

    def _portfolio_risk_card(self):
        frame,layout=_panel("RISK & PORTFOLIO","fail-closed controls")
        grid=QGridLayout(); self.v2_positions=legacy.Metric("POSITIONS","—",f"Max {settings.max_active_positions}"); self.v2_open=legacy.Metric("OPEN ORDERS","—",f"Max {settings.max_open_orders}"); self.v2_exec=legacy.Metric("EXECUTED","—",f"Max {settings.max_executed_orders}"); self.v2_account=legacy.Metric("NET LIQUIDATION","—","IBKR")
        for i,m in enumerate([self.v2_positions,self.v2_open,self.v2_exec,self.v2_account]): grid.addWidget(m,0,i)
        layout.addLayout(grid); self.v2_risk_status=legacy.lab("CORRELATION / SECTOR / DRAWDOWN: waiting for portfolio context","Muted"); layout.addWidget(self.v2_risk_status); return frame

    def _shadow_card(self):
        frame,layout=_panel("SHADOW / CALIBRATION","research comparison")
        self.v2_shadow=self._table(["Model","Signal","Score","Agreement"])
        for name in ["Legacy (v1)","Signal v2","Adaptive","News-aware","Calibrated"]:
            r=self.v2_shadow.rowCount(); self.v2_shadow.insertRow(r)
            for c,v in enumerate([name,"WAIT","—","—"]): self.v2_shadow.setItem(r,c,QTableWidgetItem(v))
        self.v2_shadow.setMinimumHeight(150); layout.addWidget(self.v2_shadow); self.v2_calibration=legacy.lab("Calibration: waiting for mature samples","Muted"); layout.addWidget(self.v2_calibration); return frame

    def _quick_card(self):
        frame,layout=_panel("QUICK SETTINGS","live controls")
        self.v2_quick=self._table(["Setting","Value"]); self.v2_quick.horizontalHeader().setVisible(False)
        for key,value in [("Order Quantity",settings.fixed_quantity),("Max Positions",settings.max_active_positions),("Max Open Orders",settings.max_open_orders),("Scope",settings.execution_count_scope),("Risk / Trade",f"{settings.risk_per_trade*100:.2f}%"),("Reward / Risk",settings.reward_risk),("News Shadow","ON" if settings.news_shadow_enabled else "OFF"),("Auto Execution","ON" if getattr(settings,"auto_execution_enabled",False) else "OFF")]:
            r=self.v2_quick.rowCount(); self.v2_quick.insertRow(r); self.v2_quick.setItem(r,0,QTableWidgetItem(str(key))); self.v2_quick.setItem(r,1,QTableWidgetItem(str(value)))
        self.v2_quick.setMinimumHeight(185); layout.addWidget(self.v2_quick); return frame

    def toggle_auto_execution(self):
        settings.auto_execution_enabled = not bool(getattr(settings,"auto_execution_enabled",False))
        self._sync_execution_ui(); self._log("AUTO EXECUTION " + ("ON — PAPER submissions allowed after gates" if settings.auto_execution_enabled else "OFF — analysis only"))

    def _sync_execution_ui(self):
        if not hasattr(self,"auto_exec_btn"): return
        enabled=bool(getattr(settings,"auto_execution_enabled",False)); self.auto_exec_btn.setText("AUTO EXECUTION ON" if enabled else "AUTO EXECUTION OFF"); self.auto_exec_btn.setObjectName("AutoOn" if enabled else "AutoOff"); self.auto_exec_btn.style().unpolish(self.auto_exec_btn); self.auto_exec_btn.style().polish(self.auto_exec_btn)
        if hasattr(self,"v2_quick"):
            for r in range(self.v2_quick.rowCount()):
                if self.v2_quick.item(r,0) and self.v2_quick.item(r,0).text()=="Auto Execution": self.v2_quick.setItem(r,1,QTableWidgetItem("ON" if enabled else "OFF"))

    def refresh_tradingview_status(self):
        super().refresh_tradingview_status()
        if self.side_tv.text().endswith("OFFLINE"):
            self.side_tv.setText("TRADINGVIEW  OPTIONAL")
            self.side_tv.setObjectName("Muted")
            self.side_tv.style().unpolish(self.side_tv); self.side_tv.style().polish(self.side_tv)

    def on_status(self,text):
        super().on_status(text)
        if "AUTO EXECUTION OFF" in text.upper() or "KEPT INSIDE BOT" in text.upper():
            self.m_gate.value.setText("ANALYSIS ONLY"); self.m_gate.sub.setText("No IBKR submission")

    def on_snapshot(self,data):
        super().on_snapshot(data)
        pos=(data or {}).get("positions") or []; opens=(data or {}).get("open_orders") or []; exe=int((data or {}).get("executed") or 0); mx=int((data or {}).get("maximum") or settings.max_executed_orders); account=(data or {}).get("account_value")
        self.v2_positions.value.setText(f"{len(pos)} / {settings.max_active_positions}"); self.v2_open.value.setText(f"{len(opens)} / {settings.max_open_orders}"); self.v2_exec.value.setText(f"{exe} / {mx}"); self.v2_account.value.setText("—" if account is None else f"${float(account):,.2f}")
        self.m_exposure.value.setText(f"{len(pos)} positions"); self.m_exposure.sub.setText(f"Max {settings.max_active_positions}")
        if not getattr(settings,"auto_execution_enabled",False) and not self.emergency_active:
            self.m_gate.value.setText("ANALYSIS ONLY"); self.m_gate.sub.setText("Auto Execution OFF")

    def on_scan(self,data):
        super().on_scan(data)
        signal=data.get("signal"); symbol=str(data.get("symbol") or "").upper(); ctx=data.get("context") or {}
        action=str(getattr(signal,"action","HOLD") or "HOLD").upper(); score=getattr(signal,"score",None); entry=getattr(signal,"entry",None); target=getattr(signal,"target",None); reasons=list(getattr(signal,"reasons",[]) or [])
        confidence=getattr(signal,"confidence",None) or ctx.get("confidence"); regime=str(ctx.get("market_regime") or ctx.get("regime") or "—").upper(); news=ctx.get("news_impact") or ctx.get("event_impact")
        self.v2_symbol.setText(symbol); self.v2_meta.setText(f"{settings.timeframe} • completed analysis"); self.v2_action.setText(action); _tone(self.v2_action,"Good" if action=="BUY" else "Bad" if action=="SELL" else "Warn"); self.v2_bias.setText("BULLISH BIAS" if action=="BUY" else "BEARISH BIAS" if action=="SELL" else "NEUTRAL / WAIT")
        self.v2_score.value.setText("—" if score is None else str(score)); self.m_regime.value.setText(regime); self.m_regime.sub.setText("Market context" if regime!="—" else "Not supplied by live worker yet")
        conf_text="—"
        if confidence is not None:
            try: conf_text=f"{(float(confidence)*100 if float(confidence)<=1 else float(confidence)):.0f}%"
            except Exception: conf_text=str(confidence)
        self.v2_conf.value.setText(conf_text); self.m_conf.value.setText(conf_text); self.m_conf.sub.setText("Signal quality")
        expected=None
        try:
            if entry not in (None,0) and target is not None: expected=(float(target)-float(entry))/float(entry)*100
        except Exception: pass
        self.v2_move.value.setText("—" if expected is None else f"{expected:+.2f}%"); self.v2_horizon.setText("Horizon: "+str(ctx.get("horizon") or settings.timeframe)); self.v2_reason.setText(" • ".join(map(str,reasons)) if reasons else "No reason summary was supplied by this cycle.")
        self.m_news.value.setText(str(news or "OPTIONAL")); self.m_news.sub.setText("SerpAPI / event context")
        if action=="BUY": self.m_opportunity.value.setText(symbol); self.m_opportunity.sub.setText(f"Score {score if score is not None else '—'} • BUY")
        self._sync_strategy_votes(ctx); self._sync_news(ctx); self._sync_shadow(ctx); self._sync_opportunity(symbol,action,regime,score,conf_text,news)

    def _sync_strategy_votes(self,ctx):
        votes=ctx.get("alpha_votes") or ctx.get("strategy_votes") or {}
        for r,name in enumerate(["Williams","Breakout","Momentum","Trend","Volume","News","Adaptive"]):
            payload=(votes.get(name) or votes.get(name.lower())) if isinstance(votes,dict) else None; values=[name,"—","—","—","—"]
            if isinstance(payload,dict):
                values[1]=str(payload.get("signal") or payload.get("direction") or "—").upper(); c=payload.get("confidence"); w=payload.get("weight"); values[4]=str(payload.get("contribution","—"))
                if c is not None:
                    try: values[2]=f"{(float(c)*100 if float(c)<=1 else float(c)):.0f}%"
                    except Exception: values[2]=str(c)
                if w is not None: values[3]=str(w)
            for c,v in enumerate(values): self.v2_strategy.setItem(r,c,QTableWidgetItem(v))

    def _sync_news(self,ctx):
        if ctx.get("news_headline") or ctx.get("headline"): self.v2_headline.setText(str(ctx.get("news_headline") or ctx.get("headline")))
        if ctx.get("event_type") or ctx.get("news_event"): self.v2_event.setText("EVENT: "+str(ctx.get("event_type") or ctx.get("news_event")).upper())
        if ctx.get("impact_score") is not None: self.v2_impact.value.setText(str(ctx.get("impact_score")))
        for key,metric in [("up_probability",self.v2_up),("neutral_probability",self.v2_neutral),("down_probability",self.v2_down)]:
            val=ctx.get(key)
            if val is not None:
                try: metric.value.setText(f"{(float(val)*100 if float(val)<=1 else float(val)):.0f}%")
                except Exception: metric.value.setText(str(val))

    def _sync_shadow(self,ctx):
        data=ctx.get("shadow") or ctx.get("shadow_comparison")
        if not isinstance(data,dict): return
        for r,key in enumerate(["legacy","v2","adaptive","news_aware","calibrated"]):
            item=data.get(key)
            if not isinstance(item,dict): continue
            for c,v in enumerate([self.v2_shadow.item(r,0).text(),item.get("signal","—"),item.get("score","—"),item.get("agreement","—")]): self.v2_shadow.setItem(r,c,QTableWidgetItem(str(v)))
        if ctx.get("calibration_status"): self.v2_calibration.setText("Calibration: "+str(ctx.get("calibration_status")))

    def _sync_opportunity(self,symbol,action,regime,score,conf,news):
        row=-1
        for i in range(self.opportunity_table.rowCount()):
            if self.opportunity_table.item(i,1) and self.opportunity_table.item(i,1).text()==symbol: row=i; break
        if row<0: row=self.opportunity_table.rowCount(); self.opportunity_table.insertRow(row)
        vals=[row+1,symbol,action,regime,score if score is not None else "—",conf,news or "—","CHECK GATE" if action!="HOLD" else "LOW","CANDIDATE" if action!="HOLD" else "WATCH",datetime.now().strftime("%H:%M:%S")]
        for c,v in enumerate(vals): self.opportunity_table.setItem(row,c,QTableWidgetItem(str(v)))
