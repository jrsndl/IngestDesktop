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
    f"{R}/stills/a.png", f"{R}/stills/a.jpg", f"{R}/stills/b.png", f"{R}/stills/_thumbs/b.jpg",
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
        self.assertEqual(self.ix.thumbnail_for(f"{R}/stills/b.png"), f"{R}/stills/_thumbs/b.jpg")

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


class TestPairingOptions(unittest.TestCase):
    FILES = [f"{R}/sh/shot_v001.exr", f"{R}/sh/shot_v001_h264.mp4", f"{R}/sh/shot_v001.mp4",
             f"{R}/sh/shot_v0010.mp4", f"{R}/_review/shot_v001_review.mov"]

    def test_same_name_mode_ignores_suffixed(self):
        ix = PairIndex(self.FILES, R, ("_review",), name_mode="same", max_reviews=5)
        got = ix.reviews_for(f"{R}/sh/shot_v001.exr")
        self.assertEqual(got[0], f"{R}/sh/shot_v001.mp4")
        self.assertNotIn(f"{R}/sh/shot_v001_h264.mp4", got)
        self.assertNotIn(f"{R}/sh/shot_v0010.mp4", got)

    def test_suffix_mode_and_max(self):
        ix = PairIndex(self.FILES, R, ("_review",), name_mode="suffix", max_reviews=2)
        got = ix.reviews_for(f"{R}/sh/shot_v001.exr")
        # equal names first (same folder before other folder), suffixed after; max 2
        self.assertEqual(got, [f"{R}/sh/shot_v001.mp4", f"{R}/_review/shot_v001_review.mov"])
        ix3 = PairIndex(self.FILES, R, ("_review",), name_mode="suffix", max_reviews=3)
        self.assertIn(f"{R}/sh/shot_v001_h264.mp4", ix3.reviews_for(f"{R}/sh/shot_v001.exr"))
        self.assertNotIn(f"{R}/sh/shot_v0010.mp4", ix3.reviews_for(f"{R}/sh/shot_v001.exr"))

    def test_custom_review_folder_text(self):
        files = [f"{R}/sh/a.exr", f"{R}/movies/a.mp4"]
        self.assertIsNone(PairIndex(files, R).review_for(f"{R}/sh/a.exr"))
        self.assertEqual(PairIndex(files, R, review_word="movies").review_for(f"{R}/sh/a.exr"), f"{R}/movies/a.mp4")


class TestInheritance(unittest.TestCase):
    def test_fields_follow_main_and_revert_on_unpair(self):
        from logic.image_model import ImageItem, INHERITED_FIELDS, link_pairs_from_metadata
        from logic import tokens
        main = ImageItem("/j/sh010_v003.exr", version=3, variant="main", comment="a")
        rev = ImageItem("/j/sh010_v003.mp4", version=8, variant="rev", comment="r")
        main.pair_review(rev)
        main.ayon_path = "/p/sh010/plate"
        main.version_user = "5"
        main.variant_user = "hero"
        main.comment = "notes"
        main.last_ayon_version = 4
        for f in INHERITED_FIELDS:
            self.assertEqual(getattr(rev, f), getattr(main, f), f)
        rev.version = 99  # read-only while paired
        self.assertEqual(rev.version, 3)
        self.assertEqual(tokens.expand("{variant}", rev, None, False), tokens.expand("{variant}", main, None, False))
        self.assertIn(rev, main.paired_reviews)
        main.unpair_review(rev)
        self.assertEqual((rev.version, rev.variant, rev.comment, rev.ayon_path), (8, "rev", "r", ""))
        self.assertNotIn("paired_review_of", rev.metadata)
        # relink from metadata (project load / rescan)
        main.pair_review(rev)
        rev2 = ImageItem("/j/sh010_v003.mp4", metadata=dict(rev.metadata))
        main2 = ImageItem("/j/sh010_v003.exr", version=7)
        self.assertEqual(link_pairs_from_metadata([main2, rev2]), 1)
        self.assertIs(rev2.pair_main, main2)
        self.assertEqual(rev2.version, 7)

    def test_scanner_links_items_and_respects_unpaired(self):
        from logic.pairing import unpair_key
        tmp = tempfile.mkdtemp()
        orig = scanner_mod.generate_thumbnail_image
        orig_ph = getattr(scanner_mod, "generate_placeholder_thumbnail_image", None)
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None
        scanner_mod.generate_placeholder_thumbnail_image = lambda *a, **k: None
        try:
            for n in ["sh/a.1001.exr", "sh/a.1002.exr", "sh/a.mp4", "sh/b.exr", "sh/b.mp4"]:
                pth = os.path.join(tmp, n)
                os.makedirs(os.path.dirname(pth), exist_ok=True)
                with open(pth, "wb") as fh:
                    fh.write(b"x")
            cfg = {"unpaired_reviews": [unpair_key(os.path.join(tmp, "sh/b.exr"), os.path.join(tmp, "sh/b.mp4"))]}
            sc = ImageScanner(tmp, config=cfg)
            got = []

            class Cap:
                def emit(self, *a):
                    got.append(a)
            sc.finished = Cap()
            sc._fetch_metadata = lambda items: None
            sc._run()
            items = {os.path.basename(i.file_path): i for i in got[0][0]}
            seq = [i for i in got[0][0] if i.is_sequence][0]
            self.assertIs(items["a.mp4"].pair_main, seq)
            self.assertIsNone(items["b.mp4"].pair_main)   # unpaired by the user
        finally:
            scanner_mod.generate_thumbnail_image = orig
            if orig_ph is not None:
                scanner_mod.generate_placeholder_thumbnail_image = orig_ph
            shutil.rmtree(tmp, ignore_errors=True)


