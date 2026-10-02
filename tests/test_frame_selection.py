"""File panel selection: with Sequences off, a frame selects only its own item."""
import sys
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from logic.image_model import ImageItem


class TestFrameSelection(unittest.TestCase):
    def test_single_frames_select_only_themselves(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            frames = [ImageItem(file_path=f"d:/seq/shot.{1001 + i}.exr", label="shot") for i in range(3)]
            win.model.add_items(frames)
            win._sync_selection_from_filter(selected_paths=[frames[1].file_path])
            sel = [d for d, t in win.thumb_area.item_to_thumb.items() if t.isSelected()]
            self.assertEqual(sel, [frames[1]])
        finally:
            win.close()

    def test_frame_selects_its_sequence_item(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            seq = ImageItem(file_path="d:/seq2/shot.1001.exr", label="shot", is_sequence=True)
            win.model.add_items([seq])
            win._sync_selection_from_filter(selected_paths=["d:/seq2/shot.1002.exr"])
            self.assertTrue(win.thumb_area.item_to_thumb[seq].isSelected())
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
