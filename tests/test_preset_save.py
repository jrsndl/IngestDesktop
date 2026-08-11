import sys
import os
import unittest
import json
import tempfile
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from gui.main_window import MainWindow

class TestPresetSave(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.presets_dir = os.path.join(self.temp_dir.name, "presets")
        os.makedirs(self.presets_dir, exist_ok=True)
        
        self.preset_a_path = os.path.join(self.presets_dir, "PresetA.json")
        preset_a_data = {
            "ayon_project": "Project_Alpha",
            "active_preset": "PresetA"
        }
        with open(self.preset_a_path, "w") as f:
            json.dump(preset_a_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_topbar_button_presence_and_order(self):
        main_win = MainWindow()
        top_bar = main_win.top_bar
        self.assertTrue(hasattr(top_bar, "btn_save_preset"))
        self.assertEqual(top_bar.btn_save_preset.text(), "Save Preset")
        
        # Check order in layout: btn_load_preset -> btn_save_preset -> btn_prefs
        layout = top_bar.layout
        load_idx = -1
        save_idx = -1
        prefs_idx = -1
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget == top_bar.btn_load_preset:
                load_idx = i
            elif widget == top_bar.btn_save_preset:
                save_idx = i
            elif widget == top_bar.btn_prefs:
                prefs_idx = i
                
        self.assertNotEqual(load_idx, -1)
        self.assertNotEqual(save_idx, -1)
        self.assertNotEqual(prefs_idx, -1)
        self.assertTrue(load_idx < save_idx < prefs_idx)

    @patch("PySide6.QtWidgets.QMessageBox.warning", return_value=QMessageBox.Yes)
    def test_save_preset_loaded_overwrites_with_warning(self, mock_warning):
        main_win = MainWindow()
        main_win.secrets["presets_folder"] = self.presets_dir
        main_win.update_preset_dropdown()

        # Load PresetA
        main_win.top_bar.combo_preset.setCurrentText("PresetA")
        main_win.config["active_preset"] = "PresetA"
        main_win.config["test_custom_setting"] = "NewValue"

        # Trigger save preset
        main_win.perform_save_preset()

        # Warning dialog must have been displayed
        mock_warning.assert_called()

        # Verify file was updated with new setting
        with open(self.preset_a_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("test_custom_setting"), "NewValue")

    @patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("PresetNew", True))
    def test_save_preset_no_loaded_preset_prompts_name(self, mock_input):
        main_win = MainWindow()
        main_win.secrets["presets_folder"] = self.presets_dir
        main_win.update_preset_dropdown()

        # Set preset to None / Active
        main_win.top_bar.combo_preset.setCurrentText("(None / Active)")
        main_win.config["active_preset"] = ""
        main_win.config["test_new_preset_setting"] = "ValueX"

        main_win.perform_save_preset()

        # Should ask for preset name
        mock_input.assert_called()

        # Check new file created
        new_preset_path = os.path.join(self.presets_dir, "PresetNew.json")
        self.assertTrue(os.path.exists(new_preset_path))
        with open(new_preset_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("test_new_preset_setting"), "ValueX")

if __name__ == "__main__":
    unittest.main()
