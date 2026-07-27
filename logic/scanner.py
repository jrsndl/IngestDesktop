import os
import time
import re
import fnmatch
from PySide6.QtCore import QThread, Signal
from utils import (get_all_files, get_version_from_name, generate_thumbnail_image, 
                   generate_video_thumbnail, generate_placeholder_thumbnail_image,
                   strip_sequence_counter, get_sequence_counter, evaluate_preset,
                   calculate_thumbnail_time)
from logic.image_model import ImageItem
from logic.metadata import get_image_info_metadata

class ImageScanner(QThread):
    progress = Signal(int, int) # current, total
    status_text = Signal(str)
    finished = Signal(list)
    item_updated = Signal(object)
    canceled = Signal()
    log = Signal(str)

    def __init__(self, directory, recursive=True, version_regex="_v(\\d+)", 
                 thumbnail_size=150, age_source="Modification Date",
                 detect_sequences=True, seq_thumb_frame="Middle", 
                 extensions=None, presets=None,
                 stills_start_frame=1001, stills_end_frame=1001,
                 video_start_from_tc=False, video_start_frame=1001,
                 ffmpeg_path="ffmpeg.exe", ffprobe_path="ffprobe.exe",
                 oiiotool_path="oiiotool.exe", ocio_config="", stills_thumb_same=True,
                 thumb_suffix="_thumbnail", thumb_format=".jpg",
                 thumb_location="Relative to Source Folder", thumb_location_path="_thumbs",
                 timeout=6, default_fps=25.0, use_fps_from_metadata=True,
                  drawing_cache_location="relative to source folder",
                  drawing_cache_path="_drawcache"):
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
        self.thumb_suffix = thumb_suffix
        self.thumb_format = thumb_format
        self.thumb_location = thumb_location
        self.thumb_location_path = thumb_location_path
        self.timeout = timeout
        self.default_fps = default_fps
        self.use_fps_from_metadata = use_fps_from_metadata
        self.drawing_cache_location = drawing_cache_location
        self.drawing_cache_path = drawing_cache_path
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    def run(self):
        if not os.path.exists(self.directory):
            self.finished.emit([])
            return

        print(f"[Timer] Starting directory scan in: {self.directory}...")
        start_time = time.perf_counter()
        self.status_text.emit("Scanning Files...")
        all_files = get_all_files(self.directory, self.recursive)
        if not all_files:
            self.finished.emit([])
            return
        self.status_text.emit(f"Scanning Files, {len(all_files)} files found")

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

        # Resolve drawing cache directory absolute path for exclusion
        cache_dir_lower = None
        if self.drawing_cache_path:
            if self.drawing_cache_location == "relative to source folder":
                if self.directory:
                    cache_dir_lower = os.path.normpath(os.path.join(self.directory, self.drawing_cache_path)).lower()
            else:
                if os.path.isabs(self.drawing_cache_path):
                    cache_dir_lower = os.path.normpath(self.drawing_cache_path).lower()
                else:
                    cache_dir_lower = os.path.normpath(os.path.abspath(self.drawing_cache_path)).lower()

        for f in all_files:
            if self._is_canceled:
                self.canceled.emit()
                return

            if self.timeout > 0 and time.perf_counter() - start_time > self.timeout:
                warning_msg = f"[Warning] Scan operation timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.status_text.emit(warning_msg)
                self.finished.emit([])
                return

            # Exclude files inside the drawing cache folder
            if cache_dir_lower:
                f_norm_path = os.path.normpath(f).lower()
                if f_norm_path.startswith(cache_dir_lower + os.sep) or f_norm_path == cache_dir_lower:
                    continue

            # Completely ignore generated thumbnails
            filename_lower = f.lower()
            if filename_lower.endswith("_thumbnail.png") or \
               (self.thumb_suffix and self.thumb_format and \
                self.thumb_suffix.lower() in filename_lower and \
                filename_lower.endswith(self.thumb_format.lower())):
                continue

            # Completely ignore generated reviews
            # 1. Check common/preset folder names
            f_norm = f.replace("\\", "/")
            parts = f_norm.lower().split("/")
            ignore_folders = {"_reviews"}
            # Collect custom review folders from presets
            for p_type, p_list in self.presets.items():
                for p in p_list:
                    r_path = p.get("Review Path")
                    if r_path: ignore_folders.add(r_path.lower())
            
            if any(p in ignore_folders for p in parts):
                continue
                
            # 2. Check common/preset suffixes
            ignore_suffixes = {"_review"}
            for p_type, p_list in self.presets.items():
                for p in p_list:
                    r_suf = p.get("Review Suffix")
                    if r_suf: ignore_suffixes.add(r_suf.lower())
            
            base_name_lower = os.path.splitext(os.path.basename(f_norm))[0]
            if any(base_name_lower.endswith(s) for s in ignore_suffixes):
                continue

            ext = os.path.splitext(f)[1].lower()
            if ext in img_exts:
                directory = os.path.dirname(f)
                filename = os.path.basename(f)
                
                # 1. Extract version
                version = get_version_from_name(filename, self.version_regex)
                
                if self.detect_sequences:
                    # 2. Strip version from filename for further pattern matching
                    name_no_ver = re.sub(self.version_regex, "", filename, flags=re.IGNORECASE)
                    # 3. Only strip sequence counter if one exists after version is removed
                    if get_sequence_counter(name_no_ver):
                        base_name = strip_sequence_counter(name_no_ver)
                        key = (directory, base_name, ext, version)
                    else:
                        key = (directory, filename, ext, version)
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
            if self.timeout > 0 and time.perf_counter() - start_time > self.timeout:
                warning_msg = f"[Warning] Scan operation timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.status_text.emit(warning_msg)
                self.finished.emit([])
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
                fn_no_ver = re.sub(self.version_regex, "", first_name, flags=re.IGNORECASE)
                ln_no_ver = re.sub(self.version_regex, "", last_name, flags=re.IGNORECASE)
                
                first_f = get_sequence_counter(fn_no_ver)
                last_f = get_sequence_counter(ln_no_ver)
                
                if first_f and last_f:
                    category = f"sequence[{first_f}-{last_f}]"
                
                nb_frames = len(paths)
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
                nb_frames = 1

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
            
            # Initial Review Status
            if matched_p and matched_p.get("Convert Review", True):
                item.review_status = "waiting"
            else:
                item.review_status = "do not convert"
            
            item.metadata["nb_frames"] = nb_frames
            if is_seq:
                item.metadata["seq_thumbnail_path"] = source_path.replace("\\", "/")
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
            if self.timeout > 0 and time.perf_counter() - start_time > self.timeout:
                warning_msg = f"[Warning] Scan operation timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.status_text.emit(warning_msg)
                self.finished.emit([])
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
            
            # Initial Review Status
            if matched_p and matched_p.get("Convert Review", True):
                item.review_status = "waiting"
            else:
                item.review_status = "do not convert"
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
            if self.timeout > 0 and time.perf_counter() - start_time > self.timeout:
                warning_msg = f"[Warning] Scan operation timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.status_text.emit(warning_msg)
                self.finished.emit([])
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
            
            # Initial Review Status
            if matched_p and matched_p.get("Convert Review", True):
                item.review_status = "waiting"
            else:
                item.review_status = "do not convert"
            self._fill_metadata(item, f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        elapsed = time.perf_counter() - start_time
        print(f"[Timer] Scan files took {elapsed:.4f} seconds.")
        self.status_text.emit(f"Scan files took {elapsed:.4f} seconds.")
        self.log.emit(f"[Timer] Scan files took {elapsed:.4f} seconds.")
        
        self.finished.emit(final_items)
        
        # --- Phase 2: Async Metadata Extraction ---
        # Filter items that actually need metadata (sequences and videos)
        meta_queue = [item for item in final_items if hasattr(item, "_meta_source")]
        if not meta_queue:
            return

        print(f"[Timer] Starting to fetch metadata for {len(meta_queue)} items...")
        meta_start_time = time.perf_counter()

        total_meta = len(meta_queue)
        checked_meta = 0

        def process_item_metadata(item):
            if self._is_canceled: return
            if self.timeout > 0 and time.perf_counter() - meta_start_time > self.timeout:
                warning_msg = f"[Warning] Metadata fetching timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.status_text.emit(warning_msg)
                self._is_canceled = True
                return
            
            metadata = get_image_info_metadata(item._meta_source, self.ffprobe_path, self.oiiotool_path, timeout=self.timeout)
            if not metadata: return
            
            item.metadata.update(metadata)
            
            # 1. Video Thumbnail Generation
            if item.category == "Video" and not getattr(item, "conversion_thumb_path", None):
                expected_thumb = self._get_expected_thumb_path(item)
                # Ensure the directory for expected_thumb exists
                os.makedirs(os.path.dirname(expected_thumb), exist_ok=True)
                
                if not os.path.exists(expected_thumb):
                    duration = metadata.get("duration")
                    generate_video_thumbnail(item._meta_source, self.ffmpeg_path, 
                                             frame_mode=self.seq_thumb_frame, duration=duration,
                                             out_path=expected_thumb)
                
                # Update icon if thumbnail exists now
                if os.path.exists(expected_thumb):
                    item.thumbnail_image = generate_thumbnail_image(expected_thumb, self.thumbnail_size)
                    item.conversion_thumb_path = expected_thumb

            # 2. Special handling for videos: start/end frames
            if item.category == "Video":
                if getattr(item, "_video_start_from_tc", False):
                    start_from_tc = metadata.get("start_from_tc")
                    if start_from_tc is not None:
                        item.frame_start = start_from_tc
                
                # Calculate frame_end based on nb_frames
                nb_frames_val = item.metadata.get("nb_frames")
                try:
                    nb_frames_val = int(nb_frames_val)
                    item.frame_end = item.frame_start + nb_frames_val - 1
                except (ValueError, TypeError):
                    item.frame_end = item.frame_start

            # 3. Calculate thumbnail time for ffmpeg seeking
            fps = self._resolve_fps(item)
            nb = item.metadata.get("nb_frames", 1)
            item.metadata["thumbnail_time"] = calculate_thumbnail_time(nb, fps, mode=self.seq_thumb_frame, default_fps=self.default_fps)
            
            nonlocal checked_meta
            checked_meta += 1
            self.status_text.emit(f"Gathering metadata from Files, {checked_meta} from {total_meta} files checked")
            self.item_updated.emit(item)

        # Use a thread pool to extract metadata in parallel
        # 4-8 workers is usually good for I/O and external processes
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_item_metadata, meta_queue)

        meta_elapsed = time.perf_counter() - meta_start_time
        print(f"[Timer] Metadata fetching took {meta_elapsed:.4f} seconds.")
        self.status_text.emit(f"Metadata fetching took {meta_elapsed:.4f} seconds.")
        self.log.emit(f"[Timer] Metadata fetching took {meta_elapsed:.4f} seconds.")

    def _resolve_fps(self, item):
        fps_val = None
        p_data = item.preset_data or {}
        if p_data.get("FPS Override", False):
            fps_preset = p_data.get("FPS")
            if fps_preset is not None:
                try:
                    fps_val = float(fps_preset)
                except (ValueError, TypeError):
                    pass
        else:
            use_meta = getattr(self, "use_fps_from_metadata", True)
            if use_meta and p_data.get("FPS From Metadata", True):
                fps_meta = item.metadata.get("framerate")
                if fps_meta is not None:
                    try:
                        fps_val = float(fps_meta)
                    except (ValueError, TypeError):
                        pass
        if fps_val is None:
            fps_val = self.default_fps
        return fps_val

    def _get_expected_thumb_path(self, item):
        """Calculate the expected generated thumbnail path based on preferences."""
        source_file = item.file_path.replace("\\", "/")
        base_dir = os.path.dirname(source_file)
        filename = os.path.basename(source_file)
        name_no_ext, _ = os.path.splitext(filename)
        
        if item.is_sequence:
            name_no_ext = strip_sequence_counter(name_no_ext)
            
        # Determine target directory
        target_dir = base_dir
        if self.thumb_location == "Relative to Source Folder":
            if self.directory:
                target_dir = os.path.join(self.directory, self.thumb_location_path).replace("\\", "/")
        elif self.thumb_location == "Custom":
            target_dir = self.thumb_location_path.replace("\\", "/")
            
        # Basename with suffix
        target_filename = f"{name_no_ext}{self.thumb_suffix}{self.thumb_format}"
        
        return os.path.join(target_dir, target_filename).replace("\\", "/")

    def _fill_metadata(self, item, file_path):
        """Helper to fill common metadata for an item."""
        # Check if expected generated thumbnail already exists on disk
        expected_thumb = self._get_expected_thumb_path(item)
        if os.path.exists(expected_thumb) and os.path.getsize(expected_thumb) > 0:
            item.conversion_thumb_path = expected_thumb
            item.thumbnail_image = generate_thumbnail_image(expected_thumb, self.thumbnail_size)
        else:
            # Thumbnail
            if item.category == "Video":
                # Check for existing sidecar thumbnail
                thumb_path = file_path + "_thumbnail.png"
                if os.path.exists(thumb_path):
                    item.thumbnail_image = generate_thumbnail_image(thumb_path, self.thumbnail_size)
                else:
                    # Use gray placeholder until background extraction finishes
                    item.thumbnail_image = generate_placeholder_thumbnail_image(self.thumbnail_size, "#555555")
            else:
                item.thumbnail_image = generate_thumbnail_image(file_path, self.thumbnail_size)
        
        # Times
        try:
            item.modification_time = os.path.getmtime(file_path)
            item.creation_time = os.path.getctime(file_path)
            
            # Age
            source_time = item.modification_time if self.age_source == "Modification Date" else item.creation_time
            item.age_minutes = int((time.time() - source_time) / 60)
            
            # Initial thumbnail_time for stills/sequences (videos handled in Phase 2)
            if item.category != "Video":
                fps = self._resolve_fps(item)
                nb = item.metadata.get("nb_frames", 1)
                item.metadata["thumbnail_time"] = calculate_thumbnail_time(nb, fps, mode=self.seq_thumb_frame, default_fps=self.default_fps)
        except Exception:
            pass

