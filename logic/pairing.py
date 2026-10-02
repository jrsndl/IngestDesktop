"""Pair footage with thumbnails and review movies that already exist on disk.

Rules (applied when a folder is scanned; options in Preferences > Pairing)
---------------------------------------------------------------------------
Names are compared without extension, without the frame counter of a
sequence and without thumbnail/review suffixes ("_thumbnail", "_thumb",
"_review", "_preview" and the suffixes set in Preferences), case-insensitively.

Name match ("pair_name_mode"):
  "same"    the names must be equal.
  "suffix"  the candidate may add a suffix after the footage name, starting with
            "_", "-" or "." (shot_v001 + shot_v001_h264.mp4); equal names win.

1. Same name, same folder            -> pair.
2. Same name, different folder       -> pair only if the candidate's path
   (relative to the scanned folder, file name included) contains the
   "Thumbnails folder" text (default "_thumb") for thumbnails or the
   "Reviews folder" text (default "_review") for reviews. Case is ignored,
   so "_review" also matches "_reviews".

What can be paired
------------------
* Thumbnail candidates: single image files in a light format (jpg, png, ...).
  Footage that is itself such an image only pairs with a candidate that is
  clearly a thumbnail (path contains the thumbnails folder text), so plate.png
  and plate.jpg next to each other stay two separate items.
* Review candidates: movie files. Movie footage only pairs with a candidate
  that is clearly a review (path contains the reviews folder text).
* Up to "pair_max_reviews" reviews per footage (default 1); the closest win:
  equal name first, then same folder, then the shortest path.
* A file used as a thumbnail is not an item at all.
* A paired review movie stays in the model (it is published with its footage)
  and inherits the footage's AYON path, variant(s), version(s), last version and
  comment (logic/image_model.py, INHERITED_FIELDS). It is shown as its own
  item only where "Show Reviews" is on. Name-based links win over the
  group-based review pairing (grouping_engine.pair_group_reviews).
* A review movie prefers its own "<name>_review_thumbnail" over the footage one.
"""
import bisect
import os

from logic.seqparse import split_name

THUMB_WORD = "_thumb"
REVIEW_WORD = "_review"
LIGHT_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mxf", ".mpg", ".mpeg", ".wmv"}
DEFAULT_SUFFIXES = ("_thumbnail", "_thumb", "-thumbnail", "-thumb", ".thumb",
                    "_review", "-review", ".review", "_preview", "-preview")
SUFFIX_SEPARATORS = "._-"


def _norm_path(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p))).replace("\\", "/")


def unpair_key(footage_path, review_path):
    """How a user's "Unpair" is remembered (config "unpaired_reviews")."""
    return f"{_norm_path(footage_path)}|{_norm_path(review_path)}"


def footage_id(path):
    """Identity of a file for remembered unpairs: folder + name without the frame
    counter, so every frame of a sequence is the same footage."""
    p = _norm_path(path)
    d, name = p.rsplit("/", 1) if "/" in p else ("", p)
    parts = split_name(name, None)
    return f"{d}/{parts.base}{parts.ext}"


def key_matches(key, footage_path, review_path):
    """Does a remembered unpair key cover this footage (any frame) and review?"""
    if not isinstance(key, str) or "|" not in key:
        return False
    f_key, r_key = key.split("|", 1)
    return r_key == _norm_path(review_path) and footage_id(f_key) == footage_id(footage_path)


