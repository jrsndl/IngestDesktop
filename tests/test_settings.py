"""Preferences file layout, migration and presets (logic/settings.py)."""
import os
import tempfile
import unittest

from logic import settings


class TestSettings(unittest.TestCase):
    def test_old_flat_file_is_migrated(self):
        old = {"high_res_size": 640, "thumbnail_size": 200, "ayon_project_name": "Proj",
               "low_res_size": 100, "geometry": "abc", "product_name": "{variant}"}
        flat = settings.flatten(old)
        self.assertEqual(flat["thumb_size"], 640)
        self.assertEqual(flat["default_thumb_size"], 200)
        self.assertEqual(flat["ayon_project"], "Proj")
        self.assertNotIn("low_res_size", flat)

    def test_sections_and_session_are_separate(self):
        flat = settings.defaults()
        flat.update({"product_name": "{variant}", "geometry": "abc", "ffmpeg_path": "x", "custom": 1})
        prefs = settings.sectioned_preferences(flat)
        self.assertEqual(prefs["format"], settings.FORMAT_VERSION)
        self.assertEqual(prefs["AYON"]["product_name"], "{variant}")
        self.assertEqual(prefs["Other"]["custom"], 1)
        all_pref_keys = {k for sec, v in prefs.items() if isinstance(v, dict) for k in v}
        self.assertNotIn("geometry", all_pref_keys)
        self.assertNotIn("ffmpeg_path", all_pref_keys)
        self.assertEqual(settings.session_state(flat)["Session"]["geometry"], "abc")

    def test_round_trip(self):
        flat = settings.defaults()
        flat["version_regex"] = r"_v(\d+)"
        back = settings.flatten(settings.sectioned_preferences(flat))
        self.assertEqual(back["version_regex"], r"_v(\d+)")
        self.assertNotIn("geometry", settings.preferences_only(back))

    def test_every_section_key_has_one_home(self):
        seen = {}
        for sec, keys in settings.PREFERENCES.items():
            for k in keys:
                self.assertNotIn(k, seen, f"{k} in {sec} and {seen.get(k)}")
                seen[k] = sec
                self.assertNotIn(k, settings.SESSION)
                self.assertNotIn(k, settings.INSTALL_KEYS)

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "c.json")
            settings.write_json_atomic(p, {"a": "ž"})
            self.assertEqual(settings.read_json(p), {"a": "ž"})
            self.assertEqual([f for f in os.listdir(os.path.dirname(p)) if f.startswith(".tmp_")], [])


if __name__ == "__main__":
    unittest.main()
