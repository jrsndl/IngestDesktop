import unittest
from PySide6.QtWidgets import QApplication
import sys

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

from gui.prefs_dialog import PreferencesDialog

class TestAyonItemsPrefs(unittest.TestCase):
    def test_ayon_items_prefs_defaults_and_saving(self):
        config = {
            "ayon_item_task_type_priority": "Compositing Editing",
            "ayon_item_task_name_priority": "comp",
            "ayon_item_product_type_priority": "review render plate",
            "ayon_item_product_name_priority": "main",
            "ayon_item_product_version": "Max Version",
            "ayon_item_product_version_status": "",
            "ayon_item_repre_priority_extension": "mp4 mov png",
            "ayon_item_label": "{folder_name}/{task_name}/{product_name} v{version}"
        }
        secrets = {}
        dlg = PreferencesDialog(config, secrets)
        
        self.assertEqual(dlg.ayon_item_task_type_priority.text(), "Compositing Editing")
        self.assertEqual(dlg.ayon_item_task_name_priority.text(), "comp")
        self.assertEqual(dlg.ayon_item_product_type_priority.text(), "review render plate")
        self.assertEqual(dlg.ayon_item_product_name_priority.text(), "main")
        self.assertEqual(dlg.ayon_item_product_version.currentText(), "Max Version")
        self.assertEqual(dlg.ayon_item_repre_priority_extension.text(), "mp4 mov png")

        # Change values
        dlg.ayon_item_task_type_priority.setText("Animation Lighting")
        dlg.ayon_item_product_version.setCurrentText("by Status or Max")

        new_config, _ = dlg.get_settings()
        self.assertEqual(new_config["ayon_item_task_type_priority"], "Animation Lighting")
        self.assertEqual(new_config["ayon_item_product_version"], "by Status or Max")

if __name__ == "__main__":
    unittest.main()
