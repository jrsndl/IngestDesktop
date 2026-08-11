import sys
import unittest
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from logic.image_model import ImageTableModel
from gui.filter_panel import FilterPanel

class TestFilterPanelUnfold(unittest.TestCase):
    def setUp(self):
        self.model = ImageTableModel()
        self.filter_panel = FilterPanel(self.model)

    def test_unfold_button_existence_and_position(self):
        self.assertTrue(hasattr(self.filter_panel, "btn_unfold"))
        self.assertEqual(self.filter_panel.btn_unfold.text(), "Unfold")
        self.assertFalse(self.filter_panel.btn_unfold.isCheckable())

    def test_unfold_active_state_logic(self):
        # Default: Files ON, Flat OFF -> Unfold active
        self.assertTrue(self.filter_panel.btn_files_only.isChecked())
        self.assertFalse(self.filter_panel.btn_flat.isChecked())
        self.assertTrue(self.filter_panel.btn_unfold.isEnabled())

        # Turn OFF Files -> Unfold inactive
        self.filter_panel.btn_files_only.setChecked(False)
        self.assertFalse(self.filter_panel.btn_unfold.isEnabled())

        # Restore Files ON, turn ON Flat -> Unfold inactive
        self.filter_panel.btn_files_only.setChecked(True)
        self.filter_panel.btn_flat.setChecked(True)
        self.assertFalse(self.filter_panel.btn_unfold.isEnabled())

        # Flat OFF -> Unfold active again
        self.filter_panel.btn_flat.setChecked(False)
        self.assertTrue(self.filter_panel.btn_unfold.isEnabled())

    def test_unfold_click_expands_tree(self):
        # Verify clicking btn_unfold triggers expandAll without throwing errors
        self.filter_panel.btn_unfold.click()

if __name__ == "__main__":
    unittest.main()
