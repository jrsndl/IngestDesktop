import sys
import unittest
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for UI components
app = QApplication.instance() or QApplication(sys.argv)

from logic.image_model import ImageItem, ImageTableModel
from gui.main_window import MainWindow

class TestPublishLocalValidation(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.model = self.window.model
        
    def test_token_expansion_in_replacements(self):
        item = ImageItem(file_path="/tmp/shot_010_v001.exr", label="shot_010_v001")
        item.ayon_path = "/project/seq01/shot_010/render"
        item.variant = "main"
        item.version = 1
        
        replacements = self.model._get_replacements(item)
        self.assertEqual(replacements.get("{ayon_path}"), "/project/seq01/shot_010/render")
        self.assertEqual(replacements.get("{ayon_path_val}"), "/project/seq01/shot_010/render")
        self.assertEqual(replacements.get("{item.version}"), "1")
        self.assertEqual(replacements.get("{version}"), "1")

    def test_duplicate_check_and_groups(self):
        item1 = ImageItem(file_path="/tmp/shot_010_v001.exr", label="shot_010_v001")
        item1.ayon_path = "/project/seq01/shot_010/render"
        item1.variant = "main"
        item1.version = 1
        item1.is_tagged = True

        item2 = ImageItem(file_path="/tmp/shot_010_v001_dup.exr", label="shot_010_v001_dup")
        item2.ayon_path = "/project/seq01/shot_010/render"
        item2.variant = "main"
        item2.version = 1
        item2.is_tagged = True

        item3 = ImageItem(file_path="/tmp/shot_020_v001.exr", label="shot_020_v001")
        item3.ayon_path = "/project/seq01/shot_020/render"
        item3.variant = "main"
        item3.version = 1
        item3.is_tagged = True

        items = [item1, item2, item3]
        dup_set, dup_groups = self.window._check_duplicates_in_list(items)
        
        self.assertIn(item1, dup_set)
        self.assertIn(item2, dup_set)
        self.assertNotIn(item3, dup_set)
        self.assertEqual(len(dup_groups), 1)

    def test_validate_tagged_items_respects_checkboxes(self):
        item1 = ImageItem(file_path="/tmp/shot_010_v001.exr", label="shot_010_v001")
        item1.ayon_path = "/project/seq01/shot_010/render"
        item1.variant = "main"
        item1.version = 1
        item1.is_tagged = True

        item2 = ImageItem(file_path="/tmp/shot_010_v001_dup.exr", label="shot_010_v001_dup")
        item2.ayon_path = "/project/seq01/shot_010/render"
        item2.variant = "main"
        item2.version = 1
        item2.is_tagged = True

        tagged_items = [item1, item2]

        # 1. When Check Duplicates is True
        self.window.chk_check_duplicates.setChecked(True)
        self.window.chk_check_versions.setChecked(False)
        valid_items, dup_groups, collision_details = self.window._validate_tagged_items(tagged_items)
        self.assertEqual(len(valid_items), 0)
        self.assertEqual(len(dup_groups), 1)
        self.assertTrue(item1.is_duplicate)
        self.assertTrue(item2.is_duplicate)

        # 2. When Check Duplicates is False
        self.window.chk_check_duplicates.setChecked(False)
        self.window.chk_check_versions.setChecked(False)
        valid_items, dup_groups, collision_details = self.window._validate_tagged_items(tagged_items)
        self.assertEqual(len(valid_items), 2)
        self.assertEqual(len(dup_groups), 0)
        self.assertFalse(item1.is_duplicate)
        self.assertFalse(item2.is_duplicate)

if __name__ == "__main__":
    unittest.main()
