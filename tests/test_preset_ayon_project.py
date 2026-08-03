import sys
import os
import unittest
import json
import tempfile

from PySide6.QtWidgets import QApplication

# Ensure QApplication instance exists
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from gui.main_window import MainWindow

class TestPresetAyonProject(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.presets_dir = os.path.join(self.temp_dir.name, "presets")
        os.makedirs(self.presets_dir, exist_ok=True)
        
        # Create dummy preset files
        self.preset_a_path = os.path.join(self.presets_dir, "PresetA.json")
        self.preset_b_path = os.path.join(self.presets_dir, "PresetB.json")
        
        preset_a_data = {
            "ayon_project": "Project_Alpha",
            "last_ayon_project": "Project_Alpha",
            "active_preset": "PresetA"
        }
        preset_b_data = {
            "ayon_project": "Project_Beta",
            "last_ayon_project": "Project_Beta",
            "active_preset": "PresetB"
        }
        
        with open(self.preset_a_path, "w") as f:
            json.dump(preset_a_data, f)
        with open(self.preset_b_path, "w") as f:
            json.dump(preset_b_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_preset_ayon_project_loading(self):
        main_win = MainWindow()
        main_win.secrets["presets_folder"] = self.presets_dir
        
        # Mock ayon panel projects
        main_win.ayon_panel.set_projects(["Project_Alpha", "Project_Beta", "Default_Project"])
        main_win.ayon_panel.combo_project.setCurrentText("Default_Project")
        
        # Verify initial project is Default_Project
        self.assertEqual(main_win.ayon_panel.combo_project.currentText(), "Default_Project")
        
        # Load PresetA
        main_win._on_preset_changed("PresetA")
        
        # Verify combo project updated to Project_Alpha
        self.assertEqual(main_win.ayon_panel.combo_project.currentText(), "Project_Alpha")
        self.assertEqual(main_win.config.get("ayon_project"), "Project_Alpha")
        
        # Load PresetB
        main_win._on_preset_changed("PresetB")
        
        # Verify combo project updated to Project_Beta
        self.assertEqual(main_win.ayon_panel.combo_project.currentText(), "Project_Beta")
        self.assertEqual(main_win.config.get("ayon_project"), "Project_Beta")

if __name__ == "__main__":
    unittest.main()
