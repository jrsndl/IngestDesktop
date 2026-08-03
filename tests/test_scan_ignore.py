import os
import tempfile
import unittest
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(list())

from logic.scanner import ImageScanner
from gui.filter_panel import TagColorProxyModel
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

class TestScanIgnore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.tmp_dir.name

        # Create test file structure:
        # dir_path/fileA_v01.png
        # dir_path/temp_folder/fileB_v01.png
        # dir_path/fileC_cache_v01.png
        os.makedirs(os.path.join(self.dir_path, "temp_folder"), exist_ok=True)

        self.file_a = os.path.join(self.dir_path, "fileA_v01.png")
        self.file_b = os.path.join(self.dir_path, "temp_folder", "fileB_v01.png")
        self.file_c = os.path.join(self.dir_path, "fileC_cache_v01.png")

        for f in [self.file_a, self.file_b, self.file_c]:
            with open(f, "wb") as fp:
                fp.write(b"dummy data")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_scanner_ignores_matching_paths(self):
        scanner = ImageScanner(
            self.dir_path,
            recursive=True,
            ignore_enabled=True,
            ignore_text="temp_folder cache"
        )
        
        found_items = []
        scanner.finished.connect(lambda items: found_items.extend(items))
        scanner.run()

        found_paths = [os.path.normpath(item.file_path) for item in found_items]
        self.assertIn(os.path.normpath(self.file_a), found_paths)
        self.assertNotIn(os.path.normpath(self.file_b), found_paths)
        self.assertNotIn(os.path.normpath(self.file_c), found_paths)

    def test_scanner_includes_all_when_ignore_disabled(self):
        scanner = ImageScanner(
            self.dir_path,
            recursive=True,
            ignore_enabled=False,
            ignore_text="temp_folder cache"
        )

        found_items = []
        scanner.finished.connect(lambda items: found_items.extend(items))
        scanner.run()

        found_paths = [os.path.normpath(item.file_path) for item in found_items]
        self.assertIn(os.path.normpath(self.file_a), found_paths)
        self.assertIn(os.path.normpath(self.file_b), found_paths)
        self.assertIn(os.path.normpath(self.file_c), found_paths)

    def test_proxy_model_ignore_filter(self):
        class MockSignal:
            def connect(self, slot): pass

        class MockItem:
            def __init__(self, path):
                self.file_path = path
                self.filename = os.path.basename(path)
                self.is_tagged = False
                self.review_status = "none"
                self.age_minutes = 0
                self.label = os.path.basename(path)
                self.is_sequence = False

        class MockMainModel:
            def __init__(self, items):
                self.items = items
                self.version_stacks = {}
                self.dataChanged = MockSignal()
                self.modelReset = MockSignal()
                self.rowsInserted = MockSignal()
                self.rowsRemoved = MockSignal()
                self.layoutChanged = MockSignal()

            def is_item_visible_by_v_stack(self, item, val):
                return True

            def get_version_stack_key(self, item):
                return None

        fs_model = QStandardItemModel()
        item_a = QStandardItem("fileA")
        item_a.setData(self.file_a, Qt.UserRole)
        item_b = QStandardItem("fileB")
        item_b.setData(self.file_b, Qt.UserRole)

        fs_model.appendRow(item_a)
        fs_model.appendRow(item_b)

        mock_main = MockMainModel([MockItem(self.file_a), MockItem(self.file_b)])
        proxy = TagColorProxyModel(mock_main)
        proxy.setSourceModel(fs_model)

        proxy.set_ignore_filter("temp_folder", ignore_enabled=True)
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual(proxy.data(proxy.index(0, 0)), "fileA")

        proxy.set_ignore_filter("temp_folder", ignore_enabled=False)
        self.assertEqual(proxy.rowCount(), 2)

if __name__ == "__main__":
    unittest.main()
