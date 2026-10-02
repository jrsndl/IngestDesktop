"""Items loaded from a project get frame range and file dates from the rescan."""
import sys
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from logic.image_model import ImageItem


class TestRescanRefreshesFileFacts(unittest.TestCase):
    def test_sequence_frame_range_and_dates(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            loaded = ImageItem(file_path="d:/p/shot_v047.1001.exr", label="shot", is_sequence=True)
            self.assertIsNone(loaded.frame_start)
            win.model.add_items([loaded])
            fresh = ImageItem(file_path="d:/p/shot_v047.1003.exr", label="shot", is_sequence=True,
                              frame_start=1001, frame_end=1100)
            fresh.modification_time = 1000.0
            fresh.age_minutes = 42
            win._refresh_file_facts([fresh])
            self.assertEqual((loaded.frame_start, loaded.frame_end), (1001, 1100))
            self.assertEqual(loaded.modification_time, 1000.0)
            self.assertEqual(loaded.age_minutes, 42)
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
