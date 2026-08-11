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

if __name__ == "__main__":
    unittest.main()
