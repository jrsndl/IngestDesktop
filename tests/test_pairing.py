"""Pairing footage with existing thumbnails / reviews (logic/pairing.py)."""
import os
import shutil
import tempfile
import unittest

import logic.scanner as scanner_mod
from logic.pairing import PairIndex
from logic.scanner import ImageScanner

R = "D:/job"
FILES = [f"{R}/sh010/plate.{f}.exr" for f in range(1001, 1004)] + [
    f"{R}/sh010/plate.jpg", f"{R}/sh010/plate.mp4",
    f"{R}/sh020/comp_v002.exr", f"{R}/_thumbs/comp_v002_thumbnail.jpg", f"{R}/other/comp_v002.jpg",
    f"{R}/reviews/comp_v002_review.mov", f"{R}/misc/comp_v002.mov",
    f"{R}/stills/a.png", f"{R}/stills/a.jpg", f"{R}/stills/b.png", f"{R}/stills/thumbs/b.jpg",
    f"{R}/vid/shot.mov", f"{R}/vid/shot.mp4",
]


class TestPairIndex(unittest.TestCase):
    def setUp(self):
        self.ix = PairIndex(FILES, R, ("_thumbnail", "_review"))

    def test_same_folder_same_name(self):
        self.assertEqual(self.ix.thumbnail_for(FILES[0], True), f"{R}/sh010/plate.jpg")
        self.assertEqual(self.ix.review_for(FILES[0], True), f"{R}/sh010/plate.mp4")

    def test_other_folder_needs_thumb_or_review_in_path(self):
        fp = f"{R}/sh020/comp_v002.exr"
        self.assertEqual(self.ix.thumbnail_for(fp), f"{R}/_thumbs/comp_v002_thumbnail.jpg")
        self.assertEqual(self.ix.review_for(fp), f"{R}/reviews/comp_v002_review.mov")

    def test_light_images_do_not_swallow_each_other(self):
        self.assertIsNone(self.ix.thumbnail_for(f"{R}/stills/a.png"))
        self.assertEqual(self.ix.thumbnail_for(f"{R}/stills/b.png"), f"{R}/stills/thumbs/b.jpg")

    def test_movie_needs_review_word(self):
        self.assertIsNone(self.ix.review_for(f"{R}/vid/shot.mov"))


class TestScannerPairing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = scanner_mod.generate_thumbnail_image
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None

    def tearDown(self):
        scanner_mod.generate_thumbnail_image = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_thumbnail_file_is_not_an_item_and_review_is_linked(self):
        for n in ["sh010/plate.1001.exr", "sh010/plate.1002.exr", "sh010/plate.jpg", "reviews/plate_review.mp4"]:
            p = os.path.join(self.tmp, n)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(b"x")
        sc = ImageScanner(self.tmp)
        all_files = scanner_mod.get_all_files(self.tmp, True)
        groups, videos, others = sc._classify(all_files)
        groups = sc._pair_existing_media(all_files, groups, videos)
        items = [sc._make_image_item(e) for e in groups.values()]
        self.assertEqual(len(items), 1)               # plate.jpg is the thumbnail, not an item
        seq = items[0]
        self.assertTrue(seq.conversion_thumb_path.endswith("sh010/plate.jpg"))
        self.assertTrue(seq.review_file_path.endswith("reviews/plate_review.mp4"))
        self.assertEqual(seq.review_status, "done")


class TestBoatLayout(unittest.TestCase):
    """Layout of a real shot folder: exr/<layer>/ sequences, _reviews/*.mp4, _thumbs/*.jpg."""
    B = "DB_000_0030_lgt_explosion_v47"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self._orig = scanner_mod.generate_thumbnail_image
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None
        B = self.B
        files = ([f"exr/beauty/{B}_beauty.{f}.exr" for f in (1001, 1002)] +
                 [f"exr/deep/{B}.{f}.exr" for f in (1001, 1002)] +
                 [f"_reviews/{B}_beauty.mp4", f"_reviews/{B}.mp4",
                  f"_thumbs/{B}_beauty_thumbnail.jpg", f"_thumbs/{B}_beauty_review_thumbnail.jpg",
                  f"_thumbs/{B}_thumbnail.jpg", f"_thumbs/{B}_review_thumbnail.jpg"])
        for f in files:
            p = os.path.join(self.root, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(b"x")

    def tearDown(self):
        scanner_mod.generate_thumbnail_image = self._orig
        shutil.rmtree(self.root, ignore_errors=True)

    def test_reviews_are_linked_and_hidden(self):
        from logic.grouping_engine import pair_group_reviews
        sc = ImageScanner(self.root)
        got = []

        class Cap:
            def emit(self, *a):
                got.append(a)
        sc.finished = Cap()
        sc._fetch_metadata = lambda items: None
        sc._run()
        items = got[0][0]
        seqs = {os.path.basename(os.path.dirname(i.file_path)): i for i in items if i.is_sequence}
        movies = [i for i in items if i.file_path.endswith(".mp4")]
        self.assertEqual(len(seqs), 2)
        self.assertTrue(all(m.is_hidden_paired_review for m in movies))
        self.assertTrue(seqs["beauty"].review_file_path.endswith(f"{self.B}_beauty.mp4"))
        self.assertTrue(seqs["deep"].review_file_path.endswith(f"_reviews/{self.B}.mp4"))
        self.assertTrue(seqs["beauty"].conversion_thumb_path.endswith(f"{self.B}_beauty_thumbnail.jpg"))
        beauty_movie = [m for m in movies if "beauty" in m.file_path][0]
        self.assertTrue(beauty_movie.conversion_thumb_path.endswith("_beauty_review_thumbnail.jpg"))
        # group-based pairing (everything in one group) must not overwrite name-based links
        pair_group_reviews(items)
        self.assertTrue(seqs["beauty"].review_file_path.endswith(f"{self.B}_beauty.mp4"))
        self.assertTrue(seqs["deep"].review_file_path.endswith(f"_reviews/{self.B}.mp4"))


if __name__ == "__main__":
    unittest.main()
