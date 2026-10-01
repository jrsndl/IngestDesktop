"""Qt-free tests for logic/tag_parser.py (mirrors test_auto_assign_parse.py)."""
import unittest

from logic.image_model import ImageItem
from logic.tag_parser import get_parse_target, parse_item_tags


class TestTagParser(unittest.TestCase):
    def test_targets(self):
        item = ImageItem(file_path="c:/foo/bar/minusthree/minustwo/minusone/fname.ext", label="fname")
        self.assertEqual(get_parse_target(item, "File Name Only"), "fname.ext")
        self.assertEqual(get_parse_target(item, "Path Only"), "c:/foo/bar/minusthree/minustwo/minusone")
        self.assertEqual(get_parse_target(item, "Folder -1"), "minusone")
        self.assertEqual(get_parse_target(item, "Folder -3"), "minusthree")
        self.assertEqual(get_parse_target(item, "Folder +2", "c:/foo"), "minusthree")
        self.assertEqual(get_parse_target(item, "Folder +2"), "")

    def test_integration(self):
        item = ImageItem(file_path="c:/my/root/seq010/shot0020/v003/render_main_v003.exr", label="x")
        cfg = {"version_parse": "Folder -1", "version_regex": r"v(\d+)",
               "sequence_parse": "Folder +1", "sequence_regex": r"(.*)",
               "folder_parse": "Folder +2", "folder_regex": r"(.*)"}
        parse_item_tags(item, cfg, "c:/my/root")
        self.assertEqual(item.version, 3)
        self.assertEqual(item.metadata.get("sequence"), "seq010")
        self.assertEqual(item.metadata.get("folder_name"), "shot0020")
        self.assertEqual(item.parsed_tags.get("folder_name"), "shot0020")

    def test_repl_and_lambda(self):
        item = ImageItem(file_path="c:/my/root/sq010_sh0020_v001.exr", label="x")
        parse_item_tags(item, {"folder_regex": r"^([^_]+)_([^_]+)_.*$", "folder_repl": r"\1/\2",
                               "version_regex": r"([._]v|v)(\d+)",
                               "version_repl": "lambda m: str(int(m.group(2)) + 1000)"})
        self.assertEqual(item.metadata.get("folder_name"), "sq010/sh0020")
        self.assertEqual(item.version, 1001)

    def test_fixed_task(self):
        item = ImageItem(file_path="c:/r/comp_v001.exr", label="x")
        parse_item_tags(item, {"fixed_task_name_enabled": True, "fixed_task_name": "comp"})
        self.assertEqual(item.metadata.get("task_name"), "comp")


if __name__ == "__main__":
    unittest.main()
