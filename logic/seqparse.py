"""File-name parsing for image sequences and versions (pure Python, no Qt).

Rules
-----
* The version is found with the user's version regex on the ORIGINAL file name.
  The number is the last capture group that matched (or the digits of the whole
  match when the regex has no group), so `_v(\\d+)`, `([._]v|v)(\\d+)` and
  `_v\\d+` all work.
* A frame counter is the trailing number of the name (before the extension):
    - separated by "." or "_"  (shot.1001.exr, shot_1001.exr, shot.-001.exr), or
    - glued to the name only when it has 4+ digits (render0001.exr)
  and it must come AFTER the version, never overlap it. So `sh010_v001.exr`
  has no frame counter (the trailing 001 is the version) and stays a still.
* Frames are compared as integers; padding is kept for display/paths.
"""
import os
import re
from collections import namedtuple

NameParts = namedtuple("NameParts", "stem ext version frame frame_str pad base label")
# stem      : name without extension
# version   : int or None
# frame     : int or None (frame counter)
# frame_str : the counter as written ("0101", "-001") or ""
# pad       : number of digits in the counter (0 if none)
# base      : stem without the frame counter (and its separator) - sequence key
# label     : base without the version text, trailing "._- " trimmed

_FRAME_SEP_RE = re.compile(r"(?P<sep>[._])(?P<num>-?\d+)$")
_FRAME_GLUED_RE = re.compile(r"(?<=[A-Za-z])(?P<num>\d{4,})$")


def _version_match(stem, version_regex):
    if not version_regex:
        return None
    try:
        matches = list(re.finditer(version_regex, stem, re.IGNORECASE))
    except re.error:
        return None
    return matches[-1] if matches else None


def version_from_match(m):
    if not m:
        return None
    text = None
    if m.lastindex:
        # last group that actually matched
        for gi in range(m.lastindex, 0, -1):
            if m.group(gi) is not None and re.search(r"\d", m.group(gi)):
                text = m.group(gi)
                break
    if text is None:
        text = m.group(0)
    d = re.search(r"\d+", text)
    return int(d.group(0)) if d else None


def parse_version(name, version_regex, default=1):
    """Version number from a file name; `default` when none is found."""
    stem = os.path.splitext(os.path.basename(name))[0]
    v = version_from_match(_version_match(stem, version_regex))
    return default if v is None else v


def split_name(filename, version_regex=r"([._]v|v)(\d+)"):
    name = os.path.basename(filename)
    stem, ext = os.path.splitext(name)
    vm = _version_match(stem, version_regex)
    version = version_from_match(vm)

    frame = None
    frame_str = ""
    base = stem
    m = _FRAME_SEP_RE.search(stem)
    if m and m.group("num").startswith("-") and m.group("sep") != ".":
        m = None
    start = m.start() if m else None
    num = m.group("num") if m else None
    if not m:
        g = _FRAME_GLUED_RE.search(stem)
        if g:
            start, num = g.start(), g.group("num")
    if num is not None:
        num_start = stem.rfind(num)
        if vm is None or num_start >= vm.end():
            frame_str = num
            frame = int(num)
            base = stem[:start]

    label_src = base
    if vm is not None and vm.end() <= len(base):
        label_src = base[:vm.start()] + base[vm.end():]
    label = label_src.rstrip("._- ") or base or stem
    pad = len(frame_str.lstrip("-")) if frame_str else 0
    return NameParts(stem, ext, version, frame, frame_str, pad, base, label)


def frame_range_info(frames):
    """(first, last, missing_count, missing_list_preview) for a list of ints."""
    if not frames:
        return None, None, 0, []
    fs = sorted(set(frames))
    first, last = fs[0], fs[-1]
    present = set(fs)
    missing = [f for f in range(first, last + 1) if f not in present] if last - first < 1000000 else []
    return first, last, len(missing), missing[:20]


def format_frame(n, pad):
    if n is None:
        return ""
    if n < 0:
        return "-" + str(-n).zfill(pad)
    return str(n).zfill(pad)
