import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QItemSelectionModel
import sys
import os

# Ensure QApplication instance exists
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from logic.image_model import ImageItem, ImageTableModel
from gui.spreadsheet_panel import SpreadsheetPanel
from gui.main_window import MainWindow

class TestReplaceValue(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.spreadsheet = self.window.spreadsheet
        self.model = self.window.model

    def test_spreadsheet_controls_setup(self):
        # 1. Dropbox options and default
        self.assertTrue(hasattr(self.spreadsheet, "combo_replace_field"))
        self.assertEqual(self.spreadsheet.combo_replace_field.count(), 3)
        items = [self.spreadsheet.combo_replace_field.itemText(i) for i in range(3)]
        self.assertEqual(items, ["Comment", "Variant User", "Version User"])
        self.assertEqual(self.spreadsheet.combo_replace_field.currentText(), "Comment")

        # 2. Text box placeholder text matches current dropbox item
        self.assertEqual(self.spreadsheet.comment_field.placeholderText(), "Comment")
        self.spreadsheet.combo_replace_field.setCurrentText("Variant User")
        self.assertEqual(self.spreadsheet.comment_field.placeholderText(), "Variant User")
        self.spreadsheet.combo_replace_field.setCurrentText("Version User")
        self.assertEqual(self.spreadsheet.comment_field.placeholderText(), "Version User")
        self.spreadsheet.combo_replace_field.setCurrentText("Comment")

        # 3. Replace button text and disabled by default
        self.assertTrue(hasattr(self.spreadsheet, "btn_replace"))
        self.assertEqual(self.spreadsheet.btn_replace.text(), "Replace:")
        self.assertFalse(self.spreadsheet.btn_replace.isEnabled())

    def test_replace_button_enabled_on_selection(self):
        item1 = ImageItem("/path/to/test1.exr", label="test1", version=1)
        self.model.add_items([item1])

        # Initially no selection
        self.spreadsheet.table.selectionModel().clearSelection()
        self.assertFalse(self.spreadsheet.btn_replace.isEnabled())

        # Select row 0
        idx = self.model.index(0, 0)
        self.spreadsheet.table.selectionModel().select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.assertTrue(self.spreadsheet.btn_replace.isEnabled())

        # Clear selection
        self.spreadsheet.table.selectionModel().clearSelection()
        self.assertFalse(self.spreadsheet.btn_replace.isEnabled())

    def test_replace_values(self):
        item1 = ImageItem("/path/to/test1.exr", label="test1", version=1)
        item2 = ImageItem("/path/to/test2.exr", label="test2", version=1)
        self.model.add_items([item1, item2])

        # Select item1
        idx0 = self.model.index(0, 0)
        self.spreadsheet.table.selectionModel().select(idx0, QItemSelectionModel.Select | QItemSelectionModel.Rows)

        # Replace Comment
        self.spreadsheet.combo_replace_field.setCurrentText("Comment")
        self.spreadsheet.comment_field.setText("My test comment")
        self.spreadsheet.btn_replace.click()
        self.assertEqual(item1.comment, "My test comment")
        self.assertEqual(item2.comment, "")

        # Replace Variant User
        self.spreadsheet.combo_replace_field.setCurrentText("Variant User")
        self.spreadsheet.comment_field.setText("var_user_01")
        self.spreadsheet.btn_replace.click()
        self.assertEqual(item1.variant_user, "var_user_01")
        self.assertEqual(item2.variant_user, "")

        # Replace Version User
        self.spreadsheet.combo_replace_field.setCurrentText("Version User")
        self.spreadsheet.comment_field.setText("10")
        self.spreadsheet.btn_replace.click()
        self.assertEqual(item1.version_user, "10")
        self.assertEqual(item2.version_user, "")

    def test_replace_group_review_propagation_when_show_reviews_off(self):
        item_main = ImageItem("/path/to/seq_v001.exr", label="seq_v001", version=1)
        item_main.group_key = "seq_v001"
        item_main.is_review_repre = False

        item_review = ImageItem("/path/to/seq_v001_review.mp4", label="seq_v001_review", version=1)
        item_review.group_key = "seq_v001"
        item_review.is_review_repre = True

        self.model.add_items([item_main, item_review])

        # Select item_main (row 0)
        idx0 = self.model.index(0, 0)
        self.spreadsheet.table.selectionModel().select(idx0, QItemSelectionModel.Select | QItemSelectionModel.Rows)

        # Case A: show_reviews is OFF -> review item values updated too
        self.window.show_reviews = False

        self.spreadsheet.combo_replace_field.setCurrentText("Comment")
        self.spreadsheet.comment_field.setText("Hidden review comment")
        self.spreadsheet.btn_replace.click()

        self.assertEqual(item_main.comment, "Hidden review comment")
        self.assertEqual(item_review.comment, "Hidden review comment")

        # Test Variant User propagation
        self.spreadsheet.combo_replace_field.setCurrentText("Variant User")
        self.spreadsheet.comment_field.setText("group_variant")
        self.spreadsheet.btn_replace.click()

        self.assertEqual(item_main.variant_user, "group_variant")
        self.assertEqual(item_review.variant_user, "group_variant")

        # Case B: show_reviews is ON -> review item values NOT automatically updated unless selected
        self.window.show_reviews = True

        self.spreadsheet.combo_replace_field.setCurrentText("Comment")
        self.spreadsheet.comment_field.setText("Main only comment")
        self.spreadsheet.btn_replace.click()

        self.assertEqual(item_main.comment, "Main only comment")
        self.assertEqual(item_review.comment, "Hidden review comment")

if __name__ == "__main__":
    unittest.main()
