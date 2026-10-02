"""Preferences, session state and presets (file layout: logic/settings.py).

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


class SettingsMixin:
    # ------------------------------------------------------------------
    # Preferences / session / install files (layout: logic/settings.py)
    # ------------------------------------------------------------------
    @staticmethod
    def _settings_dir():
        """Folder holding config.json / session.json / install.json.
        INGESTDESKTOP_CONFIG_DIR overrides it (tests use an empty temp folder)."""
        from utils import app_dir
        return os.environ.get("INGESTDESKTOP_CONFIG_DIR") or app_dir

    def _app_file(self, name):
        return os.path.join(self._settings_dir(), name)

    def _presets_folder(self):
        folder = (self.secrets.get("presets_folder") if hasattr(self, "secrets") else "") or "presets"
        from utils import expand_env_vars
        folder = expand_env_vars(folder) or folder
        return folder if os.path.isabs(folder) else os.path.join(self._settings_dir(), folder)

    def _user_prefs_path(self):
        username = os.environ.get("USERNAME") or os.environ.get("USER") or "default_user"
        return os.path.join(self._presets_folder(), "users", f"{username}.json")

    def load_config(self):
        """defaults <- config.json <- users/<USER>.json <- session.json  (later wins)."""
        import time
        from logic import settings as prefs_io
        start_time = time.perf_counter()

        config = prefs_io.defaults()
        base = prefs_io.read_json(self._app_file("config.json"))
        if base:
            config.update(prefs_io.flatten(base))
        user = prefs_io.read_json(self._user_prefs_path())
        if user:
            config.update(prefs_io.flatten(user))
            print(f"[Prefs] Loaded user preferences from {self._user_prefs_path()}")
        session = prefs_io.read_json(self._app_file("session.json"))
        if session:
            flat_session = prefs_io.flatten(session)
            config.update({k: v for k, v in flat_session.items() if k in prefs_io.SESSION})

        self._migrate_keys_to_secrets(config)
        prefs_io.with_aliases(config)
        self.load_prefs_elapsed = time.perf_counter() - start_time
        return config

    def _migrate_keys_to_secrets(self, config_dict):
        """Move per-machine keys (paths, credentials) from a config dict into install.json."""
        from logic import settings as prefs_io
        migrated = False
        for key in list(config_dict.keys()):
            if key in prefs_io.INSTALL_KEYS:
                val = config_dict.pop(key)
                if not self.secrets.get(key):
                    self.secrets[key] = val
                migrated = True
        if migrated:
            self.save_secrets()

    def load_secrets(self):
        from logic import settings as prefs_io
        data = prefs_io.read_json(self._app_file("install.json"))
        if data is None:
            legacy = prefs_io.read_json(self._app_file("secrets.json"))
            if legacy is not None:
                data = legacy
                try:
                    prefs_io.write_json_atomic(self._app_file("install.json"), data)
                    os.remove(self._app_file("secrets.json"))
                except OSError as e:
                    print(f"Error migrating secrets.json: {e}")
        return data or {}

    def load_initial_data(self):
        # Apply label regex
        label_regex = self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$")
        # Upgrade old strict regex if found
        if label_regex == "^[a-zA-Z_-]*$":
            label_regex = "^[a-zA-Z0-9_\\-\\.\\s]*$"
            self.config["label_allowed_chars"] = label_regex
            
        self.model.label_allowed_regex = label_regex
        self.thumb_area.update_label_validator(label_regex)
        
        # Initial UI states
        self._restore_gui_state()
        self.thumb_area.high_res_size = self.config.get("thumb_size", 512)
        
        self.thumb_area.slider_text_size.sizeChanged.connect(self._on_text_size_changed)
        self.thumb_area.slider_thumb_size.sizeChanged.connect(self._on_thumb_size_changed)

        # Update model presets mapping
        self._update_model_presets()
        
        # Populate and sync quick-preset selection dropdown
        self.update_preset_dropdown()

        # Async AYON Load
        self.refresh_ayon_async()
        
        self._is_initializing = False

        from utils import expand_env_vars
        last_folder = self.config.get("last_source_folder")
        if last_folder:
            last_folder = expand_env_vars(last_folder)
        if not last_folder or not os.path.exists(last_folder):
            last_folder = expand_env_vars(self.config.get("default_scan_folder", ""))
            
        # Continue the last session ('last' project in the Sessions Folder) instead
        # of scanning the last folder again
        last_session = self._last_session_path() if hasattr(self, "_last_session_path") else None
        if (self.secrets.get("load_last_session", True) and last_session and os.path.isfile(last_session)
                and not os.environ.get("INGESTDESKTOP_NO_SAVE")):
            QTimer.singleShot(0, self._open_last_session_or_scan)
        elif last_folder and os.path.exists(last_folder):
            self.start_scan(last_folder)
        
        # Initial AYON refresh (handled by refresh_ayon_async above)
        
        # Restore Geometry and Splitter States
        # Saved as hex strings in session.json; empty/None on a fresh install
        def _saved_state(key):
            val = self.config.get(key)
            if not isinstance(val, str) or not val:
                return None
            try:
                return bytes.fromhex(val)
            except ValueError:
                return None
        state = _saved_state("geometry")
        if state:
            self.restoreGeometry(state)
        state = _saved_state("h_splitter")
        if state:
            self.h_splitter.restoreState(state)
        state = _saved_state("v_splitter")
        if state:
            self.v_splitter.restoreState(state)
            
        if hasattr(self, "load_prefs_elapsed"):
            self.log_message(f"Reading preferences took {self.load_prefs_elapsed:.4f} seconds.", "info")

    def _update_model_presets(self):
        """Update the model's category-to-preset-name mapping and re-evaluate items."""
        active_map = {}
        presets = self.config.get("presets", {})
        for p_type, p_list in presets.items():
            active_name = "-"
            for p in p_list:
                if p.get("Active"):
                    active_name = p.get("Name", "-")
                    break
            else:
                if p_list:
                    active_name = p_list[0].get("Name", "-")
            
            # Map back to model categories
            if p_type == "stills": active_map["Still"] = active_name
            elif p_type == "sequences": active_map["Sequence"] = active_name
            elif p_type == "videos": active_map["Video"] = active_name
            elif p_type == "other": active_map["Other"] = active_name
            
        self.model.set_presets(active_map)
        self.model.stills_thumb_same = self.config.get("stills_thumb_same", True)
        
        # Default frame settings from config
        stills_start = self.config.get("stills_start_frame", 1001)
        stills_end = self.config.get("stills_end_frame", 1001)
        video_start = self.config.get("video_start_frame", 1001)
        video_tc = self.config.get("video_start_from_tc", False)

        # Re-evaluate every item in the model
        for item in self.model.items:
            self._parse_item_tags(item)
            cat = item.category
            p_type = "other"
            if "sequence" in cat.lower(): p_type = "sequences"
            elif cat == "Still": p_type = "stills"
            elif cat == "Video": p_type = "videos"
            
            matched_p = evaluate_preset(item.file_path, presets, p_type, label=item.label)
            if matched_p:
                item.preset_name = matched_p.get("Name")
                item.variant = matched_p.get("Variant")
                item.product_type = matched_p.get("Product Type")
                item.camel_case = matched_p.get("CamelCase", True)
                item.representation = matched_p.get("Representation", "{extension}")
                item.colorspace = matched_p.get("Colorspace", "sRGB")
                item.rep_tags = matched_p.get("Tags", "passing")
                item.preset_data = matched_p
                
                # Update review status
                if matched_p.get("Convert Review", True):
                    # Only reset to waiting if it wasn't already done/processing? 
                    # Actually, if the preset changed, we might want to re-convert.
                    # But if it's already "done", we probably shouldn't reset it unless the user explicitly asks.
                    # For now, let's only set to waiting if it was "do not convert" or "failed".
                    if item.review_status in ["do not convert", "failed"]:
                        item.review_status = "waiting"
                else:
                    item.review_status = "do not convert"
            else:
                item.preset_name = None
                item.variant = None
                item.product_type = None
                item.camel_case = True
                item.representation = "{extension}"
                item.colorspace = "sRGB"
                item.rep_tags = "passing"
                item.preset_data = {}
                item.review_status = "do not convert"

            # Refresh frames for non-sequences
            if cat == "Still":
                item.frame_start = stills_start
                item.frame_end = stills_end
            elif cat == "Video":
                # Start from TC if enabled and available in metadata
                if video_tc and item.metadata.get("start_from_tc") is not None:
                    item.frame_start = item.metadata["start_from_tc"]
                    item.frame_end = item.metadata["start_from_tc"]
                else:
                    item.frame_start = video_start
                    item.frame_end = video_start
            
        self.model.layoutChanged.emit()

    def _open_last_session_or_scan(self):
        if self.load_last_session():
            return
        from utils import expand_env_vars
        last_folder = expand_env_vars(self.config.get("last_source_folder", "") or "")
        if last_folder and os.path.exists(last_folder):
            self.start_scan(last_folder)

    def show_preferences(self):
        # Store old values to check if re-scan is needed
        old_detect = self.config.get("detect_sequences", True)
        old_thumb = self.config.get("seq_thumb_frame", "Middle")
        old_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)

        dialog = PreferencesDialog(self.config, self.secrets, self)
        
        # Set size to 80% of main window
        new_w = int(self.width() * 0.8)
        new_h = int(self.height() * 0.8)
        dialog.resize(new_w, new_h)
        
        # Connect Apply button signal
        dialog.applied.connect(lambda data: self._apply_preferences(data[0], data[1], old_detect, old_thumb, old_regex, old_exts, show_message=False))
        
        if dialog.exec():
            new_config, new_secrets = dialog.get_settings()
            self._apply_preferences(new_config, new_secrets, old_detect, old_thumb, old_regex, old_exts, show_message=True)

    def _apply_preferences(self, new_config, new_secrets, old_detect, old_thumb, old_regex, old_exts, show_message=True, save=True):
        self.config.update(new_config)
        self.secrets.update(new_secrets)
        from logic import settings as prefs_io
        prefs_io.with_aliases(self.config)
        from gui.video_player import set_inline_video_disabled
        set_inline_video_disabled(self.config.get("disable_inline_video", False))
        if getattr(self, "edge_swipe", None) is not None:
            self.edge_swipe.enabled = bool(self.config.get("edge_swipe_panels", True))
        
        default_cols = self.config.get("default_columns", 12)
        default_text_size = self.config.get("default_text_size", 10)
        default_thumb_size = self.config.get("default_thumb_size", 150)
        
        gap_h = int(default_thumb_size * 0.20)
        gap_v = int(default_thumb_size * 0.20)
        
        self.thumb_area._last_arrange_vals["cols"] = default_cols
        self.thumb_area._last_arrange_vals["gap_h"] = gap_h
        self.thumb_area._last_arrange_vals["gap_v"] = gap_v
        
        # Update sliders first so items are sized correctly before rearrange
        self.thumb_area.slider_text_size.setValue(default_text_size)
        
        self.model.tooltip_template = self.config.get("item_info_generic", "")
        self.thumb_area.slider_thumb_size.setValue(default_thumb_size)
        # Never force a re-grid here: applying preferences must keep the user's layout.
        # New/unplaced items are still laid out by rearrange_items().
        self.thumb_area.rearrange_items()
        self.thumb_area.high_res_size = self.config.get("thumb_size", 512)
        
        # Apply label regex update
        label_regex = self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$")
        self.model.label_allowed_regex = label_regex
        self.thumb_area.update_label_validator(label_regex)
        
        # Update Tooltip templates
        tt_keys = ["item_info_stills", "item_info_sequences", "item_info_videos", "item_info_other", "item_info_ayon"]
        tt_templates = {k: self.config.get(k, "") for k in tt_keys}
        self.thumb_area.set_tooltip_templates(tt_templates)
        
        # Update Filter Panel sequence display
        version_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        self.model.version_regex = version_regex
        self.model.rebuild_version_stacks()
        
        self.filter_panel.set_sequence_detection(
            self.config.get("detect_sequences", True),
            version_regex
        )
        
        # Update model properties that affect string expansion before updating model presets
        self.model.product_name_template = self.config.get("product_name", "{label}")
        self.model.product_name_camel = self.config.get("product_name_camel", True)
        self.model.stills_thumb_same = self.config.get("stills_thumb_same", True)
        self.model.high_res_size = self.config.get("thumb_size", 512)
        self.model.default_fps = self.config.get("default_fps", 25.0)
        self.model.use_fps_from_metadata = self.config.get("use_fps_from_metadata", True)
        
        self.model.thumb_location = self.config.get("thumb_location", "Relative to Source Folder")
        self.model.thumb_location_path = self.config.get("thumb_location_path", "_thumbs")
        self.model.thumb_suffix = self.config.get("thumb_suffix", "_thumbnail")
        self.model.thumb_format = self.config.get("thumb_format", ".jpg")
        
        from utils import expand_env_vars
        self.model.ffmpeg_path = expand_env_vars(self.secrets.get("ffmpeg_path", "ffmpeg.exe"))
        self.model.ffprobe_path = expand_env_vars(self.secrets.get("ffprobe_path", "ffprobe.exe"))
        self.model.oiiotool_path = expand_env_vars(self.secrets.get("oiiotool_path", "oiiotool.exe"))
        vfxtrans_path = expand_env_vars(self.secrets.get("vfxtranscode", ""))
        self.model.vfxtranscode = os.path.abspath(vfxtrans_path).replace("\\", "/") if vfxtrans_path else ""
        ocio_config_path = expand_env_vars(self.secrets.get("ocio_config", ""))
        self.model.ocio_config = os.path.abspath(ocio_config_path).replace("\\", "/") if ocio_config_path else ""
        
        if save:
            self.save_config()
            self.save_secrets()
            
        self._update_model_presets()
        self.model.rebuild_version_stacks()
        self.update_preset_dropdown()
        
        self.csv_preview_model.refresh_config(self.config)

        if hasattr(self, "spreadsheet") and self.spreadsheet:
            self.spreadsheet.update_filtering()
            if hasattr(self.spreadsheet, "table") and self.spreadsheet.table and self.spreadsheet.table.viewport():
                self.spreadsheet.table.viewport().update()
                self.spreadsheet.table.update()
        
        # Check if scan-related settings changed
        new_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)
        scan_affected = (
            old_detect != self.config.get("detect_sequences") or
            old_thumb != self.config.get("seq_thumb_frame") or
            old_regex != self.config.get("version_regex") or
            old_exts != new_exts
        )
        
        if scan_affected and self.config.get("last_source_folder"):
            self.start_scan(self.config["last_source_folder"])

        # Reload thumbnail cache states and refresh AYON panel icons
        self.load_ayon_thumb_states()
        self._refresh_ayon_panel_icons()
        self.trigger_ayon_thumbnail_downloads()

        # Refresh AYON asynchronously
        self.refresh_ayon_async(reconnect=True)
        
        if show_message:
            show_info(self, "Preferences", "Settings saved. View has been refreshed to reflect scanner changes.", self.config)

    def _on_cols_changed(self, value):
        self.config["default_columns"] = value
        self.save_config()

    def _on_text_size_changed(self, value):
        self.config["default_text_size"] = value
        self.save_config()

    def _on_thumb_size_changed(self, value):
        self.config["default_thumb_size"] = value
        # Sync with scanner size so new items match current UI
        self.config["thumbnail_size"] = value
        self.save_config()

    def _gather_gui_state(self):
        # 1. AYON Panel
        if hasattr(self, "ayon_panel") and self.ayon_panel:
            project_name = self.ayon_panel.combo_project.currentText()
            self.config["ayon_project"] = project_name
            self.config["ayon_project_name"] = project_name
            self.config["ayon_search_text"] = self.ayon_panel.search_edit.text()
            self.config["ayon_search_column"] = self.ayon_panel.search_combo.currentIndex()
            self.config["ayon_show_thumbs"] = self.ayon_panel.btn_show_thumbs.isChecked()
            
            # Selected folder & task in AYON tree
            ayon_folder = ""
            ayon_task = ""
            try:
                indexes = self.ayon_panel.tree.selectionModel().selectedIndexes()
                if indexes:
                    source_idx = self.ayon_panel.proxy.mapToSource(indexes[0])
                    first_col_index = self.ayon_panel.model.index(source_idx.row(), 0, source_idx.parent())
                    item = self.ayon_panel.model.itemFromIndex(first_col_index)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data:
                            if 'folderId' in data and 'folder_path' in data: # Task
                                ayon_folder = data.get("folder_path", "")
                                ayon_task = data.get("name", "")
                            elif 'path' in data: # Folder
                                ayon_folder = data.get("path", "")
                                ayon_task = ""
            except Exception as e:
                print(f"Error gathering AYON selection state: {e}")
            self.config["ayon_selected_folder"] = ayon_folder
            self.config["ayon_selected_task"] = ayon_task

        # 2. Top Panel
        if hasattr(self, "top_bar") and self.top_bar:
            self.config["last_source_folder"] = self.top_bar.path_display.text()
            self.config["active_preset"] = self.top_bar.combo_preset.currentText()

        # 3. Thumbnails Panel
        if hasattr(self, "thumb_area") and self.thumb_area:
            self.config["default_columns"] = self.thumb_area._last_arrange_vals["cols"]
            self.config["thumbnails_show_text"] = self.thumb_area.btn_show_text.isChecked()
            self.config["thumbnails_show_frames"] = self.thumb_area.btn_show_frames.isChecked()
            self.config["default_text_size"] = self.thumb_area.slider_text_size.value()
            self.config["default_thumb_size"] = self.thumb_area.slider_thumb_size.value()
            self.config["player_mode"] = self.thumb_area.player_mode

        # 4. Filter Panel
        if hasattr(self, "filter_panel") and self.filter_panel:
            self.config["filter_search_enabled"] = self.filter_panel.chk_search.isChecked()
            self.config["filter_search_text"] = self.filter_panel.search_bar.text()
            self.config["filter_ignore_enabled"] = self.filter_panel.chk_ignore.isChecked()
            self.config["filter_ignore_text"] = self.filter_panel.ignore_bar.text()
            self.config["filter_age_enabled"] = self.filter_panel.chk_age.isChecked()
            self.config["filter_age_value"] = self.filter_panel.spin_age.value()
            self.config["filter_age_units"] = self.filter_panel.combo_units.currentText()
            self.config["filter_files_only"] = self.filter_panel.btn_files_only.isChecked()
            self.config["filter_flat"] = self.filter_panel.btn_flat.isChecked()
            self.config["filter_v_stack"] = self.filter_panel.btn_v_stack.isChecked()
            self.config["filter_sequences"] = self.filter_panel.btn_sequences.isChecked()

        # 5. Validation Checkboxes
        if hasattr(self, "chk_check_versions"):
            self.config["check_versions"] = self.chk_check_versions.isChecked()
        if hasattr(self, "chk_check_duplicates"):
            self.config["check_duplicates"] = self.chk_check_duplicates.isChecked()

    def _restore_gui_state(self):
        # 1. AYON Panel
        if hasattr(self, "ayon_panel") and self.ayon_panel:
            self.ayon_panel.search_edit.setText(self.config.get("ayon_search_text", ""))
            self.ayon_panel.search_combo.setCurrentIndex(self.config.get("ayon_search_column", 0))
            self.ayon_panel.btn_show_thumbs.setChecked(self.config.get("ayon_show_thumbs", True))

        # 2. Thumbnails Panel
        if hasattr(self, "thumb_area") and self.thumb_area:
            self.model.tooltip_template = self.config.get("item_info_generic", "")
            
            default_cols = self.config.get("default_columns", 12)
            default_text_size = self.config.get("default_text_size", 10)
            default_thumb_size = self.config.get("default_thumb_size", 150)
            
            gap_h = int(default_thumb_size * 0.20)
            gap_v = int(default_thumb_size * 0.20)
            
            self.thumb_area._last_arrange_vals["cols"] = default_cols
            self.thumb_area._last_arrange_vals["gap_h"] = gap_h
            self.thumb_area._last_arrange_vals["gap_v"] = gap_v
            
            self.thumb_area.slider_text_size.setValue(default_text_size)
            self.thumb_area.slider_thumb_size.setValue(default_thumb_size)
            
            self.thumb_area.rearrange_items()  # keep existing placement
            
            show_text = self.config.get("thumbnails_show_text", True)
            self.thumb_area.btn_show_text.setChecked(show_text)
            self.thumb_area._on_show_text_toggled(show_text)
            self.thumb_area.btn_show_frames.setChecked(self.config.get("thumbnails_show_frames", True))
            
            player_mode = self.config.get("player_mode", "stop")
            self.thumb_area.player_mode = player_mode
            if player_mode == "stop":
                self.thumb_area.btn_player_mode.setText("Player: Stop")
            elif player_mode == "selected":
                self.thumb_area.btn_player_mode.setText("Player: Selected")
            elif player_mode == "all":
                self.thumb_area.btn_player_mode.setText("Player: All")
            self.thumb_area.update_video_overlay_geometry()

        # 3. Filter Panel
        if hasattr(self, "filter_panel") and self.filter_panel:
            self.filter_panel.chk_search.setChecked(self.config.get("filter_search_enabled", True))
            self.filter_panel.search_bar.setText(self.config.get("filter_search_text", ""))
            self.filter_panel.chk_ignore.setChecked(self.config.get("filter_ignore_enabled", True))
            self.filter_panel.ignore_bar.setText(self.config.get("filter_ignore_text", ""))
            self.filter_panel.chk_age.setChecked(self.config.get("filter_age_enabled", False))
            self.filter_panel.spin_age.setValue(self.config.get("filter_age_value", 0))
            self.filter_panel.combo_units.setCurrentText(self.config.get("filter_age_units", "minutes"))
            
            # Toggles
            toggles = {
                "files_only": self.config.get("filter_files_only", self.config.get("filter_toggles", {}).get("files_only", True)),
                "flat": self.config.get("filter_flat", self.config.get("filter_toggles", {}).get("flat", False)),
                "v_stack": self.config.get("filter_v_stack", self.config.get("filter_toggles", {}).get("v_stack", False)),
                "sequences": self.config.get("filter_sequences", self.config.get("filter_toggles", {}).get("sequences", True)),
            }
            self.filter_panel.set_toggle_states(toggles)

        # 4. Validation Checkboxes
        if hasattr(self, "chk_check_versions") and self.chk_check_versions:
            self.chk_check_versions.setChecked(self.config.get("check_versions", True))
        if hasattr(self, "chk_check_duplicates") and self.chk_check_duplicates:
            self.chk_check_duplicates.setChecked(self.config.get("check_duplicates", True))

    def save_config(self):
        """Schedule a save (coalesces bursts such as slider drags into one write)."""
        if getattr(self, "_is_initializing", False):
            return
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self.save_config_now)
        self._save_timer.start(400)

    def save_config_now(self):
        """Write preferences (config.json + user file) and session state (session.json)."""
        if getattr(self, "_is_initializing", False):
            return
        if hasattr(self, "_save_timer"):
            self._save_timer.stop()
        if os.environ.get("INGESTDESKTOP_NO_SAVE"):
            return  # tests: never touch the real preference files
        from logic import settings as prefs_io
        self._gather_gui_state()
        prefs = prefs_io.sectioned_preferences(self.config)
        try:
            prefs_io.write_json_atomic(self._app_file("config.json"), prefs)
        except Exception as e:
            print(f"Error saving config.json: {e}")
        try:
            prefs_io.write_json_atomic(self._app_file("session.json"), prefs_io.session_state(self.config))
        except Exception as e:
            print(f"Error saving session.json: {e}")
        if self.secrets.get("presets_folder"):
            try:
                prefs_io.write_json_atomic(self._user_prefs_path(), prefs)
            except Exception as e:
                print(f"Error saving user preferences to {self._user_prefs_path()}: {e}")

    def save_secrets(self):
        if os.environ.get("INGESTDESKTOP_NO_SAVE"):
            return
        from logic import settings as prefs_io
        try:
            prefs_io.write_json_atomic(self._app_file("install.json"), self.secrets)
        except Exception as e:
            print(f"Error saving install.json: {e}")

    def update_preset_dropdown(self):
        """Populate the TopBar preset combobox with available presets from presets_folder."""
        self.top_bar.combo_preset.blockSignals(True)
        self.top_bar.combo_preset.clear()
        self.top_bar.combo_preset.addItem("(None / Active)")
        
        presets_folder = self._presets_folder() if self.secrets.get("presets_folder") else ""
        if presets_folder and os.path.exists(presets_folder):
            try:
                for filename in os.listdir(presets_folder):
                    if filename.endswith(".json"):
                        preset_name = os.path.splitext(filename)[0]
                        self.top_bar.combo_preset.addItem(preset_name)
            except Exception as e:
                print(f"Error listing presets: {e}")
                
        # Set current preset in combobox if active in config
        active_preset = self.config.get("active_preset", "")
        if active_preset:
            index = self.top_bar.combo_preset.findText(active_preset)
            if index >= 0:
                self.top_bar.combo_preset.setCurrentIndex(index)
        else:
            self.top_bar.combo_preset.setCurrentIndex(0)
            
        self.top_bar.combo_preset.blockSignals(False)

    def perform_load_preset(self):
        """Show dialog to select and load a preset from available presets."""
        presets_folder = self._presets_folder() if self.secrets.get("presets_folder") else ""
        available_presets = ["(None / Active)"]
        if presets_folder and os.path.exists(presets_folder):
            for f in os.listdir(presets_folder):
                if f.endswith(".json"):
                    available_presets.append(f[:-5])

        for i in range(self.top_bar.combo_preset.count()):
            text = self.top_bar.combo_preset.itemText(i)
            if text and text not in available_presets:
                available_presets.append(text)

        current = self.top_bar.combo_preset.currentText()
        curr_idx = available_presets.index(current) if current in available_presets else 0

        preset_name, ok = QInputDialog.getItem(
            self, "Load Preset", "Select Preset to load:", available_presets, curr_idx, False
        )
        if ok and preset_name:
            idx = self.top_bar.combo_preset.findText(preset_name)
            if idx >= 0:
                self.top_bar.combo_preset.setCurrentIndex(idx)
            self._on_preset_changed(preset_name)

    def _apply_preset_ayon_project(self, target_project=None):
        """Set AYON project from loaded config if available."""
        project = target_project or (
            self.config.get("ayon_project")
            or self.config.get("ayon_project_name")
            or self.config.get("last_ayon_project")
        )
        if project and hasattr(self, "ayon_panel") and self.ayon_panel:
            if self.ayon_panel.combo_project.findText(project) < 0:
                self.ayon_panel.combo_project.addItem(project)
            if self.ayon_panel.combo_project.currentText() != project:
                self.ayon_panel.combo_project.setCurrentText(project)
            else:
                self._on_project_changed(project)
                self._restore_ayon_selection()

    def _on_preset_changed(self, preset_name):
        """Load a preset = replace the current Preferences with a saved, named set.

        Window/session state (layout, filters, last folder...) is never touched.
        "(None / Active)" keeps the current preferences and only clears the name.
        """
        from logic import settings as prefs_io
        old_detect = self.config.get("detect_sequences", True)
        old_thumb = self.config.get("seq_thumb_frame", "Middle")
        old_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)

        if not preset_name or preset_name == "(None / Active)":
            self.config["active_preset"] = ""
            self.save_config()
            self.log_message("No preset active; current preferences are kept.", "info")
            return

        preset_path = os.path.join(self._presets_folder(), f"{preset_name}.json")
        data = prefs_io.read_json(preset_path)
        if data is None:
            self.log_message(f"Preset '{preset_name}' not found at {preset_path}.", "error")
            return
        try:
            preset_prefs = prefs_io.preferences_only(prefs_io.flatten(data))
            self._migrate_keys_to_secrets(preset_prefs)

            # Start from defaults so a preset never inherits stray values, keep the session.
            session = {k: self.config[k] for k in prefs_io.SESSION if k in self.config}
            new_config = prefs_io.defaults()
            new_config.update(preset_prefs)
            new_config.update(session)
            new_config["active_preset"] = preset_name
            self.config = prefs_io.with_aliases(new_config)

            self._apply_preset_ayon_project(self.config.get("ayon_project") or None)
            self._apply_preferences(self.config, self.secrets, old_detect, old_thumb, old_regex, old_exts,
                                    show_message=False, save=False)
            self._restore_gui_state()
            self.save_config()
            self.log_message(f"Loaded preset '{preset_name}'.", "success")
        except Exception as e:
            self.log_message(f"Error loading preset '{preset_name}': {e}", "error")

    def perform_save_preset(self):
        current_preset = self.top_bar.combo_preset.currentText()
        if not current_preset or current_preset == "(None / Active)":
            current_preset = self.config.get("active_preset", "")

        if current_preset and current_preset != "(None / Active)":
            reply = QMessageBox.warning(
                self,
                "Save Preset Warning",
                f"Preset '{current_preset}' is currently loaded.\nDo you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._save_preset_to_file(current_preset)
        else:
            self.save_preset_as()

    def _save_preset_to_file(self, safe_name):
        """Save the current Preferences (no window/session state) as a named preset."""
        from logic import settings as prefs_io
        if not self.secrets.get("presets_folder"):
            QMessageBox.warning(self, "Save Preset", "Presets Folder is not configured in Preferences -> General Tab.")
            return False
        preset_path = os.path.join(self._presets_folder(), f"{safe_name}.json")
        try:
            self._gather_gui_state()
            prefs_io.write_json_atomic(preset_path, prefs_io.sectioned_preferences(self.config))
            self.config["active_preset"] = safe_name
            self.save_config()
            self.update_preset_dropdown()
            self.log_message(f"Successfully saved preset '{safe_name}' to {preset_path}.", "success")
            show_info(self, "Save Preset", f"Preset '{safe_name}' successfully saved and set as active.", self.config)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Preset Error", f"Error saving preset: {e}")
            return False

    def save_preset_as(self):
        if not self.secrets.get("presets_folder"):
            presets_folder = ""
        else:
            presets_folder = self._presets_folder()
        if not presets_folder:
            QMessageBox.warning(self, "Save Preset", "Presets Folder is not configured in Preferences -> General Tab.")
            return
            
        name, ok = QInputDialog.getText(self, "Save Preset As", "Enter preset name:")
        if not ok or not name.strip():
            return
            
        preset_name = name.strip()
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', preset_name)
        if not safe_name:
            QMessageBox.warning(self, "Save Preset", "Invalid preset name.")
            return
            
        preset_path = os.path.join(presets_folder, f"{safe_name}.json")
        if os.path.exists(preset_path):
            reply = QMessageBox.warning(self, "Save Preset", f"Preset '{safe_name}' already exists. Overwrite?", 
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
                
        self._save_preset_to_file(safe_name)
