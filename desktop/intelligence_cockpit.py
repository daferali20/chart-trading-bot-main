from __future__ import annotations

from .dashboard_v2 import MainWindow as PremiumDashboard, STYLE


class MainWindow(PremiumDashboard):
    """Final premium cockpit with stable integration-state handling."""

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