class TestUnpairMenu(unittest.TestCase):
    def test_pairs_of_main_and_review(self):
        from gui.pair_menu import pairs_of
        from logic.image_model import ImageItem
        m = ImageItem("/a/x.exr")
        r1, r2 = ImageItem("/a/x.mp4"), ImageItem("/a/x_h264.mp4")
        m.pair_review(r1)
        m.pair_review(r2)
        self.assertEqual(pairs_of([m, r1]), [(m, r1), (m, r2)])
        self.assertEqual(pairs_of([r2]), [(m, r2)])
        m.unpair_review(r1)
        self.assertEqual(m.review_file_path, "/a/x_h264.mp4")
        self.assertEqual(pairs_of([r1]), [])


class TestPairOrder(unittest.TestCase):
    def test_reviews_follow_their_main_row(self):
        from logic.image_model import ImageItem, ImageTableModel
        m = ImageTableModel()
        a, b = ImageItem("/x/a.exr", label="a"), ImageItem("/x/b.exr", label="b")
        ra, rb = ImageItem("/y/a.mp4", label="z_a"), ImageItem("/y/b.mp4", label="0_b")
        a.pair_review(ra)
        b.pair_review(rb)
        m.add_items([rb, b, ra, a])
        self.assertEqual([i.filename for i in m.items], ["b.exr", "b.mp4", "a.exr", "a.mp4"])
        m.sort(2)  # by label: reviews still right below their main file
        names = [i.filename for i in m.items]
        self.assertEqual(names.index("a.mp4"), names.index("a.exr") + 1)
        self.assertEqual(names.index("b.mp4"), names.index("b.exr") + 1)
        self.assertEqual(ra.pair_members(), [a, ra])


class TestEnableInheritance(unittest.TestCase):
    def test_enable_state_is_shared_by_the_pair(self):
        from logic.image_model import ImageItem
        main, rev = ImageItem("/j/a.exr"), ImageItem("/j/a.mp4")
        rev.is_tagged = False          # own value before pairing
        main.pair_review(rev)
        self.assertTrue(rev.is_tagged)  # follows the main file
        rev.is_tagged = False           # disabling the review disables the pair
        self.assertFalse(main.is_tagged)
        main.is_tagged = True
        self.assertTrue(rev.is_tagged)
        main.unpair_review(rev)
        self.assertFalse(rev.is_tagged)  # back to its own value

    def test_toggle_selection_toggles_each_pair_once(self):
        from logic.image_model import ImageItem, ImageTableModel
        m = ImageTableModel()
        main, rev = ImageItem("/j/a.exr"), ImageItem("/j/a.mp4")
        main.pair_review(rev)
        m.add_items([main, rev])

        class Row:
            def __init__(self, r):
                self._r = r

            def row(self):
                return self._r

        class Sel:
            def selectedRows(self):
                return [Row(0), Row(1)]
        m.toggle_tag_selection(Sel())
        self.assertFalse(main.is_tagged)
        self.assertFalse(rev.is_tagged)


