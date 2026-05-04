import os
import time
import re
from PySide6.QtCore import QThread, Signal
from utils import get_all_files, get_version_from_name, generate_thumbnail, strip_sequence_counter, get_sequence_counter
from logic.image_model import ImageItem

class ImageScanner(QThread):
    progress = Signal(int, int) # current, total
    finished = Signal(list)
    canceled = Signal()

    def __init__(self, directory, recursive=True, version_regex="_v(\\d+)", 
                 thumbnail_size=150, age_source="Modification Date",
                 detect_sequences=True, seq_thumb_frame="Middle", 
                 extensions=None, presets=None):
        super().__init__()
        self.directory = directory
        self.recursive = recursive
        self.version_regex = version_regex
        self.thumbnail_size = thumbnail_size
        self.age_source = age_source
        self.detect_sequences = detect_sequences
        self.seq_thumb_frame = seq_thumb_frame
        self.extensions = extensions or {}
        self.presets = presets or {}
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    def run(self):
        if not os.path.exists(self.directory):
            self.finished.emit([])
            return

        all_files = get_all_files(self.directory, self.recursive)
        if not all_files:
            self.finished.emit([])
            return

        # Categorization logic (defaults if config is empty)
        def parse_exts(s, default):
            if not s: return default
            return {e.strip().lower() for e in s.split() if e.strip()}

        default_img = {".jpg", ".jpeg", ".png", ".tga", ".exr", ".dpx", ".psd"}
        default_vid = {".mov", ".mp4", ".mxf"}
        
        img_exts = parse_exts(self.extensions.get("stills"), default_img)
        # Merge sequence extensions into the same pool as they are both image groups
        img_exts.update(parse_exts(self.extensions.get("sequences"), set()))
        
        vid_exts = parse_exts(self.extensions.get("videos"), default_vid)
        other_exts = parse_exts(self.extensions.get("other"), set())
        
        groups = {} # (dir, base_name, ext, version) -> [file_paths]
        others = []
        videos = []

        for f in all_files:
            if self._is_canceled:
                self.canceled.emit()
                return

            ext = os.path.splitext(f)[1].lower()
            if ext in img_exts:
                directory = os.path.dirname(f)
                filename = os.path.basename(f)
                
                # 1. Extract version
                version = get_version_from_name(filename, self.version_regex)
                
                if self.detect_sequences:
                    # 2. Strip version from filename for further pattern matching
                    name_no_ver = re.sub(self.version_regex, "", filename)
                    # 3. Strip sequence counter
                    base_name = strip_sequence_counter(name_no_ver)
                    key = (directory, base_name, ext, version)
                else:
                    # If detection is off, every file gets its own unique key
                    key = (directory, filename, ext, version)
                
                if key not in groups:
                    groups[key] = []
                groups[key].append(f)
            elif ext in vid_exts:
                videos.append(f)
            elif ext in other_exts:
                others.append(f)
            # If extensions are defined for some categories, we skip everything else?
            # Actually, let's only skip if the user has defined ANY explicit lists.
            # Otherwise we keep the "default everything else is Other" behavior.
            elif not (img_exts or vid_exts or other_exts):
                others.append(f)

        # Process groups into items
        final_items = []
        
        # Total units to process (groups + videos + others)
        total_units = len(groups) + len(videos) + len(others)
        current = 0

        def match_preset(file_path, p_type):
            p_list = self.presets.get(p_type, [])
            for p in p_list:
                f_by = p.get("Filter By", "Extension").lower()
                f_str = p.get("Filter", "").lower()
                if not f_str: continue
                
                if f_by == "extension":
                    ext = os.path.splitext(file_path)[1].lower()
                    if f_str.startswith("."):
                        if ext == f_str: return p.get("Name")
                    else:
                        if ext == f".{f_str}": return p.get("Name")
                elif f_by == "name":
                    if f_str in os.path.basename(file_path).lower():
                        return p.get("Name")
                elif f_by == "path":
                    if f_str in file_path.lower():
                        return p.get("Name")
            return None

        # 1. Process Image Groups (Stills and Sequences)
        for key, paths in groups.items():
            if self._is_canceled:
                self.canceled.emit()
                return
            
            paths.sort()
            first_path = paths[0]
            directory, base_name, ext, version = key
            
            category = "Sequence" if len(paths) > 1 else "Still"
            
            # For sequences, label is the base name. For stills, use filename minus ext.
            if category == "Sequence":
                label = base_name
                # Calculate frame range
                first_name = os.path.basename(paths[0])
                last_name = os.path.basename(paths[-1])
                
                # Strip version from these names as well to ensure we get the right counter
                fn_no_ver = re.sub(self.version_regex, "", first_name)
                ln_no_ver = re.sub(self.version_regex, "", last_name)
                
                first_f = get_sequence_counter(fn_no_ver)
                last_f = get_sequence_counter(ln_no_ver)
                
                if first_f and last_f:
                    category = f"sequence[{first_f}-{last_f}]"
                
                # Determine path for metadata/thumbnail
                if self.seq_thumb_frame == "Middle":
                    source_path = paths[len(paths) // 2]
                elif self.seq_thumb_frame == "Second" and len(paths) > 1:
                    source_path = paths[1]
                else:
                    source_path = first_path
            else:
                label = os.path.splitext(os.path.basename(first_path))[0]
                source_path = first_path

            p_type = "sequences" if len(paths) > 1 else "stills"
            matched_preset = match_preset(first_path, p_type)

            item = ImageItem(source_path, label=label, version=version, category=category, preset_name=matched_preset)
            self._fill_metadata(item, source_path)
            
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        # 2. Process Videos
        for f in videos:
            if self._is_canceled:
                self.canceled.emit()
                return
            
            matched_preset = match_preset(f, "videos")
            item = ImageItem(f, category="Video", preset_name=matched_preset)
            self._fill_metadata(item, f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        # 3. Process Others
        for f in others:
            if self._is_canceled:
                self.canceled.emit()
                return
            
            matched_preset = match_preset(f, "other")
            item = ImageItem(f, category="Other", preset_name=matched_preset)
            self._fill_metadata(item, f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        self.finished.emit(final_items)

    def _fill_metadata(self, item, file_path):
        """Helper to fill common metadata for an item."""
        # Thumbnail
        item.thumbnail = generate_thumbnail(file_path, self.thumbnail_size)
        
        # Times
        try:
            item.modification_time = os.path.getmtime(file_path)
            item.creation_time = os.path.getctime(file_path)
            
            # Age
            source_time = item.modification_time if self.age_source == "Modification Date" else item.creation_time
            item.age_minutes = int((time.time() - source_time) / 60)
        except Exception:
            pass
