import os
import re
from PySide6.QtGui import QPixmap, QImageReader
from PySide6.QtCore import Qt

def get_version_from_name(filename, pattern=r"_v(\d+)"):
    """Extract version number from filename using regex."""
    match = re.search(pattern, filename)
    if match:
        return int(match.group(1))
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