class TestUnpairMenuShape(unittest.TestCase):
    class Menu:
        def __init__(self, title=""):
            self.title, self.subs, self.actions = title, [], []

        def addMenu(self, title):
            m = TestUnpairMenuShape.Menu(title)
            self.subs.append(m)
            return m

        def addAction(self, a):
            self.actions.append(a)

        def addSeparator(self):
            pass

    def test_submenu_within_one_pair_action_across_pairs(self):
        from gui.pair_menu import add_unpair_actions
        from logic.image_model import ImageItem
        a, ra = ImageItem("/j/a.exr"), ImageItem("/j/a.mp4")
        b, rb = ImageItem("/j/b.exr"), ImageItem("/j/b.mp4")
        a.pair_review(ra)
        b.pair_review(rb)
        one = self.Menu()
        self.assertTrue(add_unpair_actions(one, [a, ra], lambda p: None))
        self.assertEqual([m.title for m in one.subs], ["Unpair"])
        self.assertEqual(len(one.subs[0].actions), 1)
        both = self.Menu()
        self.assertTrue(add_unpair_actions(both, [a, ra, b, rb], lambda p: None))
        self.assertEqual(both.subs, [])
        self.assertEqual(len(both.actions), 1)
        self.assertFalse(add_unpair_actions(self.Menu(), [ImageItem("/j/c.exr")], lambda p: None))


class TestPairAgain(unittest.TestCase):
    def test_remembered_unpair_offers_pair(self):
        from gui.pair_menu import repair_candidates, add_pair_actions
        from logic.image_model import ImageItem
        from logic.pairing import unpair_key
        a, ra, b = ImageItem("/j/a.exr"), ImageItem("/j/a.mp4"), ImageItem("/j/b.exr")
        keys = [unpair_key(a.file_path, ra.file_path)]
        everything = [a, ra, b]
        self.assertEqual(repair_candidates([ra], everything, keys), [(a, ra)])
        self.assertEqual(repair_candidates([a], everything, keys), [(a, ra)])
        self.assertEqual(repair_candidates([b], everything, keys), [])
        self.assertEqual(repair_candidates([a], everything, []), [])
        menu = TestUnpairMenuShape.Menu()
        self.assertTrue(add_pair_actions(menu, [a], everything, keys, lambda p: None))
        self.assertEqual([m.title for m in menu.subs], ["Pair"])
        a.pair_review(ra)  # paired again: nothing to offer
        self.assertEqual(repair_candidates([a], everything, keys), [])


class TestSeveralReviews(unittest.TestCase):
    """Sequence with a movie next to it and another one in _reviews (boat_test layout)."""
    B = "DB_000_0030_lgt_explosion_v47"

    def _scan(self, cfg):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        B = self.B
        for n in [f"exr/beauty/{B}_beauty.1001.exr", f"exr/beauty/{B}_beauty.1002.exr",
                  f"exr/beauty/{B}_beauty.1003.exr", f"exr/beauty/{B}_beauty.mov",
                  f"_reviews/{B}_beauty.mp4"]:
            pth = os.path.join(tmp, n)
            os.makedirs(os.path.dirname(pth), exist_ok=True)
            with open(pth, "wb") as fh:
                fh.write(b"x")
        orig = scanner_mod.generate_thumbnail_image
        orig_ph = getattr(scanner_mod, "generate_placeholder_thumbnail_image", None)
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None
        scanner_mod.generate_placeholder_thumbnail_image = lambda *a, **k: None
        try:
            sc = ImageScanner(tmp, config=cfg(tmp) if callable(cfg) else cfg)
            got = []

            class Cap:
                def emit(self, *a):
                    got.append(a)
            sc.finished = Cap()
            sc._fetch_metadata = lambda items: None
            sc._run()
        finally:
            scanner_mod.generate_thumbnail_image = orig
            if orig_ph is not None:
                scanner_mod.generate_placeholder_thumbnail_image = orig_ph
        items = got[0][0]
        seq = [i for i in items if i.is_sequence][0]
        return tmp, seq, items

    def test_all_reviews_pair_up_to_the_maximum(self):
        _tmp, seq, _items = self._scan({"pair_max_reviews": 3})
        names = sorted(os.path.basename(r.file_path) for r in seq.paired_reviews)
        self.assertEqual(names, [f"{self.B}_beauty.mov", f"{self.B}_beauty.mp4"])
        _tmp, seq1, _items = self._scan({"pair_max_reviews": 1})
        self.assertEqual([os.path.basename(r.file_path) for r in seq1.paired_reviews], [f"{self.B}_beauty.mov"])

    def test_unpair_remembered_with_any_frame(self):
        from logic.pairing import unpair_key
        B = self.B

        def cfg(tmp):
            mid = os.path.join(tmp, f"exr/beauty/{B}_beauty.1002.exr")  # not the first frame
            return {"pair_max_reviews": 3,
                    "unpaired_reviews": [unpair_key(mid, os.path.join(tmp, f"_reviews/{B}_beauty.mp4"))]}
        _tmp, seq, _items = self._scan(cfg)
        self.assertEqual([os.path.basename(r.file_path) for r in seq.paired_reviews], [f"{B}_beauty.mov"])


