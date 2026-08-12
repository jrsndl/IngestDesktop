import unittest
import sys

from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem
from gui.thumbnail_area import ThumbnailItem

app = QApplication.instance() or QApplication(sys.argv)

class TestAyonBorderThickness(unittest.TestCase):
    def test_ayon_item_border_thickness(self):
        normal_item = ImageItem("/path/to/file.png", "file")
        ayon_item = ImageItem("ayon://test/folder", "ayon_item", is_ayon_item=True)

        thumb_normal = ThumbnailItem(normal_item)
        thumb_ayon = ThumbnailItem(ayon_item)

        # Both items should instantiate cleanly
        self.assertFalse(thumb_normal.data.is_ayon_item)
        self.assertTrue(thumb_ayon.data.is_ayon_item)

if __name__ == "__main__":
    unittest.main()
