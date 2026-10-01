"""Pair footage with thumbnails and review movies that already exist on disk.

Rules (applied when a folder is scanned)
----------------------------------------
Names are compared without extension, without the frame counter of a
sequence and without thumbnail/review suffixes ("_thumbnail", "_thumb",
"_review", "_preview" and the suffixes set in Preferences), case-insensitively.

1. Same name, same folder            -> pair.
2. Same name, different folder       -> pair only if the candidate's path
   (relative to the scanned folder, file name included) contains "thumb"
   (for thumbnails) or "review" (for reviews).

What can be paired
------------------
* Thumbnail candidates: single image files in a light format (jpg, png, ...).
  Footage that is itself such an image only pairs with a candidate that is
  clearly a thumbnail (name or folder contains "thumb"), so plate.png and
  plate.jpg next to each other stay two separate items.
* Review candidates: movie files. Movie footage only pairs with a candidate
  that is clearly a review (name or folder contains "review").
* A file used as a thumbnail is not an item at all.
* A paired review movie stays in the model (so the CSV still publishes it with
  its footage) but is marked `paired_review_of` and is not shown as its own item
  in the canvas or the right panel. Name-based links win over the group-based
  review pairing (grouping_engine.pair_group_reviews).
* A review movie prefers its own "<name>_review_thumbnail" over the footage one.
"""
import os

from logic.seqparse import split_name

THUMB_WORD = "thumb"
REVIEW_WORD = "review"
LIGHT_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mxf", ".mpg", ".mpeg", ".wmv"}
DEFAULT_SUFFIXES = ("_thumbnail", "_thumb", "-thumbnail", "-thumb", ".thumb",
                    "_review", "-review", ".review", "_preview", "-preview")


def _norm_dir(p):
    return os.path.normcase(os.path.normpath(os.path.dirname(os.path.abspath(p))))


def strip_suffixes(stem, suffixes):
    s = stem
    changed = True
    while changed:
        changed = False
        for suf in suffixes:
            if suf and s.lower().endswith(suf.lower()) and len(s) > len(suf):
                s = s[: -len(suf)]
                changed = True
    return s.rstrip("._- ")


def footage_stem(path, is_sequence=False):
    name = os.path.basename(path)
    if is_sequence:
        return split_name(name, None).base.rstrip("._- ").lower()
    return os.path.splitext(name)[0].lower()


class PairIndex:
    """Index of every file found by the scan, by comparable name."""

    def __init__(self, all_files, root, extra_suffixes=()):
        self.root = os.path.normcase(os.path.normpath(os.path.abspath(root))) if root else ""
        self.suffixes = tuple(s for s in extra_suffixes if s) + DEFAULT_SUFFIXES
        self.thumbs = {}   # stem -> [paths]
        self.reviews = {}  # stem -> [paths]
        for f in all_files:
            ext = os.path.splitext(f)[1].lower()
            stem = os.path.splitext(os.path.basename(f))[0]
            if ext in LIGHT_IMAGE_EXTS:
                # a numbered image belongs to a sequence, not a single thumbnail
                if split_name(f, None).frame is not None and not self._has_word(f, THUMB_WORD):
                    continue
                self.thumbs.setdefault(strip_suffixes(stem, self.suffixes).lower(), []).append(f)
            elif ext in VIDEO_EXTS:
                self.reviews.setdefault(strip_suffixes(stem, self.suffixes).lower(), []).append(f)

    def _rel(self, path):
        p = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        if self.root and (p == self.root or p.startswith(self.root + os.sep)):
            return p[len(self.root):]
        return p

    def _has_word(self, path, word):
        return word in self._rel(path).lower()

    def _pick(self, table, footage_path, stem, word, require_word, prefer_review=False):
        cands = [c for c in table.get(stem, [])
                 if os.path.normcase(os.path.abspath(c)) != os.path.normcase(os.path.abspath(footage_path))]
        if not cands:
            return None

        def rank(c):
            # a review movie prefers "<name>_review_thumbnail", footage prefers the plain one
            has_rev = REVIEW_WORD in os.path.basename(c).lower()
            return (has_rev != prefer_review, len(self._rel(c)), c)

        fdir = _norm_dir(footage_path)
        same = sorted((c for c in cands if _norm_dir(c) == fdir and (not require_word or self._has_word(c, word))),
                      key=rank)
        if same:
            return same[0]
        other = sorted((c for c in cands if _norm_dir(c) != fdir and self._has_word(c, word)), key=rank)
        return other[0] if other else None

    def thumbnail_for(self, footage_path, is_sequence=False):
        ext = os.path.splitext(footage_path)[1].lower()
        light_footage = (ext in LIGHT_IMAGE_EXTS) and not is_sequence
        is_review_movie = ext in VIDEO_EXTS and self._has_word(footage_path, REVIEW_WORD)
        return self._pick(self.thumbs, footage_path, footage_stem(footage_path, is_sequence),
                          THUMB_WORD, require_word=light_footage, prefer_review=is_review_movie)

    def review_for(self, footage_path, is_sequence=False):
        ext = os.path.splitext(footage_path)[1].lower()
        return self._pick(self.reviews, footage_path, footage_stem(footage_path, is_sequence),
                          REVIEW_WORD, require_word=(ext in VIDEO_EXTS))
