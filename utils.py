import os
import re
import fnmatch
from PySide6.QtGui import QPixmap, QImageReader, QColor
from PySide6.QtCore import Qt

def generate_placeholder_thumbnail(size=150, color="#444444"):
    """Generate a solid color placeholder pixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    return pixmap

def get_version_from_name(filename, pattern=r"([._]v|v)(\d+)"):
    """
    Extract version number from filename using regex.
    Default pattern handles: _v001, .v001, v001 (case insensitive)
    """
    match = re.search(pattern, filename, re.IGNORECASE)
    if match:
        # The digits are in the last capturing group
        return int(match.groups()[-1])
    return 1

def generate_thumbnail(image_path, size=150):
    """Generate a thumbnail pixmap for the given image path."""
    reader = QImageReader(image_path)
    if not reader.canRead():
        return None
    
    image_size = reader.size()
    image_size.scale(size, size, Qt.KeepAspectRatio)
    reader.setScaledSize(image_size)
    
    image = reader.read()
    if image.isNull():
        return None
        
    return QPixmap.fromImage(image)

def generate_video_thumbnail(video_path, ffmpeg_path, frame_mode="Middle", duration=None):
    """Generate a PNG thumbnail for a video file at the source path."""
    import subprocess
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return None
        
    out_path = video_path + "_thumbnail.png"
    
    # Calculate timestamp based on mode
    ss = "00:00:00"
    if frame_mode == "Second":
        ss = "00:00:01"
    elif frame_mode == "Middle" and duration:
        try:
            mid = float(duration) / 2.0
            ss = str(mid)
        except: pass
    
    args = [
        ffmpeg_path,
        "-ss", ss,
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y", out_path
    ]
    
    try:
        subprocess.run(args, capture_output=True, check=True)
        if os.path.exists(out_path):
            return out_path
    except Exception:
        pass
    return None

def get_all_files(directory, recursive=True):
    """Find all files in a directory."""
    files_found = []
    if recursive:
        for root, _, files in os.walk(directory):
            for file in files:
                files_found.append(os.path.join(root, file))
    else:
        for file in os.listdir(directory):
            full_path = os.path.join(directory, file)
            if os.path.isfile(full_path):
                files_found.append(full_path)
    return files_found

def strip_sequence_counter(filename):
    """Remove sequence counter (digits before extension) from filename."""
    # Matches name.0001.ext or name0001.ext
    base, ext = os.path.splitext(filename)
    match = re.search(r"(.*?)(\d+)$", base)
    if match:
        # If there's a dot before the numbers, strip it too
        base_name = match.group(1)
        if base_name.endswith("."):
            base_name = base_name[:-1]
        return base_name
    return base

def get_sequence_counter(filename):
    """Extract sequence counter (trailing digits before extension) from filename."""
    base, ext = os.path.splitext(filename)
    match = re.search(r"(\d+)$", base)
    if match:
        return match.group(1)
    return ""

def evaluate_preset(file_path, presets, p_type, label=None):
    """Evaluate which preset name matches the given file path."""
    p_list = presets.get(p_type, [])
    for p in p_list:
        f_by = p.get("Filter By", "Extension").lower()
        f_str = p.get("Filter", "").lower()
        if not f_str: continue
        
        if f_by == "extension":
            ext = os.path.splitext(file_path)[1].lower().lstrip(".")
            if fnmatch.fnmatch(ext, f_str): return p
        elif f_by == "name":
            # name excluding extension
            name = os.path.splitext(os.path.basename(file_path))[0].lower()
            if fnmatch.fnmatch(name, f_str): return p
        elif f_by == "path":
            # path excluding file name, use forward slashes
            path_dir = os.path.dirname(file_path).replace("\\", "/").lower()
            if fnmatch.fnmatch(path_dir, f_str): return p
        elif f_by == "label" and label:
            if fnmatch.fnmatch(label.lower(), f_str): return p
    return None
