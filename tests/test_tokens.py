import unittest

from logic import tokens
from logic.image_model import ImageItem, ImageTableModel
from logic.grouping_engine import compute_group_key


def make_item(**kw):
    preset = kw.pop("preset", {"Name": "PNG", "Variant": "{label}", "Colorspace": "sRGB", "Representation": "png"})
    it = ImageItem("C:/proj/shotA/plate_bg_v003.png", label="plate_bg", version=3, category="Still",
                   preset_name=preset.get("Name"), variant=preset.get("Variant"), product_type="render",
                   camel_case=True, representation=preset.get("Representation"), preset_data=preset, **kw)
    return it


class TestTokenEngine(unittest.TestCase):
    def setUp(self):
        self.model = ImageTableModel()
        self.model.product_name_template = "{product_type}{variant}"
        self.model.product_name_camel = True

    def test_nested_variant_is_expanded(self):
        it = make_item()
        self.assertEqual(self.model.variant_value(it), "plate_bg")
        self.assertEqual(self.model.product_name(it), "renderPlate_bg")
        # CSV cell / group key see the same variant
        self.assertEqual(self.model.expand_tokens("{variant}", it), "plate_bg")

    def test_commands_are_never_camel_cased(self):
        it = make_item()
        cmd = self.model.expand_tokens("x -f {extension} --cc {repre_color} -o {parent_folder}", it)
        self.assertEqual(cmd, "x -f png --cc sRGB -o shotA")

    def test_self_reference_does_not_recurse(self):
        it = make_item()
        self.model.product_name_template = "{product_name}_x"
        self.assertEqual(self.model.product_name(it), "_x")

    def test_case_space_and_alias_insensitive(self):
        it = make_item()
        self.assertEqual(self.model.expand_tokens("{Label}|{LABEL}|{prod_name}|{repre}|{item.version}", it),
                         "plate_bg|plate_bg|renderPlate_bg|png|3")

    def test_unknown_token_is_kept(self):
        it = make_item()
        self.assertEqual(self.model.expand_tokens("{nope}_{label}", it), "{nope}_plate_bg")

    def test_metadata_token(self):
        it = make_item()
        it.metadata["width"] = 1920
        self.assertEqual(self.model.expand_tokens("{metadata.width}x{metadata.missing}", it), "1920x{metadata.missing}")

    def test_version_user_wins(self):
        it = make_item(version_user="7")
        self.assertEqual(self.model.expand_tokens("{version}", it), "7")
        self.assertEqual(compute_group_key(it, "{variant}_{version}", self.model), "plate_bg_7")

    def test_ayon_assignment_precedence_and_clear(self):
        it = make_item()
        it.metadata["folder_name"] = "parsed_sh"
        it.parsed_tags = {"folder_name": "parsed_sh"}
        # assignment writes AYON values into metadata and remembers them
        it.ayon_path = "/sq01/sh010/comp"
        it.ayon_task_name = "comp"
        it.metadata["folder_name"] = "sh010"
        it.remember_ayon_context()
        self.assertEqual(self.model.expand_tokens("{folder_name}/{task_name}", it), "sh010/comp")
        it.clear_ayon_assignment()
        self.assertEqual(self.model.expand_tokens("{folder_name}/{task_name}", it), "parsed_sh/")

    def test_tool_paths_with_spaces_are_quoted(self):
        it = make_item()
        self.model.ffmpeg_path = "C:/Program Files/ffmpeg/bin/ffmpeg.exe"
        self.assertEqual(self.model.expand_tokens("{ffmpeg} -i x", it),
                         '"C:/Program Files/ffmpeg/bin/ffmpeg.exe" -i x')
        self.assertEqual(self.model.expand_tokens('"{ffmpeg}" -i x', it),
                         '"C:/Program Files/ffmpeg/bin/ffmpeg.exe" -i x')

    def test_sequence_filename_tokens(self):
        it = ImageItem("D:/s/plate.1001.exr", label="plate", is_sequence=True)
        self.assertEqual(self.model.expand_tokens("{filename}|{filename_printf}", it),
                         "D:/s/plate.####.exr|D:/s/plate.%04d.exr")

    def test_pure_engine_without_model(self):
        it = make_item()
        self.assertEqual(tokens.expand("{label}_{fps_int}", it), "plate_bg_25")


if __name__ == "__main__":
    unittest.main()