class TestFootageId(unittest.TestCase):
    def test_any_frame_matches(self):
        from logic.pairing import footage_id, key_matches, unpair_key
        self.assertEqual(footage_id("D:/a/sh.1001.exr"), footage_id("D:/a/sh.1056.exr"))
        self.assertNotEqual(footage_id("D:/a/sh.1001.exr"), footage_id("D:/b/sh.1001.exr"))
        self.assertNotEqual(footage_id("D:/a/sh_v001.exr"), footage_id("D:/a/sh_v002.exr"))
        k = unpair_key("D:/a/sh.1056.exr", "D:/r/sh.mp4")
        self.assertTrue(key_matches(k, "D:/a/sh.1001.exr", "D:/r/sh.mp4"))
        self.assertFalse(key_matches(k, "D:/a/sh.1001.exr", "D:/r/other.mp4"))


class TestGroupPairingKeepsOwnMovie(unittest.TestCase):
    def test_paired_reviews_keep_their_own_movie(self):
        from logic.grouping_engine import pair_group_reviews
        from logic.image_model import ImageItem
        a, b = ImageItem("/j/a.1001.exr", category="Sequence"), ImageItem("/j/b.1001.exr", category="Sequence")
        ra, rb = ImageItem("/j/a.mp4", category="Video"), ImageItem("/j/b.mp4", category="Video")
        a.pair_review(ra)
        b.pair_review(rb)
        pair_group_reviews([a, b, ra, rb], {})  # all in one group
        self.assertEqual(ra.review_file_path, "/j/a.mp4")
        self.assertEqual(rb.review_file_path, "/j/b.mp4")
        self.assertEqual(a.review_file_path, "/j/a.mp4")
        self.assertEqual(b.review_file_path, "/j/b.mp4")


class TestPairAsMain(unittest.TestCase):
    def test_menu_lists_selected_rows(self):
        from gui.pair_menu import add_pair_as_main_actions
        from logic.image_model import ImageItem
        a, b, c = ImageItem("/j/a.mov"), ImageItem("/j/a.mp4"), ImageItem("/j/a_h264.mp4")
        got = []
        menu = TestUnpairMenuShape.Menu()
        self.assertTrue(add_pair_as_main_actions(menu, [a, b, c], got.append))
        self.assertEqual([m.title for m in menu.subs], ["Pair as main"])
        self.assertEqual(len(menu.subs[0].actions), 3)
        self.assertFalse(add_pair_as_main_actions(TestUnpairMenuShape.Menu(), [a], got.append))

    def test_scan_applies_manual_pairs(self):
        from logic.pairing import unpair_key
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for n in ["sh/shot.mov", "_review/shot.mp4"]:
            pth = os.path.join(tmp, n)
            os.makedirs(os.path.dirname(pth), exist_ok=True)
            with open(pth, "wb") as fh:
                fh.write(b"x")
        mov, mp4 = os.path.join(tmp, "sh/shot.mov"), os.path.join(tmp, "_review/shot.mp4")
        orig = scanner_mod.generate_thumbnail_image
        orig_ph = getattr(scanner_mod, "generate_placeholder_thumbnail_image", None)
        scanner_mod.generate_thumbnail_image = lambda *a, **k: None
        scanner_mod.generate_placeholder_thumbnail_image = lambda *a, **k: None
        try:
            # by the rules the .mov is the main file; by hand the .mp4 is
            sc = ImageScanner(tmp, config={"manual_pairs": [unpair_key(mp4, mov)]})
            got = []

            class Cap:
                def emit(self, *a):
                    got.append(a)
            sc.finished = Cap()
            sc._fetch_metadata = lambda items: None
            sc._run()
        finally:
            scanner_mod.generate_thumbnail_image = orig
            if orig_ph is not None:
                scanner_mod.generate_placeholder_thumbnail_image = orig_ph
        items = {os.path.basename(i.file_path): i for i in got[0][0]}
        self.assertIs(items["shot.mov"].pair_main, items["shot.mp4"])
        self.assertIsNone(items["shot.mp4"].pair_main)


if __name__ == "__main__":
    unittest.main()
