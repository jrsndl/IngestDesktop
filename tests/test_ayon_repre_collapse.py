import sys
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

from gui.ayon_panel import AyonPanel

class TestAyonRepreCollapse(unittest.TestCase):
    def setUp(self):
        self.panel = AyonPanel()

    def test_collapse_checkbox_defaults(self):
        self.assertTrue(hasattr(self.panel, "chk_collapse_repre"))
        self.assertEqual(self.panel.chk_collapse_repre.text(), "collapse")
        self.assertTrue(self.panel.chk_collapse_repre.isChecked())

    def test_representation_collapsing(self):
        sample_repres = [
            {"name": "png", "context": {"version": 1}, "attrib": {"path": "/path/to/v001.png"}},
            {"name": "png", "context": {"version": 3}, "attrib": {"path": "/path/to/v003.png"}},
            {"name": "png", "context": {"version": 2}, "attrib": {"path": "/path/to/v002.png"}},
            {"name": "exr", "context": {"version": 1}, "attrib": {"path": "/path/to/v001.exr"}},
            {"name": "exr", "context": {"version": 2}, "attrib": {"path": "/path/to/v002.exr"}},
            {"name": "mov", "context": {"version": 5}, "attrib": {"path": "/path/to/v005.mov"}},
        ]

        self.panel.set_representations(sample_repres)

        # Default: collapse is ON -> only 3 rows (mov v005, png v003, exr v002)
        model = self.panel.repre_model
        self.assertEqual(model.rowCount(), 3)

        displayed = []
        for r in range(model.rowCount()):
            name = model.item(r, 0).text()
            ver = model.item(r, 1).text()
            path = model.item(r, 2).text()
            displayed.append((name, ver, path))

        expected_collapsed = [
            ("mov", "v005", "/path/to/v005.mov"),
            ("png", "v003", "/path/to/v003.png"),
            ("exr", "v002", "/path/to/v002.exr"),
        ]
        self.assertEqual(displayed, expected_collapsed)

        # Toggle collapse OFF -> shows all 6 rows
        self.panel.chk_collapse_repre.setChecked(False)
        self.assertEqual(model.rowCount(), 6)

        # Toggle collapse back ON -> shows 3 rows again
        self.panel.chk_collapse_repre.setChecked(True)
        self.assertEqual(model.rowCount(), 3)

    @patch.object(AyonPanel, "_on_repre_open")
    def test_double_click_triggers_open(self, mock_open):
        sample_repres = [
            {"name": "png", "context": {"version": 1}, "attrib": {"path": "/path/to/v001.png"}},
        ]
        self.panel.set_representations(sample_repres)

        idx = self.panel.repre_model.index(0, 0)
        self.panel._on_repre_double_click(idx)

        mock_open.assert_called_once_with(["/path/to/v001.png"])

if __name__ == "__main__":
    unittest.main()
