import unittest
from logic.image_model import ImageItem, ImageTableModel

class TestAyonTokens(unittest.TestCase):
    def test_ayon_metadata_tokens_expansion(self):
        model = ImageTableModel()
        item = ImageItem(
            file_path="C:/tmp/test_shot.v002.1001.exr",
            label="",
            version=2,
            category="AYON",
            product_type="render",
            representation="exr",
            is_ayon_item=True
        )
        item.camel_case = False
        item.ayon_path = "sq010/sh010/comp"
        item.ayon_task_name = "comp"
        item.ayon_task_type = "Compositing"
        item.metadata.update({
            "folder_path": "sq010/sh010",
            "folder_name": "sh010",
            "folder_description": "Shot 010 Description",
            "folder_status": "In Progress",
            "task_name": "comp",
            "task_type": "Compositing",
            "task_description": "Comp Task Description",
            "task_status": "Ready",
            "product_name": "renderMain",
            "product_type": "render",
            "product_version": "v002",
            "product_status": "Approved",
            "product_source": "nuke_script_v02.nk",
            "version": 2,
            "representation": "exr"
        })

        # Test all 15 tokens with snake_case
        template = (
            "{folder_path}|{folder_name}|{folder_description}|{folder_status}|"
            "{task_name}|{task_type}|{task_description}|{task_status}|"
            "{product_name}|{product_type}|{product_version}|{product_status}|"
            "{product_source}|{version}|{representation}"
        )
        expected = (
            "sq010/sh010|sh010|Shot 010 Description|In Progress|"
            "comp|Compositing|Comp Task Description|Ready|"
            "renderMain|render|v002|Approved|"
            "nuke_script_v02.nk|2|exr"
        )
        result = model._expand_string(template, item)
        self.assertEqual(result, expected)

    def test_ayon_metadata_tokens_with_spaces_and_cases(self):
        model = ImageTableModel()
        item = ImageItem(
            file_path="C:/tmp/test_shot.v002.1001.exr",
            label="",
            version=2,
            category="AYON",
            product_type="render",
            representation="exr",
            is_ayon_item=True
        )
        item.camel_case = False
        item.metadata.update({
            "folder_path": "sq010/sh010",
            "folder_name": "sh010",
            "folder_description": "Shot 010 Desc",
            "folder_status": "In Progress",
            "task_name": "comp",
            "task_type": "Compositing",
            "task_description": "Task Desc",
            "task_status": "Ready",
            "product_name": "renderMain",
            "product_type": "render",
            "product_version": "v002",
            "product_status": "Approved",
            "product_source": "nuke_script_v02.nk",
            "version": 2,
            "representation": "exr"
        })

        # Test spaces in token names & case-insensitivity
        template_spaces = "{Folder Path} - {Folder Name} - {Folder Status} - {Product Source} - {Product Status}"
        res = model._expand_string(template_spaces, item)
        self.assertEqual(res, "sq010/sh010 - sh010 - In Progress - nuke_script_v02.nk - Approved")

if __name__ == "__main__":
    unittest.main()
