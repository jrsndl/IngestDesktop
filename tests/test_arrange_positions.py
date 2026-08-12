import unittest
import sys
from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem, ImageTableModel
from gui.main_window import MainWindow
from gui.thumbnail_area import ThumbnailItem

app = QApplication.instance() or QApplication(sys.argv)

class TestArrangePositions(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.thumb_area = self.window.thumb_area
        self.model = self.window.model

    def tearDown(self):
        self.window.close()

    def test_arrange_stores_positions_for_all_items(self):
        items = [
            ImageItem(file_path=f"d:/test/file_{i}.jpg", label=f"File {i}")
            for i in range(10)
        ]
        self.model.add_items(items)

        # Execute arrange on grid mode
        self.thumb_area._on_arrange("grid")
        dialog = self.thumb_area._arrange_dialog
        self.assertIsNotNone(dialog)

        # Accept dialog
        dialog.accept()

        # Check every item has has_placed_position True and stored in item_positions
        for item_data in items:
            thumb = self.thumb_area.item_to_thumb.get(item_data)
            self.assertIsNotNone(thumb)
            self.assertTrue(item_data.has_placed_position)
            key = self.thumb_area._get_item_key(item_data)
            self.assertIn(key, self.thumb_area.item_positions)
            self.assertEqual(self.thumb_area.item_positions[key], (thumb.pos().x(), thumb.pos().y()))

    def test_arrange_revert_restores_item_positions_dict(self):
        items = [
            ImageItem(file_path=f"d:/test/file_{i}.jpg", label=f"File {i}")
            for i in range(5)
        ]
        self.model.add_items(items)

        # Set custom positions
        for i, item_data in enumerate(items):
            thumb = self.thumb_area.item_to_thumb.get(item_data)
            thumb.setPos(i * 300, 100)
            item_data.position = (i * 300, 100)
            item_data.has_placed_position = True
            key = self.thumb_area._get_item_key(item_data)
            self.thumb_area.item_positions[key] = (i * 300, 100)

        pos_before = {item_data: self.thumb_area.item_positions[self.thumb_area._get_item_key(item_data)] for item_data in items}

        self.thumb_area._on_arrange("grid")
        dialog = self.thumb_area._arrange_dialog
        self.assertIsNotNone(dialog)

        # Reject dialog (revert)
        dialog.reject()

        # Check item_positions dict matches pos_before
        for item_data in items:
            key = self.thumb_area._get_item_key(item_data)
            pos_after = self.thumb_area.item_positions[key]
            self.assertEqual(pos_before[item_data], pos_after, f"Revert did not restore item_positions for {key}")

if __name__ == "__main__":
    unittest.main()
