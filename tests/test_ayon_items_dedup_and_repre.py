import unittest
import os
import sys
from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem, ImageTableModel
from gui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

class TestAyonItemsDedupAndRepre(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.model = self.window.model

    def tearDown(self):
        self.window.close()

    def test_ayon_item_deduplication(self):
        item1 = ImageItem(
            file_path="ayon://proj/shot01/comp.mp4",
            label="shot01/comp/render v1",
            is_ayon_item=True
        )
        setattr(item1, "repre_id", "rep-12345")

        item2 = ImageItem(
            file_path="ayon://proj/shot01/comp.mp4",
            label="shot01/comp/render v1",
            is_ayon_item=True
        )
        setattr(item2, "repre_id", "rep-12345")

        self.window._on_ayon_items_resolved([item1])
        all_count_1 = len(getattr(self.model, "all_items", self.model.items))
        self.assertEqual(all_count_1, 1)

        # Attempt to add duplicate item
        self.window._on_ayon_items_resolved([item2])
        all_count_2 = len(getattr(self.model, "all_items", self.model.items))
        self.assertEqual(all_count_2, 1, "Duplicate AYON item was improperly added!")

    def test_filter_panel_ayon_items_visibility(self):
        item = ImageItem(
            file_path="ayon://proj/shot02/comp.mp4",
            label="shot02/comp/render v1",
            is_ayon_item=True
        )
        self.window._on_ayon_items_resolved([item])

        # Turn files toggle OFF (btn_files_only is False)
        self.window.filter_panel.btn_files_only.setChecked(False)
        self.window.filter_panel._enable_flat_view()

        # Verify flat model contains the AYON item
        flat_model = self.window.filter_panel.flat_model
        found = False
        for r in range(flat_model.rowCount()):
            lbl = flat_model.item(r, 0).text()
            if "shot02/comp/render v1" in lbl:
                found = True
                break
        self.assertTrue(found, "AYON item was not found in FilterPanel when Files toggle was off!")

    def test_delete_ayon_item_removes_from_model_and_panels(self):
        item = ImageItem(
            file_path="ayon://proj/shot03/comp.mp4",
            label="shot03/comp/render v1",
            is_ayon_item=True
        )
        self.window._on_ayon_items_resolved([item])

        all_items_before = len(getattr(self.model, "all_items", self.model.items))
        self.assertEqual(all_items_before, 1)

        # Trigger remove_items
        self.model.remove_items([item])

        all_items_after = len(getattr(self.model, "all_items", self.model.items))
        self.assertEqual(all_items_after, 0, "AYON Item was not removed from model!")

    def test_delete_ayon_item_preserves_remaining_item_positions(self):
        item1 = ImageItem(file_path="ayon://proj/shot01/comp.mp4", label="shot01/comp/render v1", is_ayon_item=True)
        setattr(item1, "repre_id", "rep-111")

        item2 = ImageItem(file_path="ayon://proj/shot02/comp.mp4", label="shot02/comp/render v1", is_ayon_item=True)
        setattr(item2, "repre_id", "rep-222")

        self.window._on_ayon_items_resolved([item1, item2])
        thumb_area = self.window.thumb_area

        thumb1 = thumb_area.item_to_thumb.get(item1)
        thumb2 = thumb_area.item_to_thumb.get(item2)

        self.assertIsNotNone(thumb1)
        self.assertIsNotNone(thumb2)

        # Set custom canvas position for remaining item
        thumb2.setPos(500.0, 300.0)
        pos2_before = thumb2.pos()

        # Delete item1
        self.model.remove_items([item1])

        # Verify item1 thumb is removed from scene
        self.assertNotIn(item1, thumb_area.item_to_thumb)
        self.assertNotIn(thumb1, thumb_area.scene.items())

        # Verify thumb2 position remains UNCHANGED (not rearranged)
        pos2_after = thumb2.pos()
        self.assertEqual(pos2_before, pos2_after, "Remaining thumbnail position was improperly rearranged on deletion!")

if __name__ == "__main__":
    unittest.main()

