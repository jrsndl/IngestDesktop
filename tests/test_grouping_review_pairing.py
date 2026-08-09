import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.image_model import ImageItem
from logic.grouping_engine import compute_group_key, pair_group_reviews


class TestGroupingReviewPairing(unittest.TestCase):

    def test_pair_group_reviews(self):
        # 1. Create a sequence item and a review mp4 item in the same group
        item_seq = ImageItem("C:/project/seqs/sh01/v01/sh01_v01.1001.exr", label="sh01_v01", category="sequence", version=1, is_sequence=True)
        item_seq.metadata["folder_name"] = "sh01"
        item_seq.metadata["task_name"] = "comp"
        item_seq.metadata["variant_parsed"] = "main"

        item_video = ImageItem("C:/project/reviews/custom_review_file.mp4", label="custom_review_file", category="Video", version=1)
        item_video.metadata["folder_name"] = "sh01"
        item_video.metadata["task_name"] = "comp"
        item_video.metadata["variant_parsed"] = "main"

        template = "{folder_name}{task_name}{variant}{version}"

        item_seq.group_key = compute_group_key(item_seq, template)
        item_video.group_key = compute_group_key(item_video, template)

        # Verify group keys match
        self.assertEqual(item_seq.group_key, item_video.group_key)

        group_items = [item_seq, item_video]
        pair_group_reviews(group_items)

        # Assert review pairing
        self.assertEqual(item_seq.review_status, "done")
        self.assertEqual(item_seq.review_file_path, "C:/project/reviews/custom_review_file.mp4")

    def test_dynamic_group_key_uncouple(self):
        # Sequence item with version 1
        item_seq = ImageItem("C:/project/seqs/sh01/v01/sh01_v01.1001.exr", label="sh01_v01", category="sequence", version=1, is_sequence=True)
        item_seq.metadata["folder_name"] = "sh01"
        item_seq.metadata["task_name"] = "comp"
        item_seq.metadata["variant_parsed"] = "main"

        # Video item with version 2
        item_video = ImageItem("C:/project/reviews/custom_review_v02.mp4", label="custom_review_v02", category="Video", version=2)
        item_video.metadata["folder_name"] = "sh01"
        item_video.metadata["task_name"] = "comp"
        item_video.metadata["variant_parsed"] = "main"

        template = "{folder_name}{task_name}{variant}{version}"

        item_seq.group_key = compute_group_key(item_seq, template)
        item_video.group_key = compute_group_key(item_video, template)

        # Group keys should differ because versions differ
        self.assertNotEqual(item_seq.group_key, item_video.group_key)

        # Running pair_group_reviews on item_seq's group (contains only item_seq)
        pair_group_reviews([item_seq])
        self.assertNotEqual(getattr(item_seq, "review_file_path", None), item_video.file_path)

    def test_review_repre_priority(self):
        item_seq = ImageItem("C:/project/seqs/sh01/v01/sh01_v01.1001.exr", label="sh01_v01", category="sequence", version=1, is_sequence=True, representation="exr")
        item_seq.task_name = "comp"

        item_mov = ImageItem("C:/project/reviews/sh01_v01.mov", label="sh01_v01", category="Video", version=1, representation="mov")
        item_mov.task_name = "comp"

        item_mp4 = ImageItem("C:/project/reviews/sh01_v01.mp4", label="sh01_v01", category="Video", version=1, representation="mp4")
        item_mp4.task_name = "comp"

        config = {
            "group_definitions": [
                {
                    "name": "Comp Group",
                    "enabled": True,
                    "task_names": "comp",
                    "review_repre": "mp4 mov"
                }
            ]
        }

        group_items = [item_seq, item_mov, item_mp4]
        pair_group_reviews(group_items, config=config)

        # mp4 should be selected over mov because review_repre is 'mp4 mov'
        self.assertEqual(item_seq.review_file_path, "C:/project/reviews/sh01_v01.mp4")


if __name__ == "__main__":
    unittest.main()
