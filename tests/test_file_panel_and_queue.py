import unittest
from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem
from gui.main_window import MainWindow
from gui.conversion_queue_dialog import ConversionQueueDialog

app = QApplication.instance() or QApplication([])

class TestFilePanelAndQueue(unittest.TestCase):
    def test_filter_panel_tree_expansion_preservation(self):
        win = MainWindow()
        # Set ignore filter text
        win.filter_panel.ignore_bar.setText("test_ignore_string")
        # Ensure method works without throwing errors and retains state
        expanded = win.filter_panel.get_tree_expansion_state()
        self.assertIsInstance(expanded, set)
        win.close()

    def test_conversion_queue_selection_and_selected_only(self):
        win = MainWindow()
        item1 = ImageItem(file_path="C:/test/file1.exr", representation="exr")
        item1.review_status = "waiting"
        item2 = ImageItem(file_path="C:/test/file2.exr", representation="exr")
        item2.review_status = "waiting"
        win.model.add_items([item1, item2])

        # Pre-select item1 in conversion queue
        dialog = ConversionQueueDialog(win.model, win)
        dialog.set_selected_items([item1])

        # By default "Selected Only" is OFF, so both items with review_status != "do not convert" are shown
        self.assertFalse(dialog.chk_selected_only.isChecked())
        self.assertEqual(dialog.proxy.rowCount(), 2)

        # Toggle "Selected Only" ON
        dialog.chk_selected_only.setChecked(True)
        self.assertEqual(dialog.proxy.rowCount(), 1)
        
        # Verify row 0 in proxy corresponds to item1
        source_row0 = dialog.proxy.mapToSource(dialog.proxy.index(0, 0)).row()
        self.assertEqual(win.model.items[source_row0], item1)

        win.close()

if __name__ == "__main__":
    unittest.main()
