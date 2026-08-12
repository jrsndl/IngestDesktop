import unittest
import sys
from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem, ImageTableModel
from gui.thumbnail_area import ThumbnailArea

class TestItemPlacementMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_marked_placement_and_line_addition(self):
        model = ImageTableModel()
        thumb_area = ThumbnailArea()
        thumb_area.setModel(model)

        # 1. Set marked placement position (e.g. at (100, 200))
        thumb_area._marked_placement_pos = QPointF(100.0, 200.0)

        item1 = ImageItem(file_path="/path/test1.png", label="test1")
        item2 = ImageItem(file_path="/path/test2.png", label="test2")

        model.add_items([item1, item2])
        thumb_area.add_items()

        thumb1 = thumb_area.item_to_thumb[item1]
        thumb2 = thumb_area.item_to_thumb[item2]

        # Verify item1 placed at marked position (100, 200)
        self.assertEqual(thumb1.pos().x(), 100.0)
        self.assertEqual(thumb1.pos().y(), 200.0)

        # Verify item2 placed to the right of item1 on the same line
        self.assertGreater(thumb2.pos().x(), 100.0)
        self.assertEqual(thumb2.pos().y(), 200.0)

    def test_overlap_avoidance_vertical_shift(self):
        model = ImageTableModel()
        thumb_area = ThumbnailArea()
        thumb_area.setModel(model)

        item1 = ImageItem(file_path="/path/test1.png", label="test1")
        item1.position = (100.0, 100.0)
        item1.has_placed_position = True

        model.add_items([item1])
        thumb_area.add_items()

        # Now mark click position exactly over item1 at (100, 100)
        thumb_area._marked_placement_pos = QPointF(100.0, 100.0)

        item2 = ImageItem(file_path="/path/test2.png", label="test2")
        model.add_items([item2])
        thumb_area.add_items()

        thumb1 = thumb_area.item_to_thumb[item1]
        thumb2 = thumb_area.item_to_thumb[item2]

        # item1 stays at (100, 100)
        self.assertEqual(thumb1.pos().x(), 100.0)
        self.assertEqual(thumb1.pos().y(), 100.0)

        # item2 collides at (100, 100) so its Y coordinate shifts down by item height
        self.assertEqual(thumb2.pos().x(), 100.0)
        self.assertGreater(thumb2.pos().y(), 100.0)

    def test_position_memory_across_filter_toggles(self):
        model = ImageTableModel()
        thumb_area = ThumbnailArea()
        thumb_area.setModel(model)

        item1 = ImageItem(file_path="/path/test1.png", label="test1")
        model.add_items([item1])
        thumb_area.add_items()

        thumb1 = thumb_area.item_to_thumb[item1]

        # User moves item manually to custom coordinates (350, 450)
        thumb1.setPos(350.0, 450.0)
        item1.position = (350.0, 450.0)
        item1.has_placed_position = True
        thumb_area.item_positions[item1.file_path] = (350.0, 450.0)

        # Filter out item1 by search term
        thumb_area.rearrange_items(search_text="nonexistent")
        self.assertFalse(thumb1.isVisible())

        # Restore filter
        thumb_area.rearrange_items(search_text="")
        self.assertTrue(thumb1.isVisible())

        # Item1 must be restored to its exact stored position (350, 450)
        self.assertEqual(thumb1.pos().x(), 350.0)
        self.assertEqual(thumb1.pos().y(), 450.0)

if __name__ == "__main__":
    unittest.main()
