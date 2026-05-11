import os
import time
import re
import fnmatch
from PySide6.QtCore import QThread, Signal
from utils import (get_all_files, get_version_from_name, generate_thumbnail, 
                   generate_video_thumbnail, generate_placeholder_thumbnail,
                   strip_sequence_counter, get_sequence_counter, evaluate_preset)
from logic.image_model import ImageItem
from logic.metadata import get_image_info_metadata

class ImageScanner(QThread):
    progress = Signal(int, int) # current, total
    finished = Signal(list)
    item_updated = Signal(object)
    canceled = Signal()

    def __init__(self, directory, recursive=True, version_regex="_v(\\d+)", 
                 thumbnail_size=150, age_source="Modification Date",
                 detect_sequences=True, seq_thumb_frame="Middle", 
                 extensions=None, presets=None,
                 stills_start_frame=1001, stills_end_frame=1001,
                 video_start_from_tc=False, video_start_frame=1001,
                 ffmpeg_path="ffmpeg.exe", ffprobe_path="ffprobe.exe",
                 oiiotool_path="oiiotool.exe", ocio_config="", stills_thumb_same=True):
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
        self.stills_start_frame = stills_start_frame
        self.stills_end_frame = stills_end_frame
        self.video_start_from_tc = video_start_from_tc
        self.video_start_frame = video_start_frame
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.oiiotool_path = oiiotool_path
        self.ocio_config = ocio_config
        self.stills_thumb_same = stills_thumb_same
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

            # Completely ignore generated thumbnails
            if f.lower().endswith("_thumbnail.png"):
                continue

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
                first_f = self.stills_start_frame
                last_f = self.stills_end_frame

            p_type = "sequences" if len(paths) > 1 else "stills"
            is_seq = (len(paths) > 1)
            matched_p = evaluate_preset(first_path, self.presets, p_type, label=label)
            preset_name = matched_p.get("Name") if matched_p else None
            variant = matched_p.get("Variant") if matched_p else None
            product_type = matched_p.get("Product Type") if matched_p else None
            camel_case = matched_p.get("CamelCase", True) if matched_p else True
            representation = matched_p.get("Representation", "{extension}") if matched_p else "{extension}"
            colorspace = matched_p.get("Colorspace", "sRGB") if matched_p else "sRGB"
            rep_tags = matched_p.get("Tags", "passing") if matched_p else "passing"
            
            item = ImageItem(source_path, label=label, version=version, category=category, 
                             preset_name=preset_name, variant=variant, product_type=product_type, camel_case=camel_case,
                             representation=representation, colorspace=colorspace, rep_tags=rep_tags, is_sequence=is_seq,
                             preset_data=matched_p, frame_start=first_f, frame_end=last_f)
            self._fill_metadata(item, source_path)
            
            # Save ref for metadata extraction later
            item._meta_source = first_path
            
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        # 2. Process Videos
        for f in videos:
            if self._is_canceled:
                self.canceled.emit()
                return
            
            matched_p = evaluate_preset(f, self.presets, "videos", label=os.path.splitext(os.path.basename(f))[0])
            preset_name = matched_p.get("Name") if matched_p else None
            variant = matched_p.get("Variant") if matched_p else None
            product_type = matched_p.get("Product Type") if matched_p else None
            camel_case = matched_p.get("CamelCase", True) if matched_p else True
            representation = matched_p.get("Representation", "{extension}") if matched_p else "{extension}"
            colorspace = matched_p.get("Colorspace", "sRGB") if matched_p else "sRGB"
            rep_tags = matched_p.get("Tags", "passing") if matched_p else "passing"
            
            start_f = self.video_start_frame
            item = ImageItem(f, category="Video", preset_name=preset_name, variant=variant, product_type=product_type, camel_case=camel_case,
                             representation=representation, colorspace=colorspace, rep_tags=rep_tags,
                             preset_data=matched_p, frame_start=start_f, frame_end=start_f)
            self._fill_metadata(item, f)
            
            # Save ref for metadata extraction later
            item._meta_source = f
            item._video_start_from_tc = self.video_start_from_tc
            item._video_default_start = self.video_start_frame

            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        # 3. Process Others
        for f in others:
            if self._is_canceled:
                self.canceled.emit()
                return
            
            matched_p = evaluate_preset(f, self.presets, "other", label=os.path.splitext(os.path.basename(f))[0])
            preset_name = matched_p.get("Name") if matched_p else None
            variant = matched_p.get("Variant") if matched_p else None
            product_type = matched_p.get("Product Type") if matched_p else None
            camel_case = matched_p.get("CamelCase", True) if matched_p else True
            representation = matched_p.get("Representation", "{extension}") if matched_p else "{extension}"
            colorspace = matched_p.get("Colorspace", "sRGB") if matched_p else "sRGB"
            rep_tags = matched_p.get("Tags", "passing") if matched_p else "passing"
            item = ImageItem(f, category="Other", preset_name=preset_name, variant=variant, product_type=product_type, camel_case=camel_case,
                             representation=representation, colorspace=colorspace, rep_tags=rep_tags,
                             preset_data=matched_p)
            self._fill_metadata(item, f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        self.finished.emit(final_items)
        
        # --- Phase 2: Async Metadata Extraction ---
        from concurrent.futures import ThreadPoolExecutor
        
        # Filter items that actually need metadata (sequences and videos)
        meta_queue = [item for item in final_items if hasattr(item, "_meta_source")]
        if not meta_queue:
            return

        def process_item_metadata(item):
            if self._is_canceled: return
            
            metadata = get_image_info_metadata(item._meta_source, self.ffprobe_path, self.oiiotool_path)
            if not metadata: return
            
            item.metadata.update(metadata)
            
            # 1. Video Thumbnail Generation
            if item.category == "Video":
                thumb_path = item._meta_source + "_thumbnail.png"
                if not os.path.exists(thumb_path):
                    duration = metadata.get("duration")
                    generate_video_thumbnail(item._meta_source, self.ffmpeg_path, 
                                             frame_mode=self.seq_thumb_frame, duration=duration)
                
                # Update icon if thumbnail exists now
                if os.path.exists(thumb_path):
                    item.thumbnail = generate_thumbnail(thumb_path, self.thumbnail_size)

            # 2. Special handling for videos: start frame from TC
            if item.category == "Video" and getattr(item, "_video_start_from_tc", False):
                start_from_tc = metadata.get("start_from_tc")
                if start_from_tc is not None:
                    item.frame_start = start_from_tc
                    item.frame_end = start_from_tc
            
            self.item_updated.emit(item)

        # Use a thread pool to extract metadata in parallel
        # 4-8 workers is usually good for I/O and external processes
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_item_metadata, meta_queue)

    def _fill_metadata(self, item, file_path):
        """Helper to fill common metadata for an item."""
        # Thumbnail
        if item.category == "Video":
            # Check for existing sidecar thumbnail
            thumb_path = file_path + "_thumbnail.png"
            if os.path.exists(thumb_path):
                item.thumbnail = generate_thumbnail(thumb_path, self.thumbnail_size)
            else:
                # Use gray placeholder until background extraction finishes
                item.thumbnail = generate_placeholder_thumbnail(self.thumbnail_size, "#555555")
        else:
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