class ThumbnailConversionWorker(QThread):
    item_updated = Signal(object)
    progress = Signal(int, int)
    status_text = Signal(str)
    finished = Signal()
    log = Signal(str)

    def __init__(self, items, model, config, force=False, timeout=6):
        super().__init__()
        self.items = items
        self.model = model
        self.config = config
        self.force = force
        self.timeout = timeout
        self._is_canceled = False
        self.process = None

    def cancel(self):
        self._is_canceled = True
        if self.process:
            try:
                import os
                import subprocess
                if os.name == 'nt':
                    # Kill the whole process tree (cmd.exe and its children)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], 
                                   capture_output=True, creationflags=0x08000000)
                else:
                    self.process.kill()
            except Exception as e:
                print(f"Failed to kill conversion process: {e}")

    def run(self):
        import subprocess
        import os
        import time
        
        total = len(self.items)
        print(f"[Timer] Starting thumbnail generation for {total} items...")
        self.log.emit(f"Starting thumbnail generation for {total} items...")
        start_time = time.perf_counter()
        for i, item in enumerate(self.items):
            if self._is_canceled:
                break
                
            if self.timeout > 0 and time.perf_counter() - start_time > self.timeout:
                warning_msg = f"[Warning] Thumbnail generation timed out after {self.timeout} seconds. Stopping operation."
                print(warning_msg)
                self.log.emit(warning_msg)
                self.status_text.emit(warning_msg)
                break
            
            self.progress.emit(i + 1, total)
            self.status_text.emit(f"Creating Thumbnails, {i+1} from {total} done")
            
            # Only process Stills, Videos, and Sequences
            if item.category[:4].lower() not in ["stil", "vide", "sequ"]:
                print(f"Skipping conversion for {item.file_path}: category '{item.category}' not in ['Still', 'Video', 'Sequence']")
                continue
                
            p_data = item.preset_data or {}
            if not p_data.get("Convert Thumbnail", True):
                print(f"Skipping conversion for {item.file_path}: 'Convert Thumbnail' is disabled in preset")
                continue

            cmd_template = ""
            if p_data.get("Convert Thumbnail Override", False):
                cmd_template = p_data.get("Convert Thumbnail Command", "")
            
            if not cmd_template:
                if item.category == "Still":
                    cmd_template = self.config.get("cmd_stills", "")
                elif item.category == "Video":
                    cmd_template = self.config.get("cmd_videos", "")
                else:
                    cmd_template = self.config.get("cmd_sequences", "")
                
            if not cmd_template:
                print(f"Skipping conversion for {item.file_path}: no command template found (preset or general)")
                continue
                
            try:
                # Expand tokens to get the final command and target path
                cmd = self.model.expand_tokens(cmd_template, item)
                target_path = self.model.expand_tokens("{prefs_thumb_path}", item)
                
                if not cmd or not target_path:
                    continue
                    
                # Skip existing if enabled (and not forced)
                if not self.force and self.config.get("skip_existing_thumbs", True) and \
                   os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    print(f"Skipping thumbnail conversion: {target_path} already exists")
                    item.conversion_thumb_path = target_path
                    
                    # Load the QImage on background thread to prevent UI freeze!
                    from utils import generate_thumbnail_image
                    qimage = generate_thumbnail_image(target_path, self.config.get("default_thumb_size", 150))
                    if qimage:
                        item.thumbnail_image = qimage
                        
                    self.item_updated.emit(item)
                    continue
                    
                print(f"Executing conversion: {cmd}")
                self.log.emit(f"Executing conversion: {cmd}")
                
                # Ensure output directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Run the conversion command
                creationflags = 0
                if os.name == 'nt':
                    creationflags = 0x08000000 # CREATE_NO_WINDOW
                
                print(f"[Timer] Starting to execute conversion subprocess for {item.label}...")
                self.log.emit(f"Starting to execute conversion subprocess for {item.label}...")
                start_cmd_time = time.perf_counter()
                self.process = subprocess.Popen(cmd, shell=True, 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.PIPE, 
                                                text=True, 
                                                creationflags=creationflags)
                
                try:
                    # Calculate remaining time for the overall operation, but at least 0.1s
                    rem_time = max(0.1, self.timeout - (time.perf_counter() - start_time)) if self.timeout > 0 else None
                    stdout, stderr = self.process.communicate(timeout=rem_time)
                    returncode = self.process.returncode
                except subprocess.TimeoutExpired:
                    # If it times out, kill it and its children
                    self.cancel() 
                    stdout, stderr = "", f"Timeout: conversion took more than {self.timeout} seconds."
                    returncode = -1
                    warning_msg = f"[Warning] Thumbnail generation timed out after {self.timeout} seconds. Stopping operation."
                    print(warning_msg)
                    self.log.emit(warning_msg)
                    self.status_text.emit(warning_msg)
                    self._is_canceled = True
                except Exception as e:
                    stdout, stderr = "", str(e)
                    returncode = -1
                finally:
                    self.process = None
                
                elapsed_cmd = time.perf_counter() - start_cmd_time
                print(f"[Timer] Generating thumbnail for {item.label} took {elapsed_cmd:.4f} seconds.")
                self.log.emit(f"Generating thumbnail for {item.label} took {elapsed_cmd:.4f} seconds.")
                
                # Validation: exit code 0, file exists, and size > 0
                if returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    item.conversion_thumb_path = target_path
                    
                    # Load the QImage on background thread to prevent UI freeze!
                    from utils import generate_thumbnail_image
                    qimage = generate_thumbnail_image(target_path, self.config.get("default_thumb_size", 150))
                    if qimage:
                        item.thumbnail_image = qimage
                        
                    self.item_updated.emit(item)
                else:
                    err = stderr or stdout or "Unknown error"
                    print(f"Conversion failed for {item.file_path}: {err}")
                    self.log.emit(f"Conversion failed for {item.label}: {err}")
                    
            except Exception as e:
                print(f"Error during conversion for {item.file_path}: {e}")
                self.log.emit(f"Error during conversion for {item.label}: {e}")
                
        elapsed = time.perf_counter() - start_time
        print(f"[Timer] Thumbnail generation took {elapsed:.4f} seconds.")
        self.status_text.emit(f"Thumbnail generation took {elapsed:.4f} seconds.")
        self.log.emit(f"[Timer] Thumbnail generation took {elapsed:.4f} seconds.")
        self.finished.emit()

