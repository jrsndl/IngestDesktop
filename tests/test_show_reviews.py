import unittest
import sys
import os
from PySide6.QtWidgets import QApplication

if not QApplication.instance():
    app = QApplication(sys.argv)

from gui.top_bar import TopBar
from gui.thumbnail_area import ThumbnailArea
from logic.image_model import ImageItem, ImageTableModel

class TestShowReviews(unittest.TestCase):
    def test_top_bar_show_reviews_button(self):
        top_bar = TopBar()
        self.assertTrue(hasattr(top_bar, "btn_show_reviews"))
        self.assertEqual(top_bar.btn_show_reviews.text(), "Show Reviews")
        self.assertTrue(top_bar.btn_show_reviews.isCheckable())
        self.assertTrue(top_bar.btn_show_reviews.isChecked())
        
        # Verify signal emission
        toggled_states = []
        top_bar.show_reviews_toggled.connect(lambda state: toggled_states.append(state))
        
        top_bar.btn_show_reviews.setChecked(False)
        self.assertEqual(toggled_states, [False])
        
        top_bar.btn_show_reviews.setChecked(True)
        self.assertEqual(toggled_states, [False, True])

    def test_thumbnail_area_find_media_path_works_when_show_reviews_disabled(self):
        import tempfile
        model = ImageTableModel()
        thumb_area = ThumbnailArea()
        thumb_area.setModel(model)
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            item = ImageItem(file_path="C:/test/sample_v001.exr", category="Sequence")
            item.review_file_path = tmp_path
            
            # When show_reviews is False, find_media_path still returns the review video path for playback
            thumb_area.set_show_reviews(False)
            self.assertFalse(thumb_area.show_reviews)
            media_path = thumb_area.find_media_path(item)
            self.assertEqual(media_path, tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_review_repre_hiding_when_show_reviews_disabled(self):
        from gui.spreadsheet_panel import SpreadsheetPanel
        from gui.main_window import MainWindow

        win = MainWindow()
        item_exr = ImageItem(file_path="C:/test/asset_v001.exr", representation="exr")
        item_mp4 = ImageItem(file_path="C:/test/asset_v001.mp4", representation="mp4")
        item_mp4.is_review_repre = True

        win.model.add_items([item_exr, item_mp4])

        # When show_reviews is True
        win._on_show_reviews_toggled(True)
        self.assertFalse(win.spreadsheet.table.isRowHidden(0))
        self.assertFalse(win.spreadsheet.table.isRowHidden(1))

        # When show_reviews is False
        win._on_show_reviews_toggled(False)
        self.assertFalse(win.spreadsheet.table.isRowHidden(0))
        self.assertTrue(win.spreadsheet.table.isRowHidden(1))

        win.close()

    def test_show_grouped_in_csv_view(self):
        from gui.main_window import MainWindow
        from PySide6.QtCore import QModelIndex, Qt
        from PySide6.QtGui import QColor

        win = MainWindow()
        win.config["group_definitions"] = []
        item1 = ImageItem(file_path="C:/test/assetA_v001.exr", representation="exr", variant="vA")
        item2 = ImageItem(file_path="C:/test/assetB_v001.exr", representation="exr", variant="vB")
        win.model.add_items([item1, item2])

        # Enable CSV Mode
        win.spreadsheet._on_csv_toggled(True)

        # Toggle Show Grouped ON
        win._on_show_grouped_toggled(True)
        self.assertTrue(win.model.show_grouped)

        # Check background role in CSVPreviewModel
        bg_col_row0 = win.csv_preview_model.data(win.csv_preview_model.index(0, 2), Qt.BackgroundRole)
        bg_col_row1 = win.csv_preview_model.data(win.csv_preview_model.index(1, 2), Qt.BackgroundRole)
        self.assertIsInstance(bg_col_row0, QColor)
        self.assertIsInstance(bg_col_row1, QColor)
        self.assertNotEqual(bg_col_row0.name(), bg_col_row1.name())

        # Toggle Show Grouped OFF
        win._on_show_grouped_toggled(False)
        self.assertFalse(win.model.show_grouped)
        bg_off = win.csv_preview_model.data(win.csv_preview_model.index(0, 2), Qt.BackgroundRole)
        self.assertIsNone(bg_off)

        win.close()

    def test_csv_mode_only_shows_existing_review_files(self):
        from gui.main_window import MainWindow
        from logic.image_model import ImageItem
        import os, tempfile

        win = MainWindow()
        item = ImageItem(file_path="C:/test/assetA_v001.exr", representation="exr")
        item.review_status = "done"
        win.model.add_items([item])

        # CSVPreviewModel should ONLY show existing tagged files (no synthetic review rows)
        win.csv_preview_model._refresh_data()
        self.assertEqual(win.csv_preview_model.rowCount(), 1)
        self.assertFalse(win.csv_preview_model.is_review_row[0])

        # Even if review file exists on disk for processable media, CSV mode shows only tagged items (1 row)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_rev:
            tmp_rev_path = tmp_rev.name
        try:
            item.review_file_path = tmp_rev_path
            win.csv_preview_model.refresh_config(win.config)
            self.assertEqual(win.csv_preview_model.rowCount(), 1)
            self.assertFalse(win.csv_preview_model.is_review_row[0])
        finally:
            if os.path.exists(tmp_rev_path):
                os.remove(tmp_rev_path)

        win.close()

if __name__ == "__main__":
    unittest.main()
