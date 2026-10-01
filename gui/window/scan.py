"""Folder scanning, rescans, name parsing, ages, clipboard paste, drag & drop.

Mixin of MainWindow (gui/main_window.py): methods use the window's
attributes (self.model, self.config, self.thumb_area, ...).
"""
import os
import re
import json
import csv
import tempfile
import subprocess
import logging
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, 
                             QPushButton, QMessageBox, QInputDialog, QApplication,
                             QDialog, QLineEdit, QLabel, QHBoxLayout, QPlainTextEdit, QFormLayout, QScrollArea, QCheckBox, QStyle)
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel, QItemSelection, QThread, Signal, QRect
from PySide6.QtGui import QKeySequence, QCursor, QShortcut, QPainter, QColor, QImage, QAction, QTextCursor

from gui.top_bar import TopBar
from gui.ayon_panel import AyonPanel
from gui.filter_panel import FilterPanel
from gui.thumbnail_area import ThumbnailArea
from gui.spreadsheet_panel import SpreadsheetPanel
from gui.prefs_dialog import PreferencesDialog
from logic.image_model import ImageTableModel
from logic.csv_model import CSVPreviewModel
from logic.scanner import ImageScanner, ThumbnailConversionWorker, ReviewConversionWorker
from gui.conversion_queue_dialog import ConversionQueueDialog
from gui.notify import show_info, play_notification_sound
from ayon_client import AyonClient
from utils import evaluate_preset
from logic.tag_parser import get_parse_target, parse_item_tags
from logic.grouping_engine import (
    compute_group_key, find_matching_group_def, 
    validate_group_representations, apply_group_inheritance,
    pair_group_reviews, apply_thumbnail_source_inheritance, repre_of
)
from gui.window.dialogs import RenameDialog, HelpContentWidget, HelpOverlay, SearchReplaceDialog
from gui.window.ayon_threads import AyonFolderThumbnailThread, AyonThumbnailDownloadThread, AyonGetRepreThread