def unpaired_set(entries):
    return {e for e in (entries or []) if isinstance(e, str) and "|" in e}


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

    def __init__(self, all_files, root, extra_suffixes=(), name_mode="same",
                 review_word=REVIEW_WORD, thumb_word=THUMB_WORD, max_reviews=1):
        self.root = os.path.normcase(os.path.normpath(os.path.abspath(root))) if root else ""
        self.suffixes = tuple(s for s in extra_suffixes if s) + DEFAULT_SUFFIXES
        self.name_mode = "suffix" if str(name_mode).lower().startswith("suffix") else "same"
        self.review_word = (review_word or REVIEW_WORD).lower()
        self.thumb_word = (thumb_word or THUMB_WORD).lower()
        try:
            self.max_reviews = max(1, int(max_reviews))
        except (TypeError, ValueError):
            self.max_reviews = 1
        self.thumbs = {}   # stem -> [paths]
        self.reviews = {}  # stem -> [paths]
        for f in all_files:
            ext = os.path.splitext(f)[1].lower()
            stem = os.path.splitext(os.path.basename(f))[0]
            if ext in LIGHT_IMAGE_EXTS:
                # a numbered image belongs to a sequence, not a single thumbnail
                if split_name(f, None).frame is not None and not self._has_word(f, self.thumb_word):
                    continue
                self.thumbs.setdefault(strip_suffixes(stem, self.suffixes).lower(), []).append(f)
            elif ext in VIDEO_EXTS:
                self.reviews.setdefault(strip_suffixes(stem, self.suffixes).lower(), []).append(f)
        self._thumb_keys = sorted(self.thumbs)
        self._review_keys = sorted(self.reviews)

    def _rel(self, path):
        p = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        if self.root and (p == self.root or p.startswith(self.root + os.sep)):
            return p[len(self.root):]
        return p

    def _has_word(self, path, word):
        return bool(word) and word in self._rel(path).lower()

    def _candidates(self, table, keys, stem):
        """(path, exact_name) for every candidate whose name matches `stem`."""
        out = [(c, True) for c in table.get(stem, [])]
        if self.name_mode == "suffix" and stem:
            i = bisect.bisect_left(keys, stem)
            while i < len(keys) and keys[i].startswith(stem):
                k = keys[i]
                if len(k) > len(stem) and k[len(stem)] in SUFFIX_SEPARATORS:
                    out += [(c, False) for c in table[k]]
                i += 1
        return out

    def _pick(self, table, keys, footage_path, stem, word, require_word, prefer_review=False, limit=1):
        me = os.path.normcase(os.path.abspath(footage_path))
        cands = [(c, exact) for c, exact in self._candidates(table, keys, stem)
                 if os.path.normcase(os.path.abspath(c)) != me]
        if not cands:
            return []
        fdir = _norm_dir(footage_path)

        def ok(c):
            if _norm_dir(c) == fdir:
                return not require_word or self._has_word(c, word)
            return self._has_word(c, word)

        def rank(ce):
            c, exact = ce
            # a review movie prefers "<name>_review_thumbnail", footage prefers the plain one
            has_rev = self.review_word in os.path.basename(c).lower()
            return (not exact, _norm_dir(c) != fdir, has_rev != prefer_review, len(self._rel(c)), c)

        return [c for c, _ in sorted((ce for ce in cands if ok(ce[0])), key=rank)][:limit]

    def thumbnail_for(self, footage_path, is_sequence=False):
        ext = os.path.splitext(footage_path)[1].lower()
        light_footage = (ext in LIGHT_IMAGE_EXTS) and not is_sequence
        is_review_movie = ext in VIDEO_EXTS and self._has_word(footage_path, self.review_word)
        found = self._pick(self.thumbs, self._thumb_keys, footage_path, footage_stem(footage_path, is_sequence),
                           self.thumb_word, require_word=light_footage, prefer_review=is_review_movie)
        return found[0] if found else None

    def reviews_for(self, footage_path, is_sequence=False):
        """Up to max_reviews review movies for the footage, best first."""
        ext = os.path.splitext(footage_path)[1].lower()
        return self._pick(self.reviews, self._review_keys, footage_path, footage_stem(footage_path, is_sequence),
                          self.review_word, require_word=(ext in VIDEO_EXTS), limit=self.max_reviews)

    def review_for(self, footage_path, is_sequence=False):
        found = self.reviews_for(footage_path, is_sequence)
        return found[0] if found else None
