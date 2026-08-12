import unittest
from logic.ayon_autopick import autopick_task, autopick_product, autopick_version, autopick_representation

class TestAyonAutopick(unittest.TestCase):
    def test_autopick_task(self):
        tasks = [
            {"id": "1", "name": "fx", "type": "FX"},
            {"id": "2", "name": "comp_main", "type": "Compositing"},
            {"id": "3", "name": "edit", "type": "Editing"}
        ]
        # Match type priority 'Compositing'
        chosen = autopick_task(tasks, "Compositing Editing", "comp")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "2")

        # Match name priority when type priority has no match
        chosen_name = autopick_task(tasks, "Lighting", "edit")
        self.assertIsNotNone(chosen_name)
        self.assertEqual(chosen_name["id"], "3")

    def test_autopick_product(self):
        products = [
            {"id": "p1", "name": "renderMain", "type": "render"},
            {"id": "p2", "name": "reviewMain", "type": "review"},
            {"id": "p3", "name": "plateBG", "type": "plate"}
        ]
        # Match type substring 'review'
        chosen = autopick_product(products, "review render plate", "main")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "p2")

    def test_autopick_version(self):
        versions = [
            {"version": 1, "status": "In Progress"},
            {"version": 2, "status": "Approved"},
            {"version": 3, "status": "Pending Review"}
        ]
        # Max version
        chosen_max = autopick_version(versions, "Max Version", "")
        self.assertEqual(chosen_max["version"], 3)

        # Min version
        chosen_min = autopick_version(versions, "Min Version", "")
        self.assertEqual(chosen_min["version"], 1)

        # By status
        chosen_status = autopick_version(versions, "by Status Only", "Approved")
        self.assertEqual(chosen_status["version"], 2)

        # By status fallback
        chosen_fallback = autopick_version(versions, "by Status or Max", "NonExistentStatus")
        self.assertEqual(chosen_fallback["version"], 3)

    def test_autopick_representation(self):
        repres = [
            {"name": "exr", "attrib": {"path": "/path/file.exr"}},
            {"name": "mp4", "attrib": {"path": "/path/file.mp4"}},
            {"name": "mov", "attrib": {"path": "/path/file.mov"}}
        ]
        chosen = autopick_representation(repres, "mp4 mov png")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["name"], "mp4")

if __name__ == "__main__":
    unittest.main()