class ScanMixin:
    def _make_scanner(self, directory):
        """One place that turns preferences into an ImageScanner (used by scan and rescan)."""
        from utils import expand_env_vars
        has_filter = hasattr(self, "filter_panel")
        return ImageScanner(
            directory,
            recursive=self.top_bar.chk_recursive.isChecked(),
            version_regex=self.config.get("version_regex", r"([._]v|v)(\d+)"),
            thumbnail_size=self.config.get("default_thumb_size", 150),
            age_source=self.config.get("age_source", "Modification Date"),
            detect_sequences=self.config.get("detect_sequences", True),
            seq_thumb_frame=self.config.get("seq_thumb_frame", "Middle"),
            extensions=self.config.get("extensions", {}),
            presets=self.config.get("presets", {}),
            stills_start_frame=self.config.get("stills_start_frame", 1001),
            stills_end_frame=self.config.get("stills_end_frame", 1001),
            video_start_from_tc=self.config.get("video_start_from_tc", False),
            video_start_frame=self.config.get("video_start_frame", 1001),
            ffmpeg_path=expand_env_vars(self.secrets.get("ffmpeg_path", "ffmpeg.exe")),
            ffprobe_path=expand_env_vars(self.secrets.get("ffprobe_path", "ffprobe.exe")),
            oiiotool_path=expand_env_vars(self.secrets.get("oiiotool_path", "oiiotool.exe")),
            ocio_config=expand_env_vars(self.secrets.get("ocio_config", "")),
            stills_thumb_same=self.config.get("stills_thumb_same", True),
            thumb_suffix=self.config.get("thumb_suffix", "_thumbnail"),
            thumb_format=self.config.get("thumb_format", ".jpg"),
            thumb_location=self.config.get("thumb_location", "Relative to Source Folder"),
            thumb_location_path=self.config.get("thumb_location_path", "_thumbs"),
            timeout=self.config.get("timeout_seconds", 6),
            default_fps=self.config.get("default_fps", 25.0),
            use_fps_from_metadata=self.config.get("use_fps_from_metadata", True),
            drawing_cache_location=self.config.get("drawing_cache_location", "relative to source folder"),
            drawing_cache_path=self.config.get("drawing_cache_path", "_drawcache"),
            ignore_enabled=self.filter_panel.chk_ignore.isChecked() if has_filter else True,
            ignore_text=self.filter_panel.ignore_bar.text() if has_filter else "",
            config=dict(self.config),  # tags are parsed in the scanner, before presets/grouping
            pair_existing_media=self.config.get("pair_existing_media", True),
        )

    def _start_post_scan_work(self, new_items):
        """Runs once metadata (fps, frame range, thumbnail time) is known for the scan."""
        if not new_items:
            self.trigger_ayon_thumbnail_downloads()
            return
        if self.config.get("run_thumb_after_scan", False):
            self.start_conversions(new_items)
        elif self.config.get("run_review_after_scan", False):
            self.start_review_conversions()
        else:
            self.trigger_ayon_thumbnail_downloads()

    def start_scan(self, directory):
        self.log_message(f"Starting scan of directory: {directory}")
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()

        # Rescanning the folder that is already loaded (e.g. after a preference change)
        # keeps notes, backdrops and drawings, and the view stays where it is.
        prev_folder = getattr(self.model, "source_folder", "") or ""
        self._rescan_same_folder = bool(prev_folder) and (
            os.path.normcase(os.path.normpath(prev_folder)) == os.path.normcase(os.path.normpath(directory)))
        if self._rescan_same_folder:
            self.thumb_area.clear_thumbnails()
        else:
            self.thumb_area.clear_canvas()
        self.model.clear()
        self.model.source_folder = directory
        self.filter_panel.set_root_folder(directory)
        self.top_bar.set_path(directory)
        
        self.scanner = self._make_scanner(directory)
        # Ignore results from a scanner that was superseded by a newer scan
        # (its signal may already be queued when we cancel it).
        scanner = self.scanner
        def _on_finished(items, scanner=scanner):
            if scanner is not self.scanner:
                return
            self.log_message(f"Scan complete. Found {len(items)} items. Fetching metadata in background...", "success")
            self._on_scan_finished(items)
        self.scanner.finished.connect(_on_finished)
        self.scanner.metadata_done.connect(
            lambda scanner=scanner: self._start_post_scan_work(list(getattr(self, "_last_scan_items", [])))
            if scanner is self.scanner else None)
        self.scanner.item_updated.connect(self.model.update_item)
        self.scanner.status_text.connect(lambda txt: self.statusBar().showMessage(txt))
        self.scanner.log.connect(self.log_message)
        self.scanner.start()
        self._add_to_recent(directory)
        
        # Update config
        self.config["last_source_folder"] = directory
        self.save_config()
        
        # Apply current age filter after scan starts/completes
        # (Though items are added asynchronously, we want the state set)
        self._update_ages()
        self.spreadsheet.update_filtering(age_filter=(self._age_filter_enabled, self._age_filter_value))
        self.thumb_area.rearrange_items(age_filter=(self._age_filter_enabled, self._age_filter_value))

    def _on_scan_finished(self, new_items):
        """Phase 1 of the scan is done: show items, then group and pair reviews.

        Tags were already parsed by the scanner (before presets). Conversions start
        later, from the scanner's metadata_done signal, when fps/frame ranges are known.
        """
        for item in new_items:
            if not getattr(item, "_tags_parsed", False):
                self._parse_item_tags(item)
        self._last_scan_items = list(new_items)
        self.model.add_items(new_items)
        self._update_grouping_and_inheritance()
        if not getattr(self, "_rescan_same_folder", False):
            self.thumb_area.frame_all()


    def rescan_current(self):
        """Scan for new files in the current directory without clearing existing data."""
        directory = self.top_bar.path_display.text()
        if not directory or not os.path.exists(directory):
            self.log_message("No valid directory to rescan.", "warning")
            return
            
        # Check that all files shown as items in the app still exist. If not, remove them.
        version_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        items_to_remove = []
        path_updated = False
        
        for item in list(self.model.items):
            if os.path.exists(item.file_path):
                continue
                
            exists = False
            if item.is_sequence:
                directory_path = os.path.dirname(item.file_path)
                if os.path.exists(directory_path):
                    orig_filename = os.path.basename(item.file_path)
                    base, ext = os.path.splitext(orig_filename)
                    ver_match = re.search(version_regex, orig_filename, re.IGNORECASE)
                    ver_str = ver_match.group(0) if ver_match else ""
                    
                    name_no_ver = re.sub(version_regex, "", orig_filename, flags=re.IGNORECASE)
                    from utils import strip_sequence_counter
                    pattern_base = strip_sequence_counter(name_no_ver)
                    
                    try:
                        all_dir_files = os.listdir(directory_path)
                    except Exception:
                        all_dir_files = []
                        
                    for f in all_dir_files:
                        if not os.path.isfile(os.path.join(directory_path, f)):
                            continue
                        f_no_ver = re.sub(version_regex, "", f, flags=re.IGNORECASE)
                        f_pattern_base = strip_sequence_counter(f_no_ver)
                        f_ver_match = re.search(version_regex, f, re.IGNORECASE)
                        f_ver_str = f_ver_match.group(0) if f_ver_match else ""
                        
                        if f_pattern_base == pattern_base and f_ver_str == ver_str and f.lower().endswith(ext.lower()):
                            item.file_path = os.path.join(directory_path, f).replace("\\", "/")
                            item.filename = f
                            exists = True
                            path_updated = True
                            break
            if not exists:
                items_to_remove.append(item)
                
        if items_to_remove or path_updated:
            self.model.beginResetModel()
            if items_to_remove:
                self.model.items = [it for it in self.model.items if it not in items_to_remove]
            else:
                self.model.rebuild_version_stacks()
            self.model.endResetModel()
            
            if items_to_remove:
                self.log_message(f"Removed {len(items_to_remove)} items whose files no longer exist.", "info")
            if path_updated:
                self.log_message("Updated paths for sequence items with missing representative frames.", "info")
            
        self.log_message(f"Rescanning directory: {directory}")
        self.model.source_folder = directory
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()
            
        self.scanner = self._make_scanner(directory)
        scanner = self.scanner
        self.scanner.finished.connect(lambda items, scanner=scanner: self._on_rescan_finished(items) if scanner is self.scanner else None)
        self.scanner.metadata_done.connect(
            lambda scanner=scanner: self._start_post_scan_work(list(getattr(self, "_last_scan_items", [])))
            if scanner is self.scanner else None)
        self.scanner.item_updated.connect(self.model.update_item)
        self.scanner.log.connect(self.log_message)
        self.scanner.start()

    def _on_rescan_finished(self, items):
        """Filter for new items and add them to the model."""
        # A sequence is identified by folder + name + version, not by the frame that
        # represents it (that frame changes when frames are added).
        def ident(it):
            key = getattr(it, "seq_key", None)
            return key if key else os.path.normcase(os.path.normpath(it.file_path))
        existing = {ident(item) for item in self.model.items}
        new_items = [it for it in items if ident(it) not in existing]
        self._last_scan_items = list(new_items)
        
        if new_items:
            for item in new_items:
                if not getattr(item, "_tags_parsed", False):
                    self._parse_item_tags(item)
            self.model.add_items(new_items)
            self._update_grouping_and_inheritance()
            self.log_message(f"Rescan complete. Added {len(new_items)} new items.", "success")
        else:
            self.log_message("Rescan complete. No new items found.")

    def reveal_source_folder(self):
        """Open the current source folder in the OS file manager."""
        import os
        import subprocess
        folder = self.top_bar.path_display.text().strip()
        if not folder or not os.path.exists(folder):
            folder = self.config.get("last_source_folder", "").strip()
            
        if folder and os.path.exists(folder):
            folder = os.path.normpath(folder)
            subprocess.run(['explorer', folder])
        else:
            QMessageBox.warning(self, "Reveal in Filesystem", "No valid source folder selected or folder does not exist.")

    def _on_age_filter_changed(self, value, units, enabled):
        self._age_filter_enabled = enabled
        self._age_filter_units = units
        
        # Convert to minutes for internal comparison
        # We add 1 to the value to include the full period (e.g. 0 days = < 1 day)
        minutes = (value + 1)
        if units == "hours": minutes *= 60
        elif units == "days": minutes *= 1440
        self._age_filter_value = minutes
        
        self.model.set_age_unit(units)
        
        # Re-calculate ages and refresh filtering
        self._update_ages()
        self.spreadsheet.update_filtering(age_filter=(self._age_filter_enabled, self._age_filter_value))
        self.thumb_area.rearrange_items(age_filter=(self._age_filter_enabled, self._age_filter_value))
        
        # Save changed states immediately
        self.config["filter_age_enabled"] = enabled
        self.config["filter_age_value"] = value
        self.config["filter_age_units"] = units
        self.save_config()

    def _update_ages(self):
        import time
        current_time = time.time()
        source = self.config.get("age_source", "Modification Date")
        
        for item in self.model.items:
            source_time = item.modification_time if source == "Modification Date" else item.creation_time
            item.age_minutes = int((current_time - source_time) / 60)
        
        # Notify the model that the age column (index 12) has changed
        if self.model.items:
            self.model.dataChanged.emit(
                self.model.index(0, 12), 
                self.model.index(len(self.model.items)-1, 12)
            )

    def perform_paste_image(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            self.log_message("No image found in clipboard.", "warning")
            return

        # 1. Resolve path from Preferences
        import datetime
        now = datetime.datetime.now()
        yy = now.strftime("%y")
        mm = now.strftime("%m")
        dd = now.strftime("%d")
        
        default_root = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Downloads")
        from utils import expand_env_vars
        root = expand_env_vars(self.config.get("clip_temp_root", default_root))
        folder_tpl = self.config.get("clip_folder_template", "IngestDesktop_{yy}{mm}{dd}")
        folder_name = folder_tpl.replace("{yy}", yy).replace("{mm}", mm).replace("{dd}", dd)
        
        target_dir = os.path.normpath(os.path.join(root, folder_name))
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
        except Exception as e:
            self.log_message(f"Failed to create temp directory: {e}", "error")
            return
            
        # 2. Resolve filename
        prefix = self.config.get("clip_file_prefix", "clipboard")
        padding = self.config.get("clip_file_counter", 3)
        
        # Find next counter
        try:
            existing = [f for f in os.listdir(target_dir) if f.startswith(prefix) and f.endswith(".png")]
        except OSError:
            existing = []
            
        next_num = 1
        if existing:
            import re
            nums = []
            safe_prefix = re.escape(prefix)
            # Match prefix, then underscore, then digits, then .png
            pattern = rf"^{safe_prefix}_(\d+)\.png$"
            for f in existing:
                match = re.search(pattern, f)
                if match:
                    nums.append(int(match.group(1)))
            if nums:
                next_num = max(nums) + 1
        
        file_name = f"{prefix}_{str(next_num).zfill(padding)}.png"
        file_path = os.path.join(target_dir, file_name)
        
        # 3. Save as 24-bit PNG
        try:
            # Convert to RGB888 for 24bit
            image_24 = image.convertToFormat(QImage.Format_RGB888)
            if image_24.save(file_path, "PNG"):
                self.log_message(f"Clipboard image saved: {file_path}", "success")
            else:
                self.log_message(f"Failed to save image to {file_path}", "error")
                return
        except Exception as e:
            self.log_message(f"Error saving clipboard image: {e}", "error")
            return
        
        # 4. Set source folder and rescan
        self.top_bar.set_path(target_dir)
        self.start_scan(target_dir)

    def _get_parse_target(self, item, parse_mode):
        """Target string for tag regexes (see logic/tag_parser.py)."""
        return get_parse_target(item, parse_mode, self._scan_folder_for_parsing())

    def _scan_folder_for_parsing(self):
        if hasattr(self, "model") and getattr(self.model, "source_folder", None):
            return self.model.source_folder
        if hasattr(self, "top_bar") and hasattr(self.top_bar, "get_path"):
            return self.top_bar.get_path()
        return ""

    def _parse_item_tags(self, item):
        """Parse version and tags into item.metadata (see logic/tag_parser.py)."""
        parse_item_tags(item, self.config, self._scan_folder_for_parsing())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
            
        # Take the first one
        path = urls[0].toLocalFile()
        if os.path.exists(path):
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            # Start scan
            self.top_bar.path_display.setText(path)
            self.start_scan(path)
            event.acceptProposedAction()
