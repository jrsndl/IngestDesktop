import unittest
from logic.image_model import ImageItem
from logic.grouping_engine import (
    compute_group_key, find_matching_group_def, 
    validate_group_representations, apply_group_inheritance
)

class TestGroupingEngine(unittest.TestCase):
    def test_compute_group_key(self):
        item = ImageItem(file_path="c:/my/seq01_sh002_comp_v001.exr", label="seq01_sh002_comp_v001")
        item.metadata["folder_name"] = "sh002"
        item.task_name = "comp"
        item.variant = "main"
        item.version = 1
        
        key = compute_group_key(item, "{folder_name}_{task_name}_{variant}_v{version}")
        self.assertEqual(key, "sh002_comp_main_v1")

    def test_find_matching_group_def(self):
        group_defs = [
            {"name": "Comp Group", "enabled": True, "task_types": "", "task_names": "comp lighting"},
            {"name": "General Group", "enabled": True, "task_types": "", "task_names": ""}
        ]
        
        item1 = ImageItem(file_path="c:/test/a.exr", label="a")
        item1.task_name = "comp"
        
        item2 = ImageItem(file_path="c:/test/b.exr", label="b")
        item2.task_name = "anim"

        match1 = find_matching_group_def([item1], group_defs)
        self.assertEqual(match1["name"], "Comp Group")

        match2 = find_matching_group_def([item2], group_defs)
        self.assertEqual(match2["name"], "General Group")

    def test_validate_group_representations(self):
        item_exr = ImageItem(file_path="c:/test/render.exr", label="render")
        item_exr.representation = "exr"
        
        item_mov = ImageItem(file_path="c:/test/review.mov", label="review")
        item_mov.representation = "mov"
        
        g_def = {
            "always_repres": "exr",
            "always_or_convert_repres": "h264"
        }
        
        # Missing h264
        is_err, missing = validate_group_representations([item_exr, item_mov], g_def)
        self.assertTrue(is_err)
        self.assertIn("h264", missing)
        
        # With convert_review = True
        item_mov.convert_review = True
        is_err2, missing2 = validate_group_representations([item_exr, item_mov], g_def)
        self.assertFalse(is_err2)

    def test_apply_group_inheritance(self):
        item_exr = ImageItem(file_path="c:/test/render.exr", label="render")
        item_exr.representation = "exr"
        item_exr.task_name = "comp"
        item_exr.metadata["episode"] = "ep101"
        
        item_mov = ImageItem(file_path="c:/test/review.mov", label="review")
        item_mov.representation = "mov"
        item_mov.task_name = ""
        item_mov.metadata["episode"] = ""
        
        g_def = {
            "inheritance_repre_priority": "exr mov",
            "inherit_columns": "task_name episode"
        }
        
        apply_group_inheritance([item_exr, item_mov], g_def)
        
        self.assertEqual(item_mov.task_name, "comp")
        self.assertEqual(item_mov.metadata["episode"], "ep101")

if __name__ == "__main__":
    unittest.main()
