"""Presets switched off in Preferences are never used to match files."""
import unittest

from utils import evaluate_preset


class TestPresetEnabled(unittest.TestCase):
    def test_off_preset_is_skipped(self):
        presets = {"stills": [{"Name": "Off", "Filter": "png", "Enabled": False},
                              {"Name": "On", "Filter": "png"}]}
        self.assertEqual(evaluate_preset("/x/a.png", presets, "stills")["Name"], "On")
        presets["stills"][1]["Enabled"] = False
        self.assertIsNone(evaluate_preset("/x/a.png", presets, "stills"))


if __name__ == "__main__":
    unittest.main()
