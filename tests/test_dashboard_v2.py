import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config import settings
from desktop.intelligence_cockpit import MainWindow


class PremiumDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_premium_dashboard_builds_with_fail_safe_execution_off(self):
        original = settings.auto_execution_enabled
        settings.auto_execution_enabled = False
        try:
            window = MainWindow()
            self.assertEqual(window.auto_exec_btn.text(), "AUTO EXECUTION OFF")
            self.assertEqual(window.m_news.value.text(), "OPTIONAL")
            self.assertEqual(window.m_gate.value.text(), "WAITING")
            self.assertEqual(window.v2_strategy.rowCount(), 7)
            self.assertEqual(window.opportunity_table.columnCount(), 10)
            self.assertIn("OPTIONAL", window.side_tv.text())
            self.assertEqual(window.selected_data_source, "IBKR")
            window.close()
        finally:
            settings.auto_execution_enabled = original


if __name__ == "__main__":
    unittest.main()
