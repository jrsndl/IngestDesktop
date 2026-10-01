import os
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal
from utils import (get_all_files, generate_thumbnail_image,
                   generate_video_thumbnail, generate_placeholder_thumbnail_image,
                   evaluate_preset, calculate_thumbnail_time)
from logic.image_model import ImageItem
from logic.metadata import get_image_info_metadata
from logic import paths as item_paths
from logic.seqparse import split_name, frame_range_info, format_frame
from logic.tag_parser import parse_item_tags
from logic.pairing import PairIndex


def sequence_key(file_path, base, ext, version):
    """Identity of a sequence/still independent of which frame represents it."""
    return (os.path.normcase(os.path.normpath(os.path.dirname(file_path))),
            os.path.normcase(base), ext.lower(), version)


class ImageScanner(QThread):
    """Scan a folder and build ImageItems.

    Order of operations
    -------------------
    Phase 1 (fast, items are shown as soon as it ends):
      1. walk the folder, drop ignored / drawing-cache / generated-thumbnail files
      2. group image files into sequences (logic/seqparse.py rules)
      3. per item: parse version + tags from the name (logic/tag_parser.py)
      4. per item: pick the preset (may use the label), fill preset fields
      5. per item: existing review/thumbnail on disk, file times, preview image
      -> emit `finished(items)`  (name kept for compatibility; this is NOT QThread.finished)
    Phase 2 (background):
      6. ffprobe/oiiotool metadata per item (timeout per call, not per scan),
         video thumbnails, video frame range, thumbnail time
      -> emit `item_updated(item)` per item, then `metadata_done()`
    Grouping / review pairing is done by the main window after phase 1, with the
    final tags, so it is never computed from half-filled items.
    """
    progress = Signal(int, int)  # current, total
    status_text = Signal(str)
    finished = Signal(list)
    item_updated = Signal(object)
    metadata_done = Signal()
    canceled = Signal()
    log = Signal(str)

    def __init__(self, directory, recursive=True, version_regex=r"([._]v|v)(\d+)",
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
                 drawing_cache_path="_drawcache",
                 ignore_enabled=True, ignore_text="", config=None, pair_existing_media=True):
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
        self.timeout = timeout  # seconds per external tool call (ffprobe/ffmpeg/oiiotool)
        self.default_fps = default_fps
        self.use_fps_from_metadata = use_fps_from_metadata
        self.drawing_cache_location = drawing_cache_location
        self.drawing_cache_path = drawing_cache_path
        self.ignore_enabled = ignore_enabled
        self.ignore_text = ignore_text
        # Full preferences (tag parsing rules). When None, tags are parsed by the GUI.
        self.config = config
        # Link footage to thumbnails / review movies that already exist (logic/pairing.py)
        self.pair_existing_media = pair_existing_media
        self._pairs = None
        self._paired = {}  # footage path (normcase) -> (thumb_path, review_path)
        self._paired_reviews = {}  # review movie path (normcase) -> footage path
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    # ------------------------------------------------------------------
    def run(self):
        try:
            self._run()
        except Exception as e:  # never leave the UI waiting in "scanning"
            msg = f"[Error] Scan failed: {e}"
            print(msg)
            traceback.print_exc()
            self.log.emit(msg)
            self.status_text.emit(msg)
            self.finished.emit([])
            self.metadata_done.emit()

    def _canceled(self):
        if self._is_canceled:
            self.canceled.emit()
            return True
        return False

    def _run(self):
        if not os.path.exists(self.directory):
            self.finished.emit([])
            self.metadata_done.emit()
            return

        start_time = time.perf_counter()
        self.status_text.emit("Scanning Files...")
        all_files = get_all_files(self.directory, self.recursive)
        if not all_files:
            self.finished.emit([])
            self.metadata_done.emit()
            return
        self.status_text.emit(f"Scanning Files, {len(all_files)} files found")

        groups, videos, others = self._classify(all_files)
        if groups is None:
            return  # canceled
        if self.pair_existing_media:
            groups = self._pair_existing_media(all_files, groups, videos)

        total_units = len(groups) + len(videos) + len(others)
        current = 0
        final_items = []

        # 1. Image groups (stills and sequences)
        for key, entries in groups.items():
            if self._canceled():
                return
            final_items.append(self._make_image_item(entries))
            current += 1
            self.progress.emit(current, total_units)

        # 2. Videos
        for f in videos:
            if self._canceled():
                return
            item = ImageItem(f, category="Video", frame_start=self.video_start_frame,
                             frame_end=self.video_start_frame,
                             version=split_name(f, self.version_regex).version or 1)
            item._meta_source = f
            item._video_start_from_tc = self.video_start_from_tc
            item._video_default_start = self.video_start_frame
            item.seq_key = sequence_key(f, os.path.basename(f), "", None)
            footage = self._paired_reviews.get(os.path.normcase(os.path.abspath(f)))
            if footage:
                # review of other footage: kept for publishing, hidden in canvas / right panel
                item.metadata["paired_review_of"] = footage.replace("\\", "/")
                item.metadata["is_paired_review"] = True
                item.is_review_repre = True
            self._finish_item(item, "videos", f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        # 3. Others
        for f in others:
            if self._canceled():
                return
            item = ImageItem(f, category="Other", version=split_name(f, self.version_regex).version or 1)
            item.seq_key = sequence_key(f, os.path.basename(f), "", None)
            self._finish_item(item, "other", f)
            final_items.append(item)
            current += 1
            self.progress.emit(current, total_units)

        elapsed = time.perf_counter() - start_time
        self.status_text.emit(f"Scan files took {elapsed:.2f} seconds.")
        self.log.emit(f"[Timer] Scan files took {elapsed:.4f} seconds.")
        self.finished.emit(final_items)

        self._fetch_metadata(final_items)
        self.metadata_done.emit()

    # ------------------------------------------------------------------
    def _pair_existing_media(self, all_files, groups, videos):
        """Find existing thumbnails/reviews for every footage item; files used as
        thumbnails are removed from the item list."""
        review_suffixes = {p.get("Review Suffix") for plist in self.presets.values()
                           for p in plist if isinstance(p, dict) and p.get("Review Suffix")}
        self._pairs = PairIndex(all_files, self.directory, (self.thumb_suffix, *review_suffixes))
        consumed = set()
        footage = [(sorted(e[2] for e in entries), len(entries) > 1) for entries in groups.values()]
        footage += [([v], False) for v in videos]
        for paths, is_seq in footage:
            first = paths[0]
            thumb = self._pairs.thumbnail_for(first, is_seq)
            review = self._pairs.review_for(first, is_seq)
            if thumb or review:
                self._paired[os.path.normcase(os.path.abspath(first))] = (thumb, review)
            if thumb:
                consumed.add(os.path.normcase(os.path.abspath(thumb)))
            if review:
                self._paired_reviews.setdefault(os.path.normcase(os.path.abspath(review)), first)
        if consumed:
            kept = {}
            for key, entries in groups.items():
                if len(entries) == 1 and os.path.normcase(os.path.abspath(entries[0][2])) in consumed:
                    continue  # this file is a thumbnail of other footage, not an item
                kept[key] = entries
            n = len(groups) - len(kept)
            if n:
                self.log.emit(f"Paired {n} existing thumbnail file(s) with their footage.")
            groups = kept
        return groups

    def _classify(self, all_files):
        def parse_exts(s, default):
            if not s:
                return default
            return {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                    for e in s.split() if e.strip()}

        img_exts = parse_exts(self.extensions.get("stills"), {".jpg", ".jpeg", ".png", ".tga", ".exr", ".dpx", ".psd"})
        img_exts |= parse_exts(self.extensions.get("sequences"), set())
        vid_exts = parse_exts(self.extensions.get("videos"), {".mov", ".mp4", ".mxf"})
        other_exts = parse_exts(self.extensions.get("other"), set())

        cache_dir = None
        if self.drawing_cache_path:
            if self.drawing_cache_location == "relative to source folder":
                cache_dir = os.path.join(self.directory, self.drawing_cache_path)
            else:
                cache_dir = os.path.abspath(self.drawing_cache_path)
            cache_dir = os.path.normcase(os.path.normpath(cache_dir))

        ignore_patterns = []
        if self.ignore_enabled and self.ignore_text:
            ignore_patterns = [p.strip().lower() for p in self.ignore_text.split() if p.strip()]

        thumb_tail = (self.thumb_suffix + self.thumb_format).lower() if self.thumb_suffix and self.thumb_format else None

        groups = {}   # key -> [(frame, frame_str, path, parts)]
        videos, others = [], []
        for f in all_files:
            if self._canceled():
                return None, None, None
            norm = os.path.normcase(os.path.normpath(os.path.abspath(f)))
            if ignore_patterns and any(p in norm.lower() for p in ignore_patterns):
                continue
            if cache_dir and (norm == cache_dir or norm.startswith(cache_dir + os.sep)):
                continue
            base_lower = os.path.basename(f).lower()
            # generated thumbnails: only the file NAME is checked (not folder names)
            if base_lower.endswith("_thumbnail.png") or (thumb_tail and base_lower.endswith(thumb_tail)):
                continue

            ext = os.path.splitext(f)[1].lower()
            if ext in img_exts:
                parts = split_name(f, self.version_regex)
                if self.detect_sequences and parts.frame is not None:
                    key = sequence_key(f, parts.base, ext, parts.version)
                else:
                    key = ("file", norm)
                groups.setdefault(key, []).append((parts.frame, parts.frame_str, f, parts))
            elif ext in vid_exts:
                videos.append(f)
            elif ext in other_exts:
                others.append(f)
            elif not (img_exts or vid_exts or other_exts):
                others.append(f)
        return groups, videos, others

    def _make_image_item(self, entries):
        entries = sorted(entries, key=lambda e: (e[0] is None, e[0] if e[0] is not None else 0, e[2]))
        paths = [e[2] for e in entries]
        first_path = paths[0]
        parts = entries[0][3]
        version = parts.version if parts.version is not None else 1

        if len(paths) > 1:
            frames = [e[0] for e in entries]
            pad = max(e[3].pad for e in entries)
            first_f, last_f, n_missing, missing_preview = frame_range_info(frames)
            label = parts.label
            category = f"sequence[{format_frame(first_f, pad)}-{format_frame(last_f, pad)}]"
            if self.seq_thumb_frame == "Middle":
                source_path = paths[len(paths) // 2]
            elif self.seq_thumb_frame == "Second":
                source_path = paths[1]
            else:
                source_path = first_path
            item = ImageItem(source_path, label=label, version=version, category=category,
                             is_sequence=True, frame_start=first_f, frame_end=last_f)
            item.metadata["nb_frames"] = len(paths)
            item.metadata["frame_padding"] = pad
            item.metadata["seq_thumbnail_path"] = source_path.replace("\\", "/")
            if n_missing:
                item.metadata["missing_frames"] = n_missing
                preview = ", ".join(str(m) for m in missing_preview)
                more = "..." if n_missing > len(missing_preview) else ""
                self.log.emit(f"[Warning] {label}: {n_missing} missing frame(s) in {first_f}-{last_f}: {preview}{more}")
            p_type = "sequences"
        else:
            source_path = first_path
            label = os.path.splitext(os.path.basename(first_path))[0]
            item = ImageItem(source_path, label=label, version=version, category="Still",
                             frame_start=self.stills_start_frame, frame_end=self.stills_end_frame)
            item.metadata["nb_frames"] = 1
            p_type = "stills"

        item.seq_key = sequence_key(first_path, parts.base, parts.ext, parts.version)
        item._meta_source = first_path
        self._finish_item(item, p_type, first_path, thumb_source=source_path)
        return item

    def _finish_item(self, item, p_type, first_path, thumb_source=None):
        # 3. version + tags from the name, before anything that depends on them
        if self.config is not None:
            try:
                parse_item_tags(item, self.config, self.directory)
                item._tags_parsed = True
            except Exception as e:
                self.log.emit(f"[Warning] Tag parsing failed for {item.filename}: {e}")

        # 4. preset
        matched_p = evaluate_preset(first_path, self.presets, p_type, label=item.label) or None
        item.preset_data = matched_p or {}
        item.preset_name = matched_p.get("Name") if matched_p else None
        item.variant = matched_p.get("Variant") if matched_p else None
        item.product_type = matched_p.get("Product Type") if matched_p else None
        item.camel_case = matched_p.get("CamelCase", True) if matched_p else True
        item.representation = matched_p.get("Representation", "{extension}") if matched_p else "{extension}"
        item.colorspace = matched_p.get("Colorspace", "sRGB") if matched_p else "sRGB"
        item.rep_tags = matched_p.get("Tags", "passing") if matched_p else "passing"

        # 5. existing thumbnail / review found by pairing (same name, see logic/pairing.py)
        paired_thumb, paired_review = self._paired.get(os.path.normcase(os.path.abspath(first_path)), (None, None))
        if paired_thumb:
            item.conversion_thumb_path = paired_thumb.replace("\\", "/")
            item.metadata["paired_thumbnail"] = item.conversion_thumb_path
        if paired_review:
            item.review_file_path = paired_review.replace("\\", "/")
            item.metadata["paired_review"] = item.review_file_path
            item.review_status = "done"
        # 6. otherwise review status from the preset's expected location
        elif matched_p and matched_p.get("Convert Review", True):
            rev = item_paths.find_existing_review(item.file_path, item.is_sequence, self.directory, matched_p)
            if rev:
                item.review_file_path = rev
                item.review_status = "done"
            else:
                item.review_status = "waiting"
        else:
            item.review_status = "do not convert"

        self._fill_metadata(item, thumb_source or first_path)

    # ------------------------------------------------------------------
    def _fetch_metadata(self, final_items):
        meta_queue = [it for it in final_items if hasattr(it, "_meta_source")]
        if not meta_queue or self._is_canceled:
            return
        start = time.perf_counter()
        total = len(meta_queue)
        done = [0]
        lock = threading.Lock()

        def work(item):
            if self._is_canceled:
                return
            metadata = get_image_info_metadata(item._meta_source, self.ffprobe_path,
                                               self.oiiotool_path, timeout=self.timeout)
            if metadata:
                item.metadata.update(metadata)
                if item.category == "Video":
                    self._video_postprocess(item, metadata)
            fps = self._resolve_fps(item)
            nb = item.metadata.get("nb_frames", 1)
            item.metadata["thumbnail_time"] = calculate_thumbnail_time(
                nb, fps, mode=self.seq_thumb_frame, default_fps=self.default_fps)
            with lock:
                done[0] += 1
                n = done[0]
            self.status_text.emit(f"Gathering metadata from Files, {n} from {total} files checked")
            self.item_updated.emit(item)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(work, it): it for it in meta_queue}
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc is not None:
                    self.log.emit(f"[Warning] Metadata failed for {futures[fut].filename}: {exc}")

        elapsed = time.perf_counter() - start
        self.status_text.emit(f"Metadata fetching took {elapsed:.2f} seconds.")
        self.log.emit(f"[Timer] Metadata fetching took {elapsed:.4f} seconds.")

    def _video_postprocess(self, item, metadata):
        if not getattr(item, "conversion_thumb_path", None):
            expected_thumb = self._get_expected_thumb_path(item)
            try:
                os.makedirs(os.path.dirname(expected_thumb), exist_ok=True)
            except OSError as e:
                self.log.emit(f"[Warning] Cannot create thumbnail folder: {e}")
            if not os.path.exists(expected_thumb):
                generate_video_thumbnail(item._meta_source, self.ffmpeg_path,
                                         frame_mode=self.seq_thumb_frame,
                                         duration=metadata.get("duration"),
                                         out_path=expected_thumb, timeout=self.timeout)
            if os.path.exists(expected_thumb):
                item.thumbnail_image = generate_thumbnail_image(expected_thumb, self.thumbnail_size)
                item.conversion_thumb_path = expected_thumb

        if getattr(item, "_video_start_from_tc", False):
            start_from_tc = metadata.get("start_from_tc")
            if start_from_tc is not None:
                item.frame_start = start_from_tc
        try:
            item.frame_end = item.frame_start + int(item.metadata.get("nb_frames")) - 1
        except (ValueError, TypeError):
            item.frame_end = item.frame_start

    def _resolve_fps(self, item):
        p_data = item.preset_data or {}
        if p_data.get("FPS Override", False):
            try:
                return float(p_data.get("FPS"))
            except (ValueError, TypeError):
                pass
        elif self.use_fps_from_metadata and p_data.get("FPS From Metadata", True):
            try:
                v = item.metadata.get("framerate")
                if v is not None:
                    return float(v)
            except (ValueError, TypeError):
                pass
        return self.default_fps

    def _get_expected_thumb_path(self, item):
        return item_paths.thumb_path(item.file_path, item.is_sequence, self.directory,
                                     self.thumb_location, self.thumb_location_path,
                                     self.thumb_suffix, self.thumb_format)

    def _get_expected_review_path(self, item, preset_data=None):
        found = item_paths.find_existing_review(item.file_path, item.is_sequence, self.directory,
                                                preset_data or item.preset_data)
        return found or item_paths.review_path(item.file_path, item.is_sequence, self.directory,
                                               preset_data or item.preset_data)

    def _fill_metadata(self, item, file_path):
        """Preview image, file times and age."""
        expected_thumb = self._get_expected_thumb_path(item)
        paired = getattr(item, "conversion_thumb_path", "")
        if paired and item_paths.existing_file(paired):
            item.thumbnail_image = generate_thumbnail_image(paired, self.thumbnail_size)
        elif item_paths.existing_file(expected_thumb):
            item.conversion_thumb_path = expected_thumb
            item.thumbnail_image = generate_thumbnail_image(expected_thumb, self.thumbnail_size)
        elif item.category == "Video":
            sidecar = file_path + "_thumbnail.png"
            if os.path.exists(sidecar):
                item.thumbnail_image = generate_thumbnail_image(sidecar, self.thumbnail_size)
            else:
                item.thumbnail_image = generate_placeholder_thumbnail_image(self.thumbnail_size, "#555555")
        else:
            item.thumbnail_image = generate_thumbnail_image(file_path, self.thumbnail_size)

        try:
            item.modification_time = os.path.getmtime(file_path)
            item.creation_time = os.path.getctime(file_path)
            source_time = item.modification_time if self.age_source == "Modification Date" else item.creation_time
            item.age_minutes = int((time.time() - source_time) / 60)
        except OSError:
            pass
        if item.category != "Video":
            fps = self._resolve_fps(item)
            nb = item.metadata.get("nb_frames", 1)
            item.metadata["thumbnail_time"] = calculate_thumbnail_time(nb, fps, mode=self.seq_thumb_frame,
                                                                       default_fps=self.default_fps)


def _kill_process_tree(proc):
    """Kill a shell=True process and everything it started (ffmpeg under cmd.exe)."""
    if proc is None or proc.poll() is not None:
        return
    import subprocess
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=0x08000000)
        else:
            proc.kill()
    except Exception as e:
        print(f"Failed to kill conversion process: {e}")


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
                
            paired = (item.metadata or {}).get("paired_thumbnail")
            if paired and not self.force and os.path.isfile(paired):
                # An existing thumbnail was paired during the scan: use it, don't regenerate
                item.conversion_thumb_path = paired
                from utils import generate_thumbnail_image
                qimage = generate_thumbnail_image(paired, self.config.get("default_thumb_size", 150))
                if qimage:
                    item.thumbnail_image = qimage
                self.item_updated.emit(item)
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
                                                stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                text=True, encoding="utf-8", errors="replace",
                                                creationflags=creationflags)
                
                try:
                    # Timeout applies to THIS command only; a slow file does not stop the batch
                    per_cmd = self.timeout if self.timeout and self.timeout > 0 else None
                    stdout, stderr = self.process.communicate(timeout=per_cmd)
                    returncode = self.process.returncode
                except subprocess.TimeoutExpired:
                    _kill_process_tree(self.process)
                    try:
                        self.process.communicate(timeout=5)
                    except Exception:
                        pass
                    stdout, stderr = "", f"Timeout: conversion took more than {self.timeout} seconds (Preferences > Conversions > Timeout)."
                    returncode = -1
                except Exception as e:
                    stdout, stderr = "", str(e)
                    returncode = -1
                finally:
                    _kill_process_tree(self.process)
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
                
                # stdout is not read -> DEVNULL (a full stdout pipe would deadlock the tool);
                # stdin closed so a tool can never wait for a "[y/N]" answer.
                self.process = subprocess.Popen(cmd, shell=True,
                                                stdin=subprocess.DEVNULL,
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.PIPE,
                                                text=True, encoding="utf-8", errors="replace",
                                                creationflags=creationflags)
                
                tail_lines = []
                try:
                    import re
                    # Regex for ffmpeg time output: time=00:00:04.00
                    time_regex = re.compile(r"time=(\d+:\d+:\d+\.\d+)")
                    frame_regex = re.compile(r"frame=\s*(\d+)")
                    try:
                        duration = float(item.metadata.get("duration", 0) or 0)
                    except (TypeError, ValueError):
                        duration = 0.0
                    try:
                        nb_frames = int(item.metadata.get("nb_frames", 0) or 0)
                    except (TypeError, ValueError):
                        nb_frames = 0
                    last_pct = -1
                    
                    # Read stderr line by line for progress
                    # We use readline() because ffmpeg outputs progress updates on stderr
                    while True:
                        line = self.process.stderr.readline()
                        if not line and self.process.poll() is not None:
                            break
                        
                        if not line:
                            continue
                        tail_lines.append(line.rstrip())
                        if len(tail_lines) > 15:
                            tail_lines.pop(0)

                        # Sequences have no duration: use the frame counter instead
                        f_match = frame_regex.search(line)
                        if f_match and duration <= 0 and nb_frames > 1:
                            pct = min(100, int(int(f_match.group(1)) * 100 / nb_frames))
                            if pct // 10 > last_pct // 10:
                                last_pct = pct
                                item.review_status = f"processing {pct}%"
                                self.item_updated.emit(item)

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
                    stdout, stderr = "", "\n".join(tail_lines)
                except Exception as e:
                    stdout, stderr = "", str(e)
                    returncode = -1
                finally:
                    _kill_process_tree(self.process)
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
