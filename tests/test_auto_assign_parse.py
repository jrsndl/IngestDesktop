import sys
import unittest
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from logic.image_model import ImageItem
from gui.main_window import MainWindow

class TestAutoAssignParseModes(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        
    def test_file_name_only(self):
        item = ImageItem(file_path="c:/foo/bar/fname.ext", label="fname")
        target = self.window._get_parse_target(item, "File Name Only")
        self.assertEqual(target, "fname.ext")

    def test_path_only(self):
        item = ImageItem(file_path="c:/foo/bar/fname.ext", label="fname")
        target = self.window._get_parse_target(item, "Path Only")
        self.assertEqual(target, "c:/foo/bar")

    def test_full_path(self):
        item = ImageItem(file_path="c:/foo/bar/fname.ext", label="fname")
        target = self.window._get_parse_target(item, "Full Path")
        self.assertEqual(target, "c:/foo/bar/fname.ext")

    def test_folder_plus_n(self):
        self.window.model.source_folder = "c:/my/root"
        item = ImageItem(file_path="c:/my/root/plusone/plustwo/plusthree/fname.ext", label="fname")
        
        target1 = self.window._get_parse_target(item, "Folder +1")
        self.assertEqual(target1, "plusone")
        
        target2 = self.window._get_parse_target(item, "Folder +2")
        self.assertEqual(target2, "plustwo")
        
        target3 = self.window._get_parse_target(item, "Folder +3")
        self.assertEqual(target3, "plusthree")

    def test_folder_minus_n(self):
        item = ImageItem(file_path="c:/foo/bar/minusthree/minustwo/minusone/fname.ext", label="fname")
        
        target1 = self.window._get_parse_target(item, "Folder -1")
        self.assertEqual(target1, "minusone")
        
        target2 = self.window._get_parse_target(item, "Folder -2")
        self.assertEqual(target2, "minustwo")
        
        target3 = self.window._get_parse_target(item, "Folder -3")
        self.assertEqual(target3, "minusthree")

    def test_parse_item_tags_integration(self):
        self.window.model.source_folder = "c:/my/root"
        item = ImageItem(file_path="c:/my/root/seq010/shot0020/v003/render_main_v003.exr", label="render_main_v003")
        
        self.window.config["version_parse"] = "Folder -1" # "v003"
        self.window.config["version_regex"] = r"v(\d+)"
        
        self.window.config["sequence_parse"] = "Folder +1" # "seq010"
        self.window.config["sequence_regex"] = r"(.*)"
        
        self.window.config["folder_parse"] = "Folder +2" # "shot0020"
        self.window.config["folder_regex"] = r"(.*)"
        
        self.window._parse_item_tags(item)
        
        self.assertEqual(item.version, 3)
        self.assertEqual(item.metadata.get("sequence"), "seq010")
        self.assertEqual(item.metadata.get("folder_name"), "shot0020")

    def test_repl_regex_expansion(self):
        item = ImageItem(file_path="c:/my/root/sq010_sh0020_v001.exr", label="sq010_sh0020_v001")
        self.window.config["folder_parse"] = "File Name Only"
        self.window.config["folder_regex"] = r"^([^_]+)_([^_]+)_.*$"
        self.window.config["folder_repl"] = r"\1/\2"
        self.window._parse_item_tags(item)
        self.assertEqual(item.metadata.get("folder_name"), "sq010/sh0020")

    def test_repl_lambda_expression(self):
        item = ImageItem(file_path="c:/my/root/shot_v001.exr", label="shot_v001")
        self.window.config["version_parse"] = "File Name Only"
        self.window.config["version_regex"] = r"([._]v|v)(\d+)"
        self.window.config["version_repl"] = "lambda pattern: str(int(pattern.group(2)) + 1000)"
        self.window._parse_item_tags(item)
        self.assertEqual(item.version, 1001)

    def test_repl_lambda_string_manipulation(self):
        item = ImageItem(file_path="c:/my/root/comp_v001.exr", label="comp_v001")
        self.window.config["fixed_task_name_enabled"] = False
        self.window.config["task_parse"] = "File Name Only"
        self.window.config["task_regex"] = r"^([a-z]+)_"
        self.window.config["task_repl"] = "lambda pattern: pattern.group(1).upper() + '_FX'"
        self.window._parse_item_tags(item)
        self.assertEqual(item.metadata.get("task_name"), "COMP_FX")

    def test_variant_parsed_override(self):
        item = ImageItem(file_path="c:/my/root/eqs_sh002__v02_DR_RTAO_v001_review.mp4", label="eqs_sh002__v02_DR_RTAO_v001_review", variant="{variant_parsed}")
        self.window.config["variant_parse"] = "File Name Only"
        self.window.config["variant_regex"] = r"(.*)"
        self.window.config["variant_repl"] = "BAF"
        self.window._parse_item_tags(item)
        self.assertEqual(item.metadata.get("variant_parsed"), "BAF")
        self.assertEqual(item.effective_variant, "BAF")
        self.window.model.items = [item]
        self.assertEqual(self.window.model.data(self.window.model.index(0, 3)), "BAF")

    def test_apply_preferences_updates_variant_parsed_and_model_data(self):
        item = ImageItem(file_path="c:/my/root/eqs_sh002_v001.exr", label="eqs_sh002_v001", category="Sequence")
        self.window.model.items = [item]
        
        # Setup config with a preset for sequences
        self.window.config["presets"] = {
            "sequences": [{
                "Name": "EXRs",
                "Filter By": "Extension",
                "Filter": "exr",
                "Product Type": "render",
                "Variant": "{variant_parsed}",
                "Active": True
            }]
        }
        self.window.config["variant_parse"] = "File Name Only"
        self.window.config["variant_regex"] = r"([^_]+)"
        self.window.config["variant_repl"] = "OLD_VARIANT"
        self.window.config["product_name"] = "{variant}"
        
        import json
        old_detect = self.window.config.get("detect_sequences", True)
        old_thumb = self.window.config.get("seq_thumb_frame", "Middle")
        old_regex = self.window.config.get("version_regex", r"([._]v|v)(\d+)")
        old_exts = json.dumps(self.window.config.get("extensions", {}), sort_keys=True)

        # Apply initial settings
        self.window._apply_preferences(dict(self.window.config), {}, old_detect, old_thumb, old_regex, old_exts, show_message=False, save=False)
        self.assertEqual(item.metadata.get("variant_parsed"), "OLD_VARIANT")
        self.assertEqual(item.effective_variant, "OLD_VARIANT")
        self.assertEqual(self.window.model.data(self.window.model.index(0, 3)), "OLD_VARIANT")
        self.assertEqual(self.window.model.data(self.window.model.index(0, 5)), "OLD_VARIANT")

        # Now change preferences (new variant regex / repl / product_name template) and apply
        new_config = dict(self.window.config)
        new_config["variant_repl"] = "NEW_VARIANT"
        new_config["product_name"] = "PROD_{variant}"

        self.window._apply_preferences(new_config, {}, old_detect, old_thumb, old_regex, old_exts, show_message=False, save=False)

        # Verify that variant_parsed, variant (Col 3), and Product Name (Col 5) updated immediately
        self.assertEqual(item.metadata.get("variant_parsed"), "NEW_VARIANT")
        self.assertEqual(item.effective_variant, "NEW_VARIANT")
        self.assertEqual(self.window.model.data(self.window.model.index(0, 3)), "NEW_VARIANT")
        self.assertEqual(self.window.model.data(self.window.model.index(0, 5)), "PROD_NEW_VARIANT")


if __name__ == "__main__":
    unittest.main()
