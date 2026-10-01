"""Where generated thumbnails and review movies live (pure Python, no Qt).

Single source of truth for the scanner, the Qt model ({prefs_thumb_path},
{prefs_review_path} tokens) and the conversion workers.
"""
import os

from logic.seqparse import split_name


def _fwd(p):
    return p.replace("\\", "/") if p else p


def _name_stem(file_path, is_sequence):
    name = os.path.basename(file_path)
    if is_sequence:
        return split_name(name, None).base.rstrip("._")
    return os.path.splitext(name)[0]


def thumb_path(file_path, is_sequence, source_folder, location="Relative to Source Folder",
               location_path="_thumbs", suffix="_thumbnail", fmt=".jpg"):
    base_dir = os.path.dirname(_fwd(file_path))
    target_dir = base_dir
    if location == "Relative to Source Folder":
        if source_folder:
            target_dir = os.path.join(source_folder, location_path)
    elif location == "Custom":
        target_dir = location_path
    return _fwd(os.path.join(target_dir, f"{_name_stem(file_path, is_sequence)}{suffix}{fmt}"))


def review_path(file_path, is_sequence, source_folder, preset=None):
    p = preset or {}
    loc = p.get("Review Location", "Relative to Source Folder")
    rel = p.get("Review Path", "_reviews")
    suffix = p.get("Review Suffix", "_review")
    fmt = p.get("Review Format", ".mp4")
    base_dir = os.path.dirname(_fwd(file_path))
    target_dir = base_dir
    if loc == "Relative to Source Folder":
        target_dir = os.path.join(source_folder or base_dir, rel)
    elif loc == "Custom":
        target_dir = rel
    return _fwd(os.path.abspath(os.path.join(target_dir, f"{_name_stem(file_path, is_sequence)}{suffix}{fmt}")))


def existing_file(path):
    try:
        return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def find_existing_review(file_path, is_sequence, source_folder, preset=None):
    """Expected review path if it exists, else a same-folder sidecar movie, else None.

    Only the item's own folder and the configured review folder are searched, so a
    movie with the same name in another shot folder is never picked up.
    """
    expected = review_path(file_path, is_sequence, source_folder, preset)
    if existing_file(expected):
        return expected
    stem = _name_stem(file_path, is_sequence)
    p = preset or {}
    for folder in {os.path.dirname(file_path), os.path.dirname(expected)}:
        for cand in (f"{stem}{p.get('Review Suffix', '_review')}{p.get('Review Format', '.mp4')}",
                     f"{stem}_review.mp4", f"{stem}_review.mov", f"{stem}.mp4", f"{stem}.mov"):
            cp = os.path.join(folder, cand)
            if existing_file(cp):
                return _fwd(cp)
    return None
