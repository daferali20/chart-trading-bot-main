from __future__ import annotations

import json
import urllib.error
import urllib.request

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import settings


class TradingViewConnectionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Trader — TradingView Connection")
        self.resize(620, 560)
        self._build()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1500)
        self.refresh_status()

    def _label(self, text="—"):
        x = QLabel(text)
        x.setWordWrap(True)
        return x

    def _build(self):
        self.setStyleSheet(
            "QWidget{background:#070d18;color:#e6edf7;font-family:'Segoe UI';font-size:10pt;}"
            "QFrame{background:#0d1727;border:1px solid #1c2b42;border-radius:10px;}"
            "QLineEdit,QComboBox{background:#091321;color:#e6edf7;border:1px solid #293a57;"
            "border-radius:6px;padding:7px;}"
            "QPushButton{background:#142238;color:#dbeafe;border:1px solid #293a57;"
            "border-radius:7px;padding:8px 12px;}"
            "QPushButton:hover{background:#1b2d49;}"
            "QPushButton#Primary{background:#2563eb;color:white;font-weight:800;}"
            "QLabel#Title{font-size:18pt;font-weight:900;color:#f8fafc;}"
            "QLabel#Good{color:#34d399;font-weight:900;}"
            "QLabel#Warn{color:#fbbf24;font-weight:900;}"
            "QLabel#Bad{color:#fb7185;font-weight:900;}"
            "QLabel#Muted{color:#8da0b8;}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._label("TRADINGVIEW CONNECTION",))
        self.title = self._label("TradingView",)
        self.title.setObjectName("Title")
        root.addWidget(self.title)
        root.addWidget(self._label("This window tests the webhook path before we embed it in the main dashboard."))

        source_frame = QFrame()
        source_layout = QFormLayout(source_frame)
        self.source = QComboBox()
        self.source.addItems(["TradingView", "IBKR"])
        self.source.currentTextChanged.connect(self._source_changed)
        source_layout.addRow("DATA SOURCE", self.source)
        root.addWidget(source_frame)

        status_frame = QFrame()
        form = QFormLayout(status_frame)
        self.server_status = self._label("CHECKING…")
        self.server_status.setObjectName("Warn")
        self.public_status = self._label("Not configured")
        self.last_signal = self._label("—")
        self.last_received = self._label("—")
        self.pending = self._label("0")
        self.processed = self._label("0")
        self.received = self._label("0")
        self.failed = self._label("0")
        form.addRow("WEBHOOK SERVER", self.server_status)
        form.addRow("LOCAL URL", self._label(f"http://{settings.tradingview_webhook_host}:{settings.tradingview_webhook_port}"))
        form.addRow("PUBLIC HTTPS", self.public_status)
        form.addRow("LAST SIGNAL", self.last_signal)
        form.addRow("LAST RECEIVED", self.last_received)
        form.addRow("PENDING", self.pending)
        form.addRow("PROCESSED", self.processed)
        form.addRow("RECEIVED", self.received)
        form.addRow("FAILED", self.failed)
        root.addWidget(status_frame)

        url_frame = QFrame()
        url_layout = QFormLayout(url_frame)
        self.public_url = QLineEdit()
        self.public_url.setPlaceholderText("https://your-domain.example/webhook/tradingview")
        url_layout.addRow("TRADINGVIEW WEBHOOK URL", self.public_url)
        root.addWidget(url_frame)

        buttons = QHBoxLayout()
        test = QPushButton("TEST WEBHOOK")
        test.setObjectName("Primary")
        test.clicked.connect(self.test_webhook)
        copy_btn = QPushButton("COPY URL")
        copy_btn.clicked.connect(lambda: self._copy_url())
        open_tv = QPushButton("OPEN TRADINGVIEW")
        open_tv.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.tradingview.com/chart/")))
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(self.refresh_status)
        buttons.addWidget(test)
        buttons.addWidget(copy_btn)
        buttons.addWidget(open_tv)
        buttons.addWidget(refresh)
        root.addLayout(buttons)

        self.info = self._label("Waiting for webhook server…")
        self.info.setObjectName("Muted")
        root.addWidget(self.info)
        root.addStretch(1)

    def _source_changed(self, source: str):
        if source == "TradingView":
            self.info.setText("TradingView mode: waiting for alerts/webhooks.")
        else:
            self.info.setText("IBKR mode: market data comes from the broker connection.")

    def _copy_url(self):
        url = self.public_url.text().strip()
        if not url:
            QMessageBox.information(self, "TradingView", "Enter the public HTTPS webhook URL first.")
            return
        self.public_url.selectAll()
        self.public_url.copy()
        self.info.setText("Webhook URL copied to clipboard.")

    def _request(self, path: str, method="GET", body=None):
        url = f"http://{settings.tradingview_webhook_host}:{settings.tradingview_webhook_port}{path}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if settings.tradingview_webhook_token:
                headers["X-Webhook-Token"] = settings.tradingview_webhook_token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=2.5) as response:
            return json.loads(response.read().decode("utf-8"))

    def refresh_status(self):
        try:
            data = self._request("/status")
            self.server_status.setText("ONLINE / READY")
            self.server_status.setObjectName("Good")
            self.public_status.setText(self.public_url.text().strip() or "NOT CONFIGURED")
            self.last_signal.setText(
                "—" if not data.get("last_symbol") else f"{data.get('last_symbol')} / {data.get('last_action')}"
            )
            self.last_received.setText(str(data.get("last_received_at") or "—"))
            self.pending.setText(str(data.get("pending", 0)))
            self.processed.setText(str(data.get("processed", 0)))
            self.received.setText(str(data.get("received", 0)))
            self.failed.setText(str(data.get("failed", 0)))
            self.info.setText("Webhook server is reachable. Send a test signal or trigger a TradingView alert.")
        except Exception as exc:
            self.server_status.setText("OFFLINE / NOT REACHABLE")
            self.server_status.setObjectName("Bad")
            self.info.setText(f"Cannot reach local webhook: {exc}")

    def test_webhook(self):
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "price": 100.0,
            "stop": 98.0,
            "target": 104.0,
            "score": 5,
            "message": "LOCAL TEST | TradingView connection test",
        }
        try:
            result = self._request("/webhook/tradingview", method="POST", body=payload)
            self.info.setText(f"TEST ACCEPTED — signal #{result.get('signal_id')} queued.")
            self.refresh_status()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.info.setText(f"TEST FAILED — HTTP {exc.code}: {detail}")
        except Exception as exc:
            self.info.setText(f"TEST FAILED — {exc}")