class ReviewConversionWorker(QThread):
    item_updated = Signal(object)
    finished = Signal()
    progress = Signal(int, int) # current, total
    status_text = Signal(str)
    log = Signal(str)

    def __init__(self, items, model, config, force_overwrite=False):
        super().__init__()
        self.items = [it for it in items if it.review_status == "waiting"]
        self.model = model
        self.config = config
        self.force_overwrite = force_overwrite
        self._is_canceled = False
        self._is_paused = False
        self.process = None

    def cancel(self):
        self._is_canceled = True
        self.resume() # Ensure we're not stuck in paused state
        if self.process:
            try:
                import os
                import subprocess
                if os.name == 'nt':
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], 
                                   capture_output=True, creationflags=0x08000000)
                else:
                    self.process.kill()
            except Exception as e:
                print(f"Failed to kill review conversion process: {e}")

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def toggle_pause(self):
        self._is_paused = not self._is_paused
        return self._is_paused

    def run(self):
        import subprocess
        import os
        import time
        
        total = len(self.items)
        for i, item in enumerate(self.items):
            while self._is_paused and not self._is_canceled:
                time.sleep(0.5)

            if self._is_canceled:
                break
            
            p_data = item.preset_data or {}
            cmd_template = p_data.get("Convert Review Command", "")
            
            if not cmd_template:
                # If no command, we mark as failed or just done if it was supposed to be empty?
                # Actually, the user requirement implies if it's on, we should have a command.
                item.review_status = "failed"
                self.item_updated.emit(item)
                continue
                
            try:
                item.review_status = "processing"
                self.item_updated.emit(item)
                self.progress.emit(i + 1, total)
                self.status_text.emit(f"Creating Reviews, {i+1} from {total} done. Currently processing: {item.label}")

                # Expand tokens
                cmd = self.model.expand_tokens(cmd_template, item)
                target_path = self.model.expand_tokens("{prefs_review_path}", item)
                
                if not cmd or not target_path:
                    item.review_status = "failed"
                    self.item_updated.emit(item)
                    continue
                    
                # Skip existing if enabled (and not forced)
                if not self.force_overwrite and self.config.get("skip_existing_reviews", True) and \
                   os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    print(f"Skipping review conversion: {target_path} already exists")
                    item.review_status = "done"
                    self.item_updated.emit(item)
                    continue
                    
                print(f"Executing review conversion: {cmd}")
                self.log.emit(f"Executing review conversion: {cmd}")
                
                # Ensure output directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Run the conversion command
                creationflags = 0
                if os.name == 'nt':
                    creationflags = 0x08000000 # CREATE_NO_WINDOW
                
                self.process = subprocess.Popen(cmd, shell=True, 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.PIPE, 
                                                text=True, 
                                                creationflags=creationflags)
                
                try:
                    import re
                    # Regex for ffmpeg time output: time=00:00:04.00
                    time_regex = re.compile(r"time=(\d+:\d+:\d+\.\d+)")
                    duration = float(item.metadata.get("duration", 0))
                    last_pct = -1
                    
                    # Read stderr line by line for progress
                    # We use readline() because ffmpeg outputs progress updates on stderr
                    while True:
                        line = self.process.stderr.readline()
                        if not line and self.process.poll() is not None:
                            break
                        
                        if not line:
                            continue
                            
                        # Parse time
                        match = time_regex.search(line)
                        if match and duration > 0:
                            t_str = match.group(1)
                            # Convert HH:MM:SS.ms to seconds
                            parts = t_str.split(':')
                            if len(parts) == 3:
                                h, m, s = map(float, parts)
                                current_secs = h * 3600 + m * 60 + s
                                pct = int((current_secs / duration) * 100)
                                pct = min(100, max(0, pct))
                                
                                # Only update every 10% to avoid flickering/perf issues
                                if pct // 10 > last_pct // 10:
                                    last_pct = pct
                                    item.review_status = f"processing {pct}%"
                                    self.item_updated.emit(item)
                    
                    returncode = self.process.wait()
                    stdout, stderr = "", "" # Not used anymore for success check
                except Exception as e:
                    stdout, stderr = "", str(e)
                    returncode = -1
                finally:
                    self.process = None
                
                if returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    item.review_status = "done"
                    # We don't have a field for review path in ImageItem yet, but review_status is "done"
                else:
                    item.review_status = "failed"
                    err = stderr or stdout or "Unknown error"
                    print(f"Review conversion failed for {item.file_path}: {err}")
                    self.log.emit(f"Review conversion failed for {item.label}: {err}")
                
                self.item_updated.emit(item)
                
            except Exception as e:
                item.review_status = "failed"
                self.item_updated.emit(item)
                print(f"Error during review conversion for {item.file_path}: {e}")
                self.log.emit(f"Error during review conversion for {item.label}: {e}")
                
        self.finished.emit()
