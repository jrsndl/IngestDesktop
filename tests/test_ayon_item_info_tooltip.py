import unittest
import sys

from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem, ImageTableModel
from gui.thumbnail_area import ThumbnailItem
from gui.prefs_dialog import PreferencesDialog

app = QApplication.instance() or QApplication(sys.argv)

class TestAyonItemInfoTooltip(unittest.TestCase):
    def test_ayon_item_info_tooltip_resolution(self):
        item = ImageItem("ayon://test/folder", "test_item", is_ayon_item=True, camel_case=False)
        item.ayon_path = "/shots/shot01/comp"
        item.ayon_task_name = "comp"
        item.metadata = {"folder_name": "shot01", "task_name": "comp"}

        templates = {
            "item_info_stills": "STILL TOOLTIP",
            "item_info_ayon": "AYON ITEM TOOLTIP\n{ayon_task_name}\n{folder_name}"
        }

        model = ImageTableModel()
        model._items = [item]
        thumb = ThumbnailItem(item)

        thumb.update_tooltip(templates, model)

        expected_tooltip = "AYON ITEM TOOLTIP\ncomp\nshot01"
        self.assertEqual(thumb.toolTip(), expected_tooltip)

    def test_preferences_dialog_single_ayon_items_tab(self):
        config = {"item_info_ayon": "AYON info text"}
        secrets = {}
        dlg = PreferencesDialog(config, secrets)

        # Count tab titles named "AYON Items"
        ayon_items_tabs = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count()) if dlg.tabs.tabText(i) == "AYON Items"]
        self.assertEqual(len(ayon_items_tabs), 1)

        # Ensure item_info_ayon is present and correctly loaded
        self.assertEqual(dlg.item_info_ayon.toPlainText(), "AYON info text")

        # Test settings output
        dlg.item_info_ayon.setPlainText("Updated AYON info")
        new_config, new_secrets = dlg.get_settings()
        self.assertEqual(new_config.get("item_info_ayon"), "Updated AYON info")

if __name__ == "__main__":
    unittest.main()
