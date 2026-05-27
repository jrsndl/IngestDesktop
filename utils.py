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

def generate_placeholder_thumbnail_image(size=150, color="#444444"):
    """Generate a solid color placeholder QImage."""
    from PySide6.QtGui import QImage
    image = QImage(size, size, QImage.Format_RGB32)
    image.fill(QColor(color))
    return image

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

def generate_thumbnail_image(image_path, size=150):
    """Generate a scaled QImage for the given image path."""
    import time
    start_time = time.perf_counter()
    print(f"[Timer] Starting to read thumbnail image for {os.path.basename(image_path)}...")
    reader = QImageReader(image_path)
    if not reader.canRead():
        return None
    
    image_size = reader.size()
    image_size.scale(size, size, Qt.KeepAspectRatio)
    reader.setScaledSize(image_size)
    
    image = reader.read()
    if image.isNull():
        return None
        
    elapsed = time.perf_counter() - start_time
    print(f"[Timer] Reading thumbnail image for {os.path.basename(image_path)} took {elapsed:.4f} seconds.")
    return image

def generate_thumbnail(image_path, size=150):
    """Generate a thumbnail pixmap for the given image path."""
    import time
    start_time = time.perf_counter()
    print(f"[Timer] Starting to generate thumbnail pixmap for {os.path.basename(image_path)}...")
    image = generate_thumbnail_image(image_path, size)
    if not image or image.isNull():
        return None
        
    pixmap = QPixmap.fromImage(image)
    elapsed = time.perf_counter() - start_time
    print(f"[Timer] Generating thumbnail pixmap for {os.path.basename(image_path)} took {elapsed:.4f} seconds.")
    return pixmap

def generate_video_thumbnail(video_path, ffmpeg_path, frame_mode="Middle", duration=None, out_path=None):
    """Generate a PNG/JPG thumbnail for a video file at the source path."""
    import subprocess
    import time
    print(f"[Timer] Starting to generate video thumbnail for {os.path.basename(video_path)}...")
    start_time = time.perf_counter()
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return None
        
    if not out_path:
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
    
    # Hide window on Windows
    creationflags = 0
    if os.name == 'nt':
        creationflags = 0x08000000 # subprocess.CREATE_NO_WINDOW

    try:
        subprocess.run(args, capture_output=True, check=True, creationflags=creationflags)
        elapsed = time.perf_counter() - start_time
        print(f"[Timer] Generating video thumbnail for {os.path.basename(video_path)} took {elapsed:.4f} seconds.")
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
    if ext and re.match(r"^\.\d+$", ext):
        # Numeric extension (e.g. .1001), treat as part of sequence counter
        base = filename
    match = re.search(r"(.*?)(\d+)$", base)
    if match:
        # If there's a dot or underscore before the numbers, strip it too
        base_name = match.group(1)
        while base_name.endswith(".") or base_name.endswith("_"):
            base_name = base_name[:-1]
        return base_name
    return base

def get_sequence_counter(filename):
    """Extract sequence counter (trailing digits before extension) from filename."""
    base, ext = os.path.splitext(filename)
    if ext and re.match(r"^\.\d+$", ext):
        # Numeric extension (e.g. .1001), treat as part of sequence counter
        base = filename
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

def calculate_thumbnail_time(nb_frames, framerate, mode="Middle"):
    """
    Calculate the time in seconds for thumbnail extraction.
    mode: First, Second, Middle
    """
    try:
        nb_frames = int(nb_frames)
        # Default to 24 fps if missing or zero
        fps = float(framerate) if (framerate and float(framerate) > 0) else 24.0
    except (ValueError, TypeError):
        fps = 24.0
        nb_frames = 1

    if mode == "First":
        target_frame = 0
    elif mode == "Second" and nb_frames > 1:
        target_frame = 1
    elif mode == "Middle":
        target_frame = max(0, (nb_frames - 1) // 2) if nb_frames > 0 else 0
    else:
        target_frame = 0

    # User's specific formula implementation
    hours = int(target_frame / 3600 / fps)
    minutes = int((target_frame - hours * 3600 * fps) / 60 / fps)
    seconds = int((target_frame - (hours * 3600 * fps) - (minutes * 60 * fps)) / fps)
    rem_frames = int(target_frame - (hours * 3600 * fps) - (minutes * 60 * fps) - (seconds * fps))
    
    ms_per_frame = 1000.0 / fps
    miliseconds = rem_frames * ms_per_frame
    
    total_seconds = float(hours * 3600 + minutes * 60 + seconds) + float(0.001 * miliseconds)
    return total_seconds

import sys
_ENV_CACHE = dict(os.environ)
if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    resource_dir = getattr(sys, '_MEIPASS', app_dir)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))
    resource_dir = app_dir

_ENV_CACHE["IngestDesktop"] = app_dir
_ENV_CACHE["IngestDesktopResources"] = resource_dir

def expand_env_vars(path_str):
    """
    Expand environment variables present as ${variable_name}.
    If the variable is not found in the environment, it is replaced by an empty string.
    The environment variables are cached at app start for speedup.
    """
    if not path_str or not isinstance(path_str, str):
        return path_str
        
    def replacer(match):
        var_name = match.group(1)
        return _ENV_CACHE.get(var_name, "")
        
    return re.sub(r'\$\{([^}]+)\}', replacer, path_str)
