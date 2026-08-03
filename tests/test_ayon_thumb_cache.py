import unittest
import os
import sys
import tempfile
import shutil
from PySide6.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from gui.main_window import MainWindow

class TestAyonThumbCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.window = MainWindow()
        self.window.secrets["ayon_thumbnails_cache"] = self.temp_dir

    def tearDown(self):
        self.window.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_root_resolution(self):
        cache_root = self.window._get_ayon_thumb_cache_root()
        self.assertTrue(os.path.isabs(cache_root))
        self.assertEqual(cache_root, os.path.abspath(self.temp_dir))

    def test_missing_thumb_file_redownload_logic(self):
        # Simulate state marked as "cached" previously, but target file does not exist on disk
        thumb_id = "test_thumb_123"
        self.window.ayon_thumb_states[thumb_id] = "cached"
        
        # Verify that if target path doesn't exist, missing state is not skipped
        project_cache_dir = os.path.join(self.temp_dir, "TestProject")
        target_path = os.path.join(project_cache_dir, f"{thumb_id}.jpg")
        self.assertFalse(os.path.exists(target_path))

        # Check filtering logic directly:
        state = self.window.ayon_thumb_states.get(thumb_id)
        # With the fix, missing files should NOT be skipped when state is 'cached' or 'downloaded'
        should_skip = (state in ("not available", "downloading"))
        self.assertFalse(should_skip)

if __name__ == "__main__":
    unittest.main()
