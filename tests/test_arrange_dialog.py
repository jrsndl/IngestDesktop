import unittest
from PySide6.QtWidgets import QApplication
from gui.thumbnail_area import ArrangeDialog

app = QApplication.instance() or QApplication([])

class TestArrangeDialog(unittest.TestCase):
    def test_horizontal_gap_max_range(self):
        dialog = ArrangeDialog(mode="grid", initial_values={"gap_h": 50})
        self.assertIsNotNone(dialog.slider_gap_h)
        self.assertEqual(dialog.slider_gap_h.maximum(), 10000)

        dialog_h = ArrangeDialog(mode="horizontal", initial_values={"gap_h": 50})
        self.assertIsNotNone(dialog_h.slider_gap_h)
        self.assertEqual(dialog_h.slider_gap_h.maximum(), 10000)

    def test_thumb_size_slider(self):
        dialog = ArrangeDialog(mode="grid", initial_values={"thumb_size": 250})
        self.assertIsNotNone(dialog.slider_thumb_size)
        self.assertEqual(dialog.slider_thumb_size.value(), 250)
        self.assertEqual(dialog.slider_thumb_size.minimum(), 20)
        self.assertEqual(dialog.slider_thumb_size.maximum(), 2048)
        self.assertEqual(dialog.get_values()["thumb_size"], 250)

if __name__ == "__main__":
    unittest.main()
