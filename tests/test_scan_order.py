"""Sequence detection, frame ranges and scan order (tags before presets)."""
import os
import shutil
import tempfile
import unittest

import logic.scanner as scanner_mod
from logic.scanner import ImageScanner
from logic.seqparse import split_name, parse_version, frame_range_info

R = r"([._]v|v)(\d+)"


class TestSeqParse(unittest.TestCase):
    def test_shot_numbers_are_not_frames(self):
        self.assertIsNone(split_name("sh010_v001.exr", R).frame)
        self.assertNotEqual(split_name("sh010_v001.exr", R).label, split_name("sh020_v001.exr", R).label)

    def test_frames(self):
        p = split_name("shot_v001.1001.exr", R)
        self.assertEqual((p.version, p.frame, p.pad, p.label), (1, 1001, 4, "shot"))
        self.assertEqual(split_name("plate.-001.exr", R).frame, -1)
        self.assertEqual(split_name("render0001.exr", R).frame, 1)
        self.assertIsNone(split_name("shot010.exr", R).frame)

    def test_version_regex_variants(self):
        self.assertEqual(parse_version("x_v12.exr", r"_v\d+"), 12)      # no group: no crash
        self.assertEqual(parse_version("x_v12.exr", r"_v(\d+)"), 12)
        self.assertEqual(parse_version("x.exr", R), 1)

    def test_numeric_range_and_gaps(self):
        self.assertEqual(frame_range_info([995, 1005, 996, 1000])[:3], (995, 1005, 7))


class TestScannerGrouping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = scanner_mod.generate_thumbnail_image
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None

    def tearDown(self):
        scanner_mod.generate_thumbnail_image = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def touch(self, *names):
        for n in names:
            p = os.path.join(self.tmp, n)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()

    def build(self, **kw):
        sc = ImageScanner(self.tmp, version_regex=R, **kw)
        groups, videos, others = sc._classify(scanner_mod.get_all_files(self.tmp, True))
        return [sc._make_image_item(e) for e in groups.values()]

    def test_shots_stay_separate_and_frames_sort_numerically(self):
        self.touch("sh010_v001.exr", "sh020_v001.exr", *[f"plate_v002.{f}.exr" for f in range(995, 1006)])
        items = {it.label: it for it in self.build()}
        self.assertIn("sh010_v001", items)
        self.assertIn("sh020_v001", items)
        seq = items["plate"]
        self.assertTrue(seq.is_sequence)
        self.assertEqual((seq.frame_start, seq.frame_end, seq.version), (995, 1005, 2))
        self.assertEqual(seq.category, "sequence[0995-1005]")

    def test_tags_are_parsed_before_preset(self):
        self.touch("sq01_sh010_comp_main_v001.png")
        presets = {"stills": [{"Name": "PNG", "Filter By": "Extension", "Filter": "png",
                               "Variant": "{variant_parsed}", "Representation": "png"}]}
        cfg = {"folder_regex": r"^[^_]*_([^_]*)_", "variant_regex": r"^[^_]*_[^_]*_[^_]*_([^_]*)"}
        it = self.build(presets=presets, config=cfg)[0]
        self.assertTrue(getattr(it, "_tags_parsed", False))
        self.assertEqual(it.metadata.get("folder_name"), "sh010")
        self.assertEqual(it.effective_variant, "main")
        self.assertEqual(it.preset_name, "PNG")

    def test_review_lookup_ignores_other_folders(self):
        self.touch("shotA/comp_v001.png", "shotB/comp_v001.mp4")
        with open(os.path.join(self.tmp, "shotB", "comp_v001.mp4"), "wb") as f:
            f.write(b"x")
        presets = {"stills": [{"Name": "PNG", "Filter By": "Extension", "Filter": "png", "Convert Review": True}]}
        its = [i for i in self.build(presets=presets) if i.file_path.endswith(".png")]
        self.assertEqual(its[0].review_status, "waiting")


if __name__ == "__main__":
    unittest.main()
