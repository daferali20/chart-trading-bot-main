from __future__ import annotations

from PySide6.QtCore import QThread

from app.config import settings
from app.ui_worker2 import IndependentScannerWorker
from .dashboard import MainWindow as DashboardWindow


class MainWindow(DashboardWindow):
    """Desktop controller with a persistent IBKR connection and independent scanner controls."""

    def connect_ibkr(self):
        if self.thread and self.thread.isRunning():
            return
        settings.ib_host = self.s_host.text().strip()
        settings.ib_port = int(self.s_port.value())
        settings.ib_client_id = int(self.s_client.value())
        self.emergency_active = False
        self.thread = QThread(self)
        self.worker = IndependentScannerWorker(int(self.interval.currentText()))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.on_status)
        self.worker.scan.connect(self.on_scan)
        self.worker.order.connect(self.on_order)
        self.worker.snapshot.connect(self.on_snapshot)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()
        self.connect_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.footer_status.setText("Connecting to IBKR…")
        self._log("IBKR connection requested")

    def start_scanner(self):
        if not self.worker or not self.thread or not self.thread.isRunning() or not self.broker_live:
            self._log("Connect IBKR first.")
            return
        settings.fixed_quantity = self.quantity.value()
        settings.take_profit_percent = self.tp.value()
        settings.scan_interval_seconds = int(self.interval.currentText())
        self.worker.interval = max(5, settings.scan_interval_seconds)
        self.worker.start_scanning()
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self._log("Scanner STARTED")

    def pause_scanner(self):
        if self.worker:
            self.worker.pause_scanning()
        self.start_btn.setEnabled(self.broker_live and not self.emergency_active)
        self.pause_btn.setEnabled(False)
        self._log("Scanner PAUSED")

    def disconnect_ibkr(self):
        if self.worker:
            self.worker.stop()
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self._log("IBKR DISCONNECT requested")

    def emergency_stop(self):
        self.emergency_active = True
        if self.worker:
            self.worker.pause_scanning()
            self.worker.stop()
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.gate_status.setText("EMERGENCY STOP")
        self.gate_reason.setText("All new execution is stopped. Reconnect manually to resume.")
        self.risk_gate.setText("GATE: EMERGENCY STOP")
        self._log("EMERGENCY STOP | new execution disabled")


def run():
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DashboardWindow.__module__ and __import__("desktop.dashboard", fromlist=["STYLE"]).STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
