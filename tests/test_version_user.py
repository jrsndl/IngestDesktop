import unittest
import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

# Ensure app instance exists
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from logic.image_model import ImageItem, ImageTableModel

class TestVersionUser(unittest.TestCase):
    def setUp(self):
        self.model = ImageTableModel()
        self.item1 = ImageItem("/path/to/render_v001.exr", label="render_v001", version=1, category="Still")
        self.item2 = ImageItem("/path/to/render_v002.exr", label="render_v002", version=2, category="Still", version_user="5")
        self.model.items = [self.item1, self.item2]

    def test_effective_version(self):
        # item1 has no version_user, effective_version should be version (1)
        self.assertEqual(self.item1.effective_version, 1)
        
        # item2 has version_user="5", effective_version should be 5
        self.assertEqual(self.item2.effective_version, 5)

        # token {version} expansion should yield effective version
        repl1 = self.model._get_replacements(self.item1)
        self.assertEqual(repl1["{version}"], "1")
        
        repl2 = self.model._get_replacements(self.item2)
        self.assertEqual(repl2["{version}"], "5")
        self.assertEqual(repl2["{version_user}"], "5")

    def test_model_columns_and_editing(self):
        # Check column headers
        headers = [self.model.headerData(i, Qt.Horizontal) for i in range(self.model.columnCount())]
        self.assertIn("Version", headers)
        self.assertIn("Version User", headers)
        self.assertIn("Last Version", headers)
        
        version_idx = headers.index("Version")
        version_user_idx = headers.index("Version User")
        last_version_idx = headers.index("Last Version")
        
        self.assertEqual(version_idx, 8)
        self.assertEqual(version_user_idx, 9)
        self.assertEqual(last_version_idx, 10)

        # Test data access
        idx_v_user = self.model.index(0, version_user_idx)
        self.assertEqual(self.model.data(idx_v_user), "")
        
        idx_v_user2 = self.model.index(1, version_user_idx)
        self.assertEqual(self.model.data(idx_v_user2), "5")

        # Edit version_user on item1
        res = self.model.setData(idx_v_user, "10", Qt.EditRole)
        self.assertTrue(res)
        self.assertEqual(self.item1.version_user, "10")
        self.assertEqual(self.item1.effective_version, 10)
        self.assertEqual(self.item1.version, 1) # original version unchanged!

    def test_version_collision_highlighting(self):
        # Set last_ayon_version to 5 for item1 (version=1, version_user="") -> collision!
        self.item1.last_ayon_version = 5
        self.item1.version_collision = True

        idx_ver = self.model.index(0, 8) # Version column
        idx_ver_user = self.model.index(0, 9) # Version User column
        idx_last = self.model.index(0, 10) # Last Version column

        # Foreground role should be red (#f44336) for Version cell
        fg_ver = self.model.data(idx_ver, Qt.ForegroundRole)
        fg_last = self.model.data(idx_last, Qt.ForegroundRole)

        self.assertEqual(fg_ver, QColor("#f44336"))
        self.assertEqual(fg_last, QColor("#ff8c00"))

        # When Version User fix is applied ("6"), Version User (6 > 5) is NOT red,
        # BUT base Version (1 <= 5) STAYS RED!
        self.item1.version_user = "6"
        fg_ver_fixed = self.model.data(idx_ver, Qt.ForegroundRole)
        fg_ver_user_fixed = self.model.data(idx_ver_user, Qt.ForegroundRole)
        self.assertEqual(fg_ver_fixed, QColor("#f44336"))
        self.assertIsNone(fg_ver_user_fixed)

if __name__ == "__main__":
    unittest.main()
