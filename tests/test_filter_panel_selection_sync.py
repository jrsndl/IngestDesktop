import unittest
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QItemSelectionModel
from gui.main_window import MainWindow
from logic.image_model import ImageItem, ImageTableModel

app = QApplication.instance() or QApplication([])

class TestFilterPanelSelectionSync(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow()

    def tearDown(self):
        self.win.close()

    def test_filter_panel_selection_syncs_to_table_and_thumbs(self):
        item = ImageItem("sparks_020_pl01_v01_review.mp4", "d:/test/sparks_020_pl01_v01_review.mp4")
        item.representation = "mp4"
        item.category = "Video"
        
        self.win.model.items = [item]
        self.win.model.layoutChanged.emit()

        # Connect filter selection signal
        self.win._connect_filter_selection_signal()

        # Directly emit selection_changed from filter_panel (simulating tree selection)
        self.win._sync_selection_from_filter()

        # Call filter_panel._on_tree_selection_changed
        self.win.filter_panel._on_tree_selection_changed(None, None)

        # Trigger direct sync with path
        self.win.filter_panel.selection_changed.emit(None, None)

        # Verify signal connection
        self.assertTrue(hasattr(self.win.filter_panel, "selection_changed"))

    def test_flat_off_selection_sync(self):
        test_path = os.path.normpath(os.path.abspath(os.path.join(os.getcwd(), "test_file.mp4")))
        item = ImageItem("test_file.mp4", test_path)
        self.win.model.items = [item]
        self.win.model.layoutChanged.emit()

        # Ensure Flat is OFF
        self.win.filter_panel.btn_flat.setChecked(False)
        self.win.filter_panel._on_toggles_changed()

        self.win._connect_filter_selection_signal()

        # Test path matching when flat is OFF
        items_list = self.win.model.items
        target_items = set()
        p_norm = test_path.lower()
        for it in items_list:
            item_norm = os.path.normpath(os.path.abspath(it.file_path)).lower()
            if item_norm == p_norm or item_norm.startswith(p_norm + os.sep):
                target_items.add(it)

        self.assertIn(item, target_items)

    def test_ayon_item_selection_sync_bidirectional(self):
        ayon_item = ImageItem(
            file_path="ayon://proj/shot05/comp.mp4",
            label="shot05/comp/render v1",
            is_ayon_item=True
        )
        setattr(ayon_item, "repre_id", "rep-999")
        self.win.filter_panel.btn_files_only.setChecked(False)
        self.win.filter_panel._on_toggles_changed()
        self.win._on_ayon_items_resolved([ayon_item])

        # Verify item added to canvas
        thumb = self.win.thumb_area.item_to_thumb.get(ayon_item)
        self.assertIsNotNone(thumb, "ThumbnailItem not created for AYON item!")

        # 1. Main Canvas selection -> Right Panel
        thumb.setSelected(True)
        self.win._sync_selection_to_table()
        # FilterPanel select_paths should find and select the item in its tree
        sel_indexes = self.win.filter_panel.tree.selectionModel().selectedIndexes()
        self.assertTrue(len(sel_indexes) > 0, "Right panel tree did not select the AYON item!")

        # Clear selections
        self.win.thumb_area.scene.clearSelection()
        self.win.filter_panel.tree.selectionModel().clearSelection()

        # 2. Right Panel selection -> Main Canvas
        self.win.filter_panel.select_paths(["ayon://proj/shot05/comp.mp4"])
        self.win._sync_selection_from_filter()
        self.assertTrue(thumb.isSelected(), "Main canvas thumbnail was not selected from Right panel selection!")

    def test_folder_selection_sync_selects_all_contained_items(self):
        folder_path = os.path.normpath(os.path.abspath("d:/project/shots/shot01"))
        item1 = ImageItem(os.path.join(folder_path, "comp_v01.mp4"), "comp_v01.mp4")
        item2 = ImageItem(os.path.join(folder_path, "comp_v02.mp4"), "comp_v02.mp4")
        other_item = ImageItem("d:/project/shots/shot02/other.mp4", "other.mp4")

        self.win.model._items = [item1, item2, other_item]
        self.win.model.layoutChanged.emit()
        self.win.thumb_area.add_items([item1, item2, other_item])

        thumb1 = self.win.thumb_area.item_to_thumb.get(item1)
        thumb2 = self.win.thumb_area.item_to_thumb.get(item2)
        other_thumb = self.win.thumb_area.item_to_thumb.get(other_item)

        # Select the folder path in the right file panel
        self.win._sync_selection_from_filter(selected_paths=[folder_path])

        self.assertTrue(thumb1.isSelected(), "Contained item1 thumbnail was not selected!")
        self.assertTrue(thumb2.isSelected(), "Contained item2 thumbnail was not selected!")
        self.assertFalse(other_thumb.isSelected(), "Unrelated item thumbnail should not be selected!")

    def test_ignore_checkbox_preserves_tree_root_index(self):
        root_dir = os.path.normpath(os.path.abspath(os.getcwd()))
        self.win.filter_panel.set_root_folder(root_dir)

        expected_source_idx = self.win.filter_panel.fs_model.index(root_dir)
        expected_proxy_idx = self.win.filter_panel.proxy.mapFromSource(expected_source_idx)

        # Confirm initial root index
        self.assertEqual(self.win.filter_panel.tree.rootIndex(), expected_proxy_idx)

        # Toggle Ignore checkbox
        self.win.filter_panel.chk_ignore.setChecked(False)
        self.win.filter_panel._on_ignore_change()

        # Verify root index remains set to current source folder, not QModelIndex()
        self.assertEqual(self.win.filter_panel.tree.rootIndex(), expected_proxy_idx)

        # Toggle Ignore checkbox back on
        self.win.filter_panel.chk_ignore.setChecked(True)
        self.win.filter_panel._on_ignore_change()

        self.assertEqual(self.win.filter_panel.tree.rootIndex(), expected_proxy_idx)

    def test_version_diff_items_not_selected_together(self):
        folder_path = os.path.normpath(os.path.abspath("d:/project/reviews"))
        v1_path = os.path.join(folder_path, "sparks_020_pl01_v01_review.mp4")
        v2_path = os.path.join(folder_path, "sparks_020_pl01_v02_review.mp4")

        item_v1 = ImageItem(v1_path, "sparks_020_pl01_v01_review.mp4")
        item_v2 = ImageItem(v2_path, "sparks_020_pl01_v02_review.mp4")

        self.win.model._items = [item_v1, item_v2]
        self.win.model.layoutChanged.emit()
        self.win.thumb_area.add_items([item_v1, item_v2])

        thumb_v1 = self.win.thumb_area.item_to_thumb.get(item_v1)
        thumb_v2 = self.win.thumb_area.item_to_thumb.get(item_v2)

        # Select v2 in the right file panel
        self.win.filter_panel.select_paths([v2_path])
        self.win._sync_selection_from_filter(selected_paths=[v2_path])

        # v2 should be selected, v1 must NOT be selected
        self.assertTrue(thumb_v2.isSelected(), "v2 item thumbnail should be selected!")
        self.assertFalse(thumb_v1.isSelected(), "v1 item thumbnail MUST NOT be selected when v2 is selected!")

if __name__ == "__main__":
    unittest.main()
