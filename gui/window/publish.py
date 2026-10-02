"""CSV export, validation, AYON publish, ingest check, PDF report, duplicate / version checks.

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


class PublishMixin:
    def perform_export_csv(self):
        tagged_items = self._get_tagged_for_ingest()
        if not tagged_items: return
        
        source_folder = self.config.get("last_source_folder")
        if not source_folder or not os.path.exists(source_folder):
            QMessageBox.warning(self, "Export CSV", "No valid source folder scanned.")
            return

        # 1. Validate items
        self.log_message("Export CSV: Running validation checks...")
        valid_items, dup_groups, collision_details = self._validate_tagged_items(tagged_items)
            
        total_dups = sum(len(g) for g in dup_groups.values())
        total_colls = len(collision_details)

        if not valid_items:
            msg = "All selected items were skipped due to errors / duplicate checks:\n\n"
            if dup_groups:
                msg += f"Duplicate items ({total_dups}):\n"
                for ident, items in dup_groups.items():
                    labels = ", ".join([f"'{it.label}' ({it.filename})" for it in items])
                    msg += f"  - [{ident}]: {labels}\n"
                msg += "\n"
            if total_colls:
                msg += f"Version collisions ({total_colls}):\n"
                for item, prod_name, eff_v, last_v in collision_details:
                    msg += f"  - {item.label}: v{eff_v} <= AYON v{last_v}\n"
            
            invalid_items = list(set([it for g in dup_groups.values() for it in g] + [item for item, _, _, _ in collision_details]))
            self.select_items(invalid_items)
            msg += "\nThe skipped items have been selected in the interface."
            QMessageBox.warning(self, "Export CSV", msg)
            return

        # 2. Export logic
        folder_name = os.path.basename(os.path.abspath(source_folder))
        if not folder_name: folder_name = "export"
        csv_path = os.path.join(source_folder, f"{folder_name}.csv")
        
        try:
            self._write_csv_from_preview(valid_items, csv_path)
            self.log_message(f"Exported {len(valid_items)} items to CSV: {csv_path}", "success")
            
            # Summary message
            summary = f"CSV exported successfully to:\n{csv_path}\n\n"
            summary += f"Total exported: {len(valid_items)}\n"
            if total_dups or total_colls:
                summary += f"Total skipped: {total_dups + total_colls}\n"
                if total_dups:
                    summary += f"  - Duplicates ({total_dups}):\n"
                    for ident, items in dup_groups.items():
                        labels = ", ".join([f"'{it.label}' ({it.filename})" for it in items])
                        summary += f"    * [{ident}]: {labels}\n"
                if total_colls:
                    summary += f"  - Version collisions ({total_colls}):\n"
                    for item, prod_name, eff_v, last_v in collision_details:
                        summary += f"    * {item.label} (v{eff_v} <= v{last_v})\n"
                
                invalid_items = list(set([it for g in dup_groups.values() for it in g] + [item for item, _, _, _ in collision_details]))
                self.select_items(invalid_items)
                summary += "\nThe skipped items have been selected in the interface."
            
            show_info(self, "Export CSV", summary, self.config)
            
        except Exception as e:
            self.log_message(f"Failed to export CSV: {e}", "error")
            QMessageBox.critical(self, "Export CSV", f"Failed to export CSV: {e}")

    def _on_show_grouped_toggled(self, checked):
        """Handle Show Grouped toggle from spreadsheet panel toolbar."""
        if hasattr(self, "model") and self.model:
            self.model.show_grouped = checked
        self._update_grouping_and_inheritance()

    def _update_grouping_and_inheritance(self):
        """Compute grouping key, validate representations, apply column inheritance, and set group background indices."""
        if not hasattr(self, "model") or not self.model or not self.model.items:
            return

        group_by_template = self.config.get("group_by", "{folder_name}{task_name}{variant}{version}")
        group_defs = self.config.get("group_definitions", [])

        groups = {}
        for item in self.model.items:
            key = compute_group_key(item, group_by_template, self.model)
            item.group_key = key
            groups.setdefault(key, []).append(item)

        group_keys = sorted(groups.keys())
        for idx, key in enumerate(group_keys):
            g_items = groups[key]
            g_def = find_matching_group_def(g_items, group_defs)
            is_err, missing = validate_group_representations(g_items, g_def, self.config)

            rev_repres = set()
            if g_def:
                r_str = g_def.get("review_repre", "").strip()
                if r_str:
                    rev_repres = {r.lower().lstrip(".") for r in r_str.split()}
            if not rev_repres:
                global_revs = self.config.get("review_representations", ["mp4", "mov", "webm", "mxf"])
                rev_repres = {r.strip().lower().lstrip(".") for r in global_revs if r.strip()}

            MEDIA_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".ogg", ".ogv", ".mxf")
            for item in g_items:
                item.group_index = idx
                item.group_error = is_err
                item.group_missing_repres = missing
                item_repre = repre_of(item)
                item_cat = getattr(item, "category", "") or ""
                item_fp = (getattr(item, "file_path", "") or "").lower()

                if item_repre in rev_repres or item_cat == "Video" or item_fp.endswith(MEDIA_EXTS) or item.metadata.get("is_paired_review", False):
                    item.is_review_repre = True
                else:
                    item.is_review_repre = False

            if g_def:
                apply_group_inheritance(g_items, g_def)
                apply_thumbnail_source_inheritance(g_items, g_def)

            pair_group_reviews(g_items, self.config)

            if rev_repres:
                for item in g_items:
                    item_repre = repre_of(item)
                    if item_repre in rev_repres:
                        item.is_review_repre = True

        if getattr(self.model, "show_grouped", False):
            self.model.items.sort(key=lambda it: (getattr(it, "group_index", 0), getattr(it, "representation", "") or ""))

        self.model.layoutChanged.emit()
        self.model.order_pairs()  # paired reviews right below their main file, whatever the sort
        if hasattr(self, "spreadsheet"):
            self.spreadsheet.update_filtering()
        if hasattr(self, "thumb_area"):
            self.thumb_area.rearrange_items()

    def _validate_tagged_items(self, tagged_items):
        """Run duplicity, version collision, and grouping representation checks and return (valid_items, dup_groups, collision_details)."""
        self._update_grouping_and_inheritance()
        
        check_dups = getattr(self, "chk_check_duplicates", None) is None or self.chk_check_duplicates.isChecked()
        check_vers = getattr(self, "chk_check_versions", None) is None or self.chk_check_versions.isChecked()
        check_group_repres = self.config.get("group_do_not_export_missing_repres", True)

        # Reset item validation states
        for item in tagged_items:
            item.is_duplicate = False
            item.version_collision = None

        # 0. Check missing representations in group
        group_blocked_set = set()
        if check_group_repres:
            for item in tagged_items:
                if getattr(item, "group_error", False):
                    group_blocked_set.add(item)

        if group_blocked_set:
            self.log_message(f"Validation Warning: {len(group_blocked_set)} item(s) belong to groups with missing required representations.", "warning")
            for item in group_blocked_set:
                missing_str = ", ".join(getattr(item, "group_missing_repres", []))
                self.log_message(f"  - Item '{item.label}' (Group '{item.group_key}') missing representations: {missing_str}", "warning")

        # 1. Run Duplicity Test (if enabled)
        duplicate_set = set()
        dup_groups = {}
        if check_dups:
            duplicate_set, dup_groups = self._check_duplicates_in_list(tagged_items)
            for item in duplicate_set:
                item.is_duplicate = True
        
        # 2. Run Version Collision Test (Synchronous, if enabled)
        collision_set = set()
        collision_details = []
        if check_vers:
            project = self.ayon_panel.combo_project.currentText()
            v_map = {}
            if project:
                v_map = self._check_versions_sync(tagged_items)
            
            path_map = self.ayon_panel.get_path_to_id_map()
            for item in tagged_items:
                if not item.ayon_path:
                    continue
                folder_path = "/".join(item.ayon_path.split("/")[:-1])
                f_id = path_map.get(folder_path)
                if f_id:
                    prod_name = self.model.product_name(item)
                    key = f"{f_id}|{prod_name}|{item.product_type}"
                    last_v = v_map.get(key)
                    if last_v is not None:
                        item.last_ayon_version = last_v
                        eff_v = item.effective_version
                        try:
                            eff_v_int = int(eff_v)
                            is_colliding = (last_v >= eff_v_int)
                        except (ValueError, TypeError):
                            is_colliding = True
                            
                        if is_colliding:
                            item.version_collision = True
                            collision_set.add(item)
                            collision_details.append((item, prod_name, eff_v, last_v))
                        else:
                            item.version_collision = False
        
        valid_items = []
        for item in tagged_items:
            if item in duplicate_set or item in collision_set or item in group_blocked_set:
                continue
            valid_items.append(item)
            
        return valid_items, dup_groups, collision_details

    def _check_duplicates_in_list(self, items):
        """Returns tuple of (duplicate_set, dup_groups)."""
        dup_template = self.config.get("duplicate_identity", "{ayon_path_val}{prod_name}{variant}{item.version}")
        identity_map = {}
        for item in items:
            identity = self.model.expand_tokens(dup_template, item)
            if identity not in identity_map:
                identity_map[identity] = []
            identity_map[identity].append(item)
            
        dup_groups = {}
        duplicate_set = set()
        for identity, group in identity_map.items():
            if len(group) > 1:
                dup_groups[identity] = group
                for item in group:
                    duplicate_set.add(item)
                    
        return duplicate_set, dup_groups

    def _check_versions_sync(self, items):
        """Synchronously fetch versions from AYON for the provided items."""
        import time
        start_t = time.perf_counter()
        project = self.ayon_panel.combo_project.currentText()
        if not project: return {}
        
        path_map = self.ayon_panel.get_path_to_id_map()
        folder_ids = set()
        for item in items:
            if not item.ayon_path: continue
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            if f_id: folder_ids.add(f_id)
            
        if not folder_ids: return {}
        
        try:
            print(f"[Timer] Starting synchronous pull of last versions for {len(folder_ids)} folders in project '{project}' from AYON...")
            res = self.ayon.get_last_versions(project, list(folder_ids))
            elapsed = time.perf_counter() - start_t
            print(f"[Timer] Synchronous pull of last versions from AYON took {elapsed:.4f} seconds.")
            return res
        except Exception as e:
            self.log_message(f"Version check failed during export: {e}", "error")
            return {}

    def perform_publish_local(self):
        tagged_items = self._get_tagged_for_ingest()
        if not tagged_items: return
        
        # 1. Validate items
        self.log_message("Publish Local: Running validation checks...")
        valid_items, dup_groups, collision_details = self._validate_tagged_items(tagged_items)
        
        total_dups = sum(len(g) for g in dup_groups.values())
        total_colls = len(collision_details)
        
        # Log duplicates in detail to log console
        if dup_groups:
            self.log_message(f"Validation Warning: Found {total_dups} duplicate items across {len(dup_groups)} duplicate identities:", "warning")
            for identity, group in dup_groups.items():
                self.log_message(f"  - Duplicate identity '{identity}':", "warning")
                for item in group:
                    prod_name = self.model.product_name(item)
                    self.log_message(f"      * '{item.label}' (File: {item.filename}, AYON Path: {item.ayon_path}, Product: {prod_name}, Version: v{item.effective_version})", "warning")

        # Log version collisions in detail to log console
        if collision_details:
            self.log_message(f"Validation Warning: Found {total_colls} version collisions:", "warning")
            for item, prod_name, eff_v, last_v in collision_details:
                self.log_message(f"  - '{item.label}' (Product: {prod_name}, Version: v{eff_v} <= existing AYON v{last_v})", "warning")

        if dup_groups or collision_details:
            popup_lines = []
            
            if dup_groups:
                popup_lines.append(f"<b>DUPLICATE ITEMS ({total_dups} items in {len(dup_groups)} groups):</b>")
                g_idx = 1
                displayed_items = 0
                max_display = 20
                for identity, group in dup_groups.items():
                    if displayed_items >= max_display:
                        remaining_dups = total_dups - displayed_items
                        popup_lines.append(f"  <i>... and {remaining_dups} more duplicate items (see log console for full list)</i>")
                        break
                    popup_lines.append(f"<b>Group {g_idx}</b> (Identity: <i>{identity}</i>):")
                    for item in group:
                        popup_lines.append(f"  • <b>{item.label}</b> (File: {item.filename}, Version: v{item.effective_version}, AYON Path: {item.ayon_path})")
                        displayed_items += 1
                        if displayed_items >= max_display:
                            break
                    g_idx += 1
                popup_lines.append("")
                
            if collision_details:
                popup_lines.append(f"<b>VERSION COLLISIONS ({total_colls} items):</b>")
                displayed_colls = 0
                max_coll_display = 15
                for item, prod_name, eff_v, last_v in collision_details:
                    popup_lines.append(f"  • <b>{item.label}</b>: Version v{eff_v} ≤ existing AYON version v{last_v} (Product: {prod_name})")
                    displayed_colls += 1
                    if displayed_colls >= max_coll_display:
                        remaining_colls = total_colls - displayed_colls
                        if remaining_colls > 0:
                            popup_lines.append(f"  <i>... and {remaining_colls} more version collisions (see log console)</i>")
                        break
                popup_lines.append("")

            if not valid_items:
                dialog_text = "<b>All selected items were skipped due to validation errors:</b><br/><br/>"
                dialog_text += "<br/>".join(popup_lines)
                QMessageBox.warning(self, "Publish Ayon Local", dialog_text)
                return
            else:
                dialog_text = f"<b>Found {total_dups + total_colls} invalid items which will be skipped:</b><br/><br/>"
                dialog_text += "<br/>".join(popup_lines)
                dialog_text += f"<br/><b>Do you want to proceed with publishing the remaining {len(valid_items)} valid item(s)?</b>"
                res = QMessageBox.question(self, "Publish Ayon Local", dialog_text, QMessageBox.Yes | QMessageBox.No)
                if res == QMessageBox.No:
                    return

        # 2. Proceed with publish
        project = self.ayon_panel.combo_project.currentText()
        
        # Ingest log CSV (and later the PDF report) go to the Ingest Log Folder
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.normpath(os.path.join(self._ingest_log_dir(project), f"ayon_ingest_{timestamp}.csv"))
        self.log_message(f"Ingest log: {csv_path}", "info")
        
        try:
            self._write_csv_from_preview(valid_items, csv_path)
        except Exception as e:
            self.log_message(f"Failed to write temporary CSV: {e}", "error")
            QMessageBox.critical(self, "CSV Error", f"Failed to write temporary CSV: {e}")
            return
        
        from utils import expand_env_vars
        tray_path = expand_env_vars(self.secrets.get("traypublisher_path", "ayon_console.exe"))
        ingest_folder = self.config.get("ayon_csv_ingest_folder", "/edit/csvingest")
        ingest_task = self.config.get("ayon_csv_ingest_task", "csvingest")
        ingest_preset = self.config.get("ayon_csv_preset", "Default")
        ignore_validators = self.config.get("ayon_ignore_validators", True)

        cmd = [
            tray_path, "addon", "traypublisher", "ingestcsv",
            "--filepath", csv_path,
            "--project", project,
            "--folder-path", ingest_folder,
            "--task", ingest_task,
            "--preset", ingest_preset
        ]
        if ignore_validators:
            cmd.append("--ignore-validators")
        print(cmd)
        try:
            # Prepare environment with Ftrack secrets
            env = os.environ.copy()
            ftrack_server = self.secrets.get("ftrack_server", "")
            ftrack_user = self.secrets.get("ftrack_api_user", "")
            ftrack_key = self.secrets.get("ftrack_api_key", "")
            
            if ftrack_server: env["FTRACK_SERVER"] = ftrack_server
            if ftrack_user: env["FTRACK_API_USER"] = ftrack_user
            if ftrack_key: env["FTRACK_API_KEY"] = ftrack_key
            
            # Show log console and inform user
            self.log_console.show()
            self.btn_toggle_log.setChecked(True)
            self.log_message("Starting Ayon Publish process...", "info")

            class PublishWorker(QThread):
                line_received = Signal(str)
                
                def __init__(self, cmd, env):
                    super().__init__()
                    self.cmd = cmd
                    self.env = env
                    
                def run(self):
                    # UTF-8 decoding (ayon_console prints UTF-8; the Windows default code page
                    # would raise on some characters and stop reading -> the tool blocks).
                    try:
                        process = subprocess.Popen(
                            self.cmd,
                            env=self.env,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            bufsize=1,
                            creationflags=0x08000000
                        )
                    except Exception as e:
                        self.line_received.emit(f"Failed to start TrayPublisher: {e}")
                        return
                    for line in process.stdout:
                        self.line_received.emit(line.strip())
                    rc = process.wait()
                    if rc != 0:
                        self.line_received.emit(f"TrayPublisher exited with code {rc}")

            if getattr(self, "_publish_worker", None) is not None and self._publish_worker.isRunning():
                self.log_message("A publish is already running; wait for it to finish.", "warning")
                return
            self._publish_worker = PublishWorker(cmd, env)
            self._publish_worker.line_received.connect(lambda line: self.log_message(f"[TrayPublisher] {line}"))
            self._publish_worker.finished.connect(lambda: self._on_publish_finished(csv_path, valid_items))
            self._publish_worker.start()

        except Exception as e:
            self.log_message(f"Failed to start TrayPublisher: {e}", "error")

    def _ingest_log_dir(self, project=""):
        """Folder for ingest CSV logs and PDF reports.

        Preferences > General > Ingest Log Folder (${ENV} variables allowed, relative
        paths are relative to the app folder); empty -> <app>/ingestLog. With
        "Per Project Logging" a sub-folder per AYON project is used.
        """
        import tempfile
        from utils import expand_env_vars
        folder = (self.secrets.get("ingest_log_folder") or "").strip()
        folder = expand_env_vars(folder) if folder else ""
        if not folder:
            folder = "ingestLog"
        if not os.path.isabs(folder):
            folder = os.path.join(self._settings_dir(), folder)
        if self.secrets.get("per_project_logging", True) and project:
            safe_project = re.sub(r'[<>:"/\\|?*]', "_", project)
            folder = os.path.join(folder, safe_project)
        try:
            os.makedirs(folder, exist_ok=True)
            return os.path.normpath(folder)
        except OSError as e:
            fallback = os.path.join(tempfile.gettempdir(), "IngestDesktop_ingestLog")
            os.makedirs(fallback, exist_ok=True)
            self.log_message(f"Cannot use Ingest Log Folder '{folder}' ({e}); using {fallback}", "warning")
            return fallback

    def _ingest_item_map(self, items):
        """Lookup from any path the CSV may contain (file, ####/%04d sequence pattern,
        review movie) to the item, normalised and lower-case."""
        def norm(p):
            return os.path.normpath(os.path.abspath(p)).lower() if p else None
        item_map = {}
        for item in items:
            for key in (item.file_path,
                        self.model.expand_tokens("{filename}", item),
                        self.model.expand_tokens("{filename_printf}", item),
                        self.model.expand_tokens("{prefs_review_path}", item)):
                k = norm(key)
                if k and k not in item_map:
                    item_map[k] = item
        return item_map

    def _report_without_check(self, csv_path, valid_items, reason):
        """Ingest Check could not run: still write the PDF report (status "Not checked")."""
        if not self.config.get("create_ingest_report", True):
            return
        if not csv_path or not os.path.exists(csv_path):
            self.log_message(f"No ingest log to build a report from ({csv_path}).", "warning")
            return
        import csv
        delimiter = self.config.get("csv_delimiter", ",")
        quotechar = self.config.get("csv_quotechar", '"')
        try:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
                headers = next(reader, [])
                rows = [list(r) + [f"Not checked ({reason})"] for r in reader if r]
        except Exception as e:
            self.log_message(f"Cannot read ingest log for the report: {e}", "error")
            return
        cols = {h.lower().strip(): i for i, h in enumerate(headers)}
        def col(*names):
            return next((cols[n] for n in names if n in cols), -1)
        pdf_path = os.path.splitext(csv_path)[0] + "_notChecked.pdf"
        self.generate_ingest_pdf_report(pdf_path, rows, list(headers) + ["Check"],
                                        col("file path", "filepath"),
                                        col("ayon path", "folder path", "folder_path"),
                                        col("version", "v"), self._ingest_item_map(valid_items))

    def _on_publish_finished(self, csv_path, valid_items):
        self.log_message("Publish process finished.", "success")
        self.refresh_ayon()
        
        # Check if Ingest Check is enabled
        if not self.config.get("ayon_ingest_check", True):
            self._report_without_check(csv_path, valid_items, "Ingest Check disabled")
            return
            
        self.log_message("Starting Ingest Check verification...", "info")
        
        import csv
        import shutil
        import datetime
        import ayon_api
        
        if not self.ayon.is_connected:
            self.log_message("AYON is not connected. Ingest Check cannot run.", "error")
            self._report_without_check(csv_path, valid_items, "AYON not connected")
            return
            
        project = self.ayon_panel.combo_project.currentText()
        if not project:
            self.log_message("No project selected for Ingest Check.", "error")
            self._report_without_check(csv_path, valid_items, "no AYON project")
            return
            
        if not csv_path or not os.path.exists(csv_path):
            self.log_message(f"Ingest Log file not found at: {csv_path}", "error")
            return
            
        delimiter = self.config.get("csv_delimiter", ",")
        quotechar = self.config.get("csv_quotechar", '"')
        
        rows = []
        headers = []
        try:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
                headers = next(reader, [])
                for r in reader:
                    if r:
                        rows.append(r)
        except Exception as e:
            self.log_message(f"Error reading Ingest Log file: {e}", "error")
            return
            
        # Find critical columns by checking headers case-insensitively
        file_path_col = -1
        ayon_path_col = -1
        product_name_col = -1
        version_col = -1
        repre_col = -1
        task_col = -1
        
        for idx, h in enumerate(headers):
            h_lower = h.lower().strip()
            if h_lower in ["file path", "filepath"]:
                file_path_col = idx
            elif h_lower in ["ayon path", "folder path", "folder_path"]:
                ayon_path_col = idx
            elif h_lower in ["product name", "product", "subset"]:
                product_name_col = idx
            elif h_lower in ["version", "v"]:
                version_col = idx
            elif h_lower in ["representation", "repre"]:
                repre_col = idx
            elif h_lower in ["task", "task name", "task_name"]:
                task_col = idx
                
        def normalize_version(v_str):
            if not v_str: return None
            try:
                return int(v_str)
            except ValueError:
                pass
            import re
            m = re.search(r'\d+', str(v_str))
            if m:
                return int(m.group())
            return None
            
        checked_rows = []
        check_results = []
        
        # Map every path the CSV may contain (incl. sequence ####) -> item, so the
        # Ingest Status column and the report also work for sequences
        item_map = self._ingest_item_map(valid_items)
                
        item_statuses = {}
        
        for row in rows:
            while len(row) < len(headers):
                row.append("")
                
            file_path_val = row[file_path_col] if file_path_col >= 0 else ""
            ayon_path_val = row[ayon_path_col] if ayon_path_col >= 0 else ""
            version_val = row[version_col] if version_col >= 0 else ""
            
            matched_item = None
            if file_path_val:
                norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                matched_item = item_map.get(norm_f)
                
            product_name_val = ""
            if matched_item:
                product_name_val = self.model.product_name(matched_item)
            if not product_name_val and product_name_col >= 0 and product_name_col < len(row):
                product_name_val = row[product_name_col]
                
            if not product_name_val:
                p_type_val = ""
                variant_val = ""
                for idx, h in enumerate(headers):
                    h_lower = h.lower().strip()
                    if "product type" in h_lower or "product_type" in h_lower:
                        p_type_val = row[idx] if idx < len(row) else ""
                    elif "variant" in h_lower:
                        variant_val = row[idx] if idx < len(row) else ""
                if p_type_val or variant_val:
                    camel = self.config.get("product_name_camel", True)
                    if camel:
                        if p_type_val: p_type_val = p_type_val[0].upper() + p_type_val[1:]
                        if variant_val: variant_val = variant_val[0].upper() + variant_val[1:]
                    product_name_val = f"{p_type_val}{variant_val}"
            
            repre_name = ""
            if repre_col >= 0 and repre_col < len(row):
                repre_name = row[repre_col]
            if not repre_name and file_path_val:
                repre_name = os.path.splitext(file_path_val)[1].replace(".", "").lower()
                
            status_str = "OK"
            try:
                folder = ayon_api.get_folder_by_path(project, ayon_path_val)
                if not folder:
                    status_str = f"Failed: AYON Folder {ayon_path_val} not found"
                else:
                    products = list(ayon_api.get_products(project, folder_ids=[folder["id"]]))
                    product = next((p for p in products if p["name"].lower() == product_name_val.lower()), None)
                    if not product:
                        status_str = f"Failed: Product name \"{product_name_val}\" not found"
                    else:
                        versions = list(ayon_api.get_versions(project, product_ids=[product["id"]]))
                        target_v_num = normalize_version(version_val)
                        version_obj = next((v for v in versions if normalize_version(v.get("version")) == target_v_num), None)
                        if not version_obj:
                            status_str = f"Failed: version {version_val} of product \"{product['name']}\" not found"
                        else:
                            repres = list(ayon_api.get_representations(project, version_ids=[version_obj["id"]]))
                            repre_obj = next((r for r in repres if (
                                r["name"].lower() == repre_name.lower() or
                                repre_name.lower() in r["name"].lower() or
                                r["name"].lower() in repre_name.lower()
                            )), None)
                            if not repre_obj:
                                status_str = f"Failed: version {version_val} of repre \"{repre_name}\" of product \"{product['name']}\" not found"
                            else:
                                if self.config.get("set_version_status_after_check", True):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        ayon_api.update_version(project, version_id=version_obj["id"], status=target_status)
                                        self.log_message(f"Updated AYON version {version_val} (ID: {version_obj['id']}) status to: {target_status}", "success")
                                    except Exception as e:
                                        self.log_message(f"Failed to update AYON version status for version {version_val}: {e}", "warning")

                                if self.config.get("set_product_status_after_check", True):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        ayon_api.update_product(project, product_id=product["id"], status=target_status)
                                        self.log_message(f"Updated AYON product {product['name']} status to: {target_status}", "success")
                                    except Exception as e:
                                        self.log_message(f"Failed to update AYON product status for {product['name']}: {e}", "warning")

                                if self.config.get("set_task_status_after_check", True) or self.config.get("set_neighbour_status_after_check", False):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        tasks = list(ayon_api.get_tasks(project, folder_ids=[folder["id"]]))
                                        
                                        if self.config.get("set_task_status_after_check", True):
                                            current_task_name = row[task_col] if (task_col >= 0 and len(row) > task_col and row[task_col]) else self.config.get("ayon_csv_ingest_task", "csvingest")
                                            if current_task_name:
                                                current_task = next((t for t in tasks if t["name"].lower() == current_task_name.lower()), None)
                                                if current_task:
                                                    ayon_api.update_task(project, task_id=current_task["id"], status=target_status)
                                                    self.log_message(f"Updated AYON task {current_task['name']} status to: {target_status}", "success")
                                                else:
                                                    self.log_message(f"Task '{current_task_name}' not found under folder {ayon_path_val}", "warning")

                                        if self.config.get("set_neighbour_status_after_check", False):
                                            neighbour_name = self.config.get("neighbour_task_name", "comp")
                                            neighbour_status = self.config.get("neighbour_task_status", "Ready to start")
                                            if neighbour_name:
                                                neighbour_task = next((t for t in tasks if t["name"].lower() == neighbour_name.lower()), None)
                                                if neighbour_task:
                                                    ayon_api.update_task(project, task_id=neighbour_task["id"], status=neighbour_status)
                                                    self.log_message(f"Updated AYON neighbour task {neighbour_task['name']} status to: {neighbour_status}", "success")
                                                else:
                                                    self.log_message(f"Neighbour task '{neighbour_name}' not found under folder {ayon_path_val}", "warning")
                                    except Exception as e:
                                        self.log_message(f"Failed to update task/neighbour task status: {e}", "warning")
            except Exception as e:
                self.log_message(f"Error checking AYON database for product '{product_name_val}': {e}", "warning")
                status_str = f"Failed: Error checking AYON database: {e}"
                
            check_results.append(status_str)
            
            if file_path_val:
                norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                if norm_f not in item_statuses:
                    item_statuses[norm_f] = []
                item_statuses[norm_f].append(status_str)
            
            checked_row = list(row)
            checked_row.append(status_str)
            checked_rows.append(checked_row)
            
        # Update matching items with their final resolved status for this run
        for norm_f, statuses in item_statuses.items():
            matched_item = item_map.get(norm_f)
            if matched_item:
                if any(s != "OK" for s in statuses):
                    matched_item.ingest_status = "Failed"
                else:
                    matched_item.ingest_status = "OK"
                self.model.update_item(matched_item)
                if hasattr(self, "thumb_area"):
                    self.thumb_area.note_ingest_result(matched_item, matched_item.ingest_status == "OK")
            
        checked_headers = list(headers)
        checked_headers.append("Check")
        
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
                writer.writerow(checked_headers)
                writer.writerows(checked_rows)
        except Exception as e:
            self.log_message(f"Failed to overwrite checked CSV file: {e}", "error")
            return
            
        if all(res == "OK" for res in check_results):
            suffix = "_checkedOK"
        elif all(res.startswith("Failed") for res in check_results):
            suffix = "_checkedFailed"
        else:
            suffix = "_checkedMixed"
            
        base_no_ext, ext = os.path.splitext(csv_path)
        new_csv_path = f"{base_no_ext}{suffix}{ext}"
        try:
            shutil.move(csv_path, new_csv_path)
            self.log_message(f"Ingest Check completed! Result suffix: {suffix}. File renamed to: {os.path.basename(new_csv_path)}", "success")
        except Exception as e:
            self.log_message(f"Failed to rename Ingest Log CSV: {e}", "error")

        # Generate PDF Ingest Report if configured
        self._last_report_path = None
        if self.config.get("create_ingest_report", True):
            pdf_path = f"{base_no_ext}{suffix}.pdf"
            self.generate_ingest_pdf_report(pdf_path, checked_rows, checked_headers, file_path_col, ayon_path_col, version_col, item_map)
            
        # Clearly communicate to the user that the item was ingested (OK/FAIL)
        ok_count = check_results.count("OK")
        fail_count = len(check_results) - ok_count
        
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("AYON Ingest Check Summary")
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
            }
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #555555;
                padding: 5px 15px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        
        summary_text = "<h3>AYON Ingest Verification Complete</h3>"
        summary_text += f"<p><b>Total checked:</b> {len(check_results)}<br/>"
        summary_text += f"<span style='color: #4caf50;'><b>Successfully Ingested (OK):</b> {ok_count}</span><br/>"
        if fail_count > 0:
            summary_text += f"<span style='color: #f44336;'><b>Failed Ingest Check:</b> {fail_count}</span></p>"
        else:
            summary_text += f"<span style='color: #4caf50;'><b>All items ingested perfectly!</b></span></p>"
            
        if fail_count > 0:
            summary_text += "<p><b>Ingest failure details:</b><ul style='color: #f44336;'>"
            for r in check_results:
                if r != "OK":
                    summary_text += f"<li>{r}</li>"
            summary_text += "</ul></p>"
            
        import html as html_lib
        summary_text += f"<p><b>Ingest log:</b> {html_lib.escape(new_csv_path if os.path.exists(new_csv_path) else csv_path)}"
        if getattr(self, "_last_report_path", None):
            summary_text += f"<br/><b>PDF report:</b> {html_lib.escape(self._last_report_path)}"
        summary_text += "</p>"
        msg.setText(summary_text)

        # Sound is optional (Preferences > General > Play notification sounds, default off).
        # A QMessageBox with a standard icon makes Windows play its own alert sound,
        # so when sounds are off we show the same icon as a plain pixmap instead.
        if fail_count > 0:
            std_icon = QStyle.SP_MessageBoxWarning
        else:
            std_icon = QStyle.SP_MessageBoxInformation
        if self.config.get("play_sounds", False):
            msg.setIcon(QMessageBox.Warning if fail_count > 0 else QMessageBox.Information)
            play_notification_sound(self.config, error=fail_count > 0)
        else:
            msg.setIconPixmap(self.style().standardIcon(std_icon).pixmap(48, 48))

        msg.exec()

        # Hide the LOG window when pressing OK / closing the summary popup
        self.log_console.hide()
        self.btn_toggle_log.setChecked(False)

        self.model.layoutChanged.emit()

    def generate_ingest_pdf_report(self, pdf_path, checked_rows, headers, file_path_col, ayon_path_col, version_col, item_map):
        self.log_message(f"Generating Ingest PDF report: {os.path.basename(pdf_path)}...", "info")
        
        try:
            import datetime
            from datetime import timezone, timedelta
            
            # 1. Parse timezone offsets
            def parse_offset_to_hours(offset_str):
                import re
                if not offset_str:
                    return 0.0
                offset_str = str(offset_str).strip()
                match = re.match(r'^([+-]?)(\d+)(?::(\d+))?$', offset_str)
                if match:
                    sign = -1 if match.group(1) == '-' else 1
                    hours = int(match.group(2))
                    minutes = int(match.group(3)) if match.group(3) else 0
                    return sign * (hours + minutes / 60.0)
                try:
                    return float(offset_str)
                except ValueError:
                    return 0.0

            tz_a = self.config.get("timezone_offset_a", "+00:00")
            tz_b = self.config.get("timezone_offset_b", "+00:00")
            
            # Local time A: do not subtract the offset A, just display the local system time of the app
            local_now = datetime.datetime.now()
            date_time_a = local_now.strftime("%Y-%m-%d %H:%M") + f" {tz_a}"
            
            # Client time B: convert to UTC, then apply client offset B
            utc_now = datetime.datetime.now(timezone.utc)
            hours_b = parse_offset_to_hours(tz_b)
            time_b = utc_now + timedelta(hours=hours_b)
            date_time_b = time_b.strftime("%Y-%m-%d %H:%M") + f" {tz_b}"

            # 2. All published rows; the last column is the check result
            import html as html_lib
            esc = lambda v: html_lib.escape(str(v)) if v is not None else ""
            report_rows = [r for r in checked_rows if r]
            if not report_rows:
                self.log_message("Nothing was published; no PDF report written.", "warning")
                return
            ok_count = sum(1 for r in report_rows if r[-1] == "OK")
            thumb_resources = []  # (name, QImage): QTextDocument does not render data: URLs

            # Find Variant column in headers case-insensitively
            variant_col = -1
            for idx, h in enumerate(headers):
                if h.lower().strip() == "variant":
                    variant_col = idx
                    break

            # 3. Build HTML
            html_rows = []
            for row in report_rows:
                file_path_val = row[file_path_col] if file_path_col >= 0 else ""
                ayon_path_val = row[ayon_path_col] if ayon_path_col >= 0 else ""
                version_val = row[version_col] if version_col >= 0 else ""
                
                filename = os.path.basename(file_path_val) if file_path_val else ""
                
                # Fetch matched item properties
                matched_item = None
                if file_path_val:
                    norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                    matched_item = item_map.get(norm_f)
                
                variant_val = ""
                if matched_item:
                    variant_val = matched_item.effective_variant
                elif variant_col >= 0 and variant_col < len(row):
                    variant_val = row[variant_col]

                length = "1"
                frame_start = "-"
                frame_end = "-"
                b64_image = ""
                
                if matched_item:
                    # Frame range for sequences and videos (stills stay "-")
                    fs, fe = matched_item.frame_start, matched_item.frame_end
                    if (matched_item.is_sequence or matched_item.category == "Video") and \
                            isinstance(fs, int) and isinstance(fe, int):
                        frame_start, frame_end = str(fs), str(fe)
                        length = str(fe - fs + 1)
                    
                    # Thumbnail as a document resource (kept with its aspect ratio)
                    if matched_item.thumbnail and not matched_item.thumbnail.isNull():
                        from PySide6.QtCore import Qt
                        scaled_thumb = matched_item.thumbnail.scaled(75, 75, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        b64_image = f"thumb_{len(thumb_resources)}.png"
                        thumb_resources.append((b64_image, scaled_thumb.toImage()))
                
                # Render Thumbnail cell
                if b64_image:
                    thumb_html = f'<img src="{b64_image}" />'
                else:
                    thumb_html = '<div style="width: 75px; height: 75px; background-color: #eaeaea; border: 1px solid #cccccc; border-radius: 4px; text-align: center; line-height: 75px; color: #888888; font-size: 10px;">No Image</div>'
                
                status_color = "#2e7d32" if row[-1] == "OK" else "#c62828"  # (no nested quotes in f-strings: Python 3.9)
                html_rows.append(f"""
                <tr>
                    <td style="padding: 8px; text-align: center; border-bottom: 1px solid #eeeeee;">{thumb_html}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; word-break: break-all;">{esc(filename)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee;">{esc(variant_val)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee;">{esc(ayon_path_val)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">v{esc(version_val)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{length}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{frame_start}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{frame_end}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; color: {status_color};">{esc(row[-1])}</td>
                </tr>
                """)
            
            rows_html = "\n".join(html_rows)
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        color: #333333;
                        margin: 0;
                        padding: 0;
                    }}
                    h1 {{
                        font-size: 24pt;
                        color: #111111;
                        margin: 0 0 8px 0;
                    }}
                    .subtitle {{
                        font-size: 11pt;
                        color: #666666;
                        margin: 0 0 20px 0;
                        line-height: 1.4;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                    }}
                    th {{
                        background-color: #f7f7f7;
                        border-bottom: 2px solid #dddddd;
                        color: #222222;
                        font-weight: bold;
                        font-size: 11pt;
                        padding: 8px;
                        text-align: left;
                    }}
                    td {{
                        font-size: 10pt;
                        padding: 8px;
                        border-bottom: 1px solid #eeeeee;
                        vertical-align: middle;
                    }}
                </style>
            </head>
            <body>
                <h1>Ingest Report</h1>
                <div class="subtitle">
                    <strong>Local:</strong> {date_time_a}<br/>
                    <strong>Client:</strong> {date_time_b}<br/>
                    <strong>Items:</strong> {len(report_rows)} published, {ok_count} confirmed in AYON
                </div>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 85px; text-align: center;">Thumbnail</th>
                            <th>File Name</th>
                            <th>Variant</th>
                            <th>Ayon Folder</th>
                            <th style="width: 55px; text-align: center;">Version</th>
                            <th style="width: 70px; text-align: center;">Length (frames)</th>
                            <th style="width: 65px; text-align: center;">Frame Start</th>
                            <th style="width: 65px; text-align: center;">Frame End</th>
                            <th>Check</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </body>
            </html>
            """
            
            # 4. Write to PDF using QPdfWriter
            from PySide6.QtGui import QPdfWriter, QTextDocument, QPageLayout, QPageSize
            from PySide6.QtCore import QMarginsF
            
            writer = QPdfWriter(pdf_path)
            writer.setPageSize(QPageSize(QPageSize.A4))
            
            # Landscape orientation with half-sized margins (7.5mm)
            layout = QPageLayout(
                QPageSize(QPageSize.A4),
                QPageLayout.Landscape,
                QMarginsF(7.5, 7.5, 7.5, 7.5),
                QPageLayout.Millimeter
            )
            writer.setPageLayout(layout)
            
            doc = QTextDocument()
            doc.setHtml(html_content)
            from PySide6.QtCore import QUrl
            for res_name, res_img in thumb_resources:
                doc.addResource(QTextDocument.ImageResource, QUrl(res_name), res_img)
            doc.print_(writer)
            del writer  # finalise the PDF file now, not at garbage collection
            
            self._last_report_path = pdf_path
            self.log_message(f"Ingest PDF report written: {pdf_path}", "success")
        except Exception as e:
            self.log_message(f"Failed to generate Ingest PDF report: {e}", "error")

    def _get_tagged_for_ingest(self):
        v_stack_enabled = getattr(self.model, "v_stack_enabled", False)
        tagged_items = [
            item for item in self.model.items 
            if item.is_tagged and (not v_stack_enabled or self.model.is_item_visible_by_v_stack(item, True))
        ]
        if not tagged_items:
            QMessageBox.warning(self, "Ingest", "No images tagged for ingest.")
            return None
        return tagged_items

    def _write_csv_from_preview(self, items, csv_path):
        """Write items to CSV using the column definitions from CSVPreviewModel."""
        column_defs = self.csv_preview_model.column_defs
        delimiter = self.config.get("csv_delimiter", ",")
        quotechar = self.config.get("csv_quotechar", '"')
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
            writer.writerow([h for h, t in column_defs])
            for item in items:
                row_data = []
                for h, template in column_defs:
                    val = self.model.expand_tokens(template, item)
                    row_data.append(val)
                writer.writerow(row_data)

    def perform_duplicate_check(self):
        """Identify items sharing same {ayon_path}{product_name}{version} strings."""
        self.log_message("Starting duplicate check...")
        
        is_csv = self.spreadsheet._is_csv_mode
        
        # 1. Gather candidate items based on criteria
        # - tagged on
        # - valid AYON path assigned (only required if not in CSV mode)
        # - visible according to current UI filters
        candidates = []
        for item in self.model.items:
            item.is_duplicate = False # Reset status for all
            
            if not item.is_tagged:
                continue
            
            if not is_csv and not item.ayon_path:
                continue
            
            if not is_csv:
                # Check if fits the right filter panel
                age_min = item.age_minutes
                label = item.label
                matches_search = not self._search_filter_text or self._search_filter_text in label.lower()
                matches_age = not self._age_filter_enabled or (age_min < self._age_filter_value)
                
                if not (matches_search and matches_age):
                    continue
            
            candidates.append(item)

        if not candidates:
            self.log_message("No candidate items (tagged, assigned, and filtered) for duplicate check.", "warning")
            self.model.layoutChanged.emit()
            if is_csv:
                self.csv_preview_model._refresh_data()
            return

        # 2. Group by identity string using configurable template via _check_duplicates_in_list
        duplicate_set, dup_groups = self._check_duplicates_in_list(candidates)
        for item in duplicate_set:
            item.is_duplicate = True

        # 3. Refresh view to show updated {is_duplicate} in Key Value Pairs column
        self.model.layoutChanged.emit()
        if is_csv:
            self.csv_preview_model._refresh_data()
        
        if dup_groups:
            total_dup_items = sum(len(g) for g in dup_groups.values())
            self.log_message(f"Duplicate check complete: Found {total_dup_items} items sharing {len(dup_groups)} unique identities.", "warning")
            msg = f"Found {total_dup_items} duplicate items sharing {len(dup_groups)} unique identities:\n\n"
            for identity, group in dup_groups.items():
                items_str = ", ".join([f"'{it.label}' ({it.filename})" for it in group])
                self.log_message(f"  - Duplicate identity [{identity}]: {items_str}", "warning")
                msg += f"• Identity [{identity}]:\n"
                for it in group:
                    msg += f"   - {it.label} ({it.filename})\n"
            
            self.select_items(list(duplicate_set))
            msg += "\nThe duplicate items have been selected in the interface."
            QMessageBox.warning(self, "Duplicate Check", msg)
        else:
            self.log_message("Duplicate check complete: No duplicates found among candidate items.", "success")
            show_info(self, "Duplicate Check", "No duplicate items found.", self.config)

    def perform_version_collision_check(self, fix=False):
        """Batch check current versions in AYON for tagged and filtered items."""
        project = self.ayon_panel.combo_project.currentText()
        if not project: 
            self.log_message("No project selected for version check.", "warning")
            return
        
        is_csv = self.spreadsheet._is_csv_mode
        
        # 1. Gather candidate items based on criteria
        candidates = []
        for item in self.model.items:
            if not (item.is_tagged and item.ayon_path):
                continue
            
            if not is_csv:
                # Check if fits the right filter panel
                age_min = item.age_minutes
                label = item.label
                matches_search = not self._search_filter_text or self._search_filter_text in label.lower()
                matches_age = not self._age_filter_enabled or (age_min < self._age_filter_value)
                
                if not (matches_search and matches_age):
                    continue
            
            candidates.append(item)

        self.log_message(f"Version Check: Found {len(candidates)} candidate items.")

        if not candidates:
            self.log_message("No candidate items (tagged, assigned, and filtered) for version collision check.", "warning")
            return
        
        path_map = self.ayon_panel.get_path_to_id_map()
        folder_ids = set()
        items_to_check = []
        
        for item in candidates:
            # ayon_path is /Project/Folder/Task - we need the folder path
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            
            variant = self.model.variant_value(item)
            prod_name = self.model.product_name(item)
            
            self.log_message(f"Debug Item: {item.filename} | Variant: {variant} | Product: {prod_name}", "info")
            
            if f_id:
                folder_ids.add(f_id)
                items_to_check.append((item, f_id, prod_name))
            else:
                self.log_message(f"Debug: Could not find folder ID for path '{folder_path}' in path_map", "warning")

        if not folder_ids:
            self.log_message(f"Could not resolve any AYON folder IDs. Path map size: {len(path_map)}", "error")
            return
            
        self.log_message(f"Checking AYON versions for {len(candidates)} items across {len(folder_ids)} folders...")
        
        if hasattr(self, "_ver_thread") and self._ver_thread.isRunning():
            try:
                self._ver_thread.finished.disconnect()
            except Exception:
                pass
            # (no terminate(): killing a thread mid-request can corrupt the AYON connection;
            #  it is disconnected above and kept alive below until it finishes)
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._ver_thread)

        class VersionThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project, f_ids):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.f_ids = f_ids
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull last versions for {len(self.f_ids)} folder IDs in project '{self.project}' from AYON...")
                versions = self.ayon.get_last_versions(self.project, self.f_ids)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling last versions for folder IDs in project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(versions)

        self._ver_thread = VersionThread(self.ayon, project, list(folder_ids))
        self._ver_thread.finished.connect(lambda v_map: self._on_versions_fetched(v_map, items_to_check, fix=fix))
        self._ver_thread.start()

    def _on_versions_fetched(self, v_map, items_to_check, fix=False):
        updated = 0
        collision_mode = self.config.get("version_collision", "fail")
        
        self.log_message(f"Debug: Received {len(v_map)} product versions from AYON.")
        
        for item, f_id, prod_name in items_to_check:
            # Key is f"{f_id}|{prod_name}|{prod_type}"
            key = f"{f_id}|{prod_name}|{item.product_type}"
            last_v = v_map.get(key)
            
            if last_v is not None:
                item.last_ayon_version = last_v
                item.version_collision = (last_v >= item.version)
                
                if fix:
                    eff_ver = item.effective_version
                    if last_v >= eff_ver or collision_mode == "lowest":
                        item.version_user = str(last_v + 1)
                    
                updated += 1
            else:
                # Debug log for missing product
                if len(v_map) > 0:
                    self.log_message(f"Debug: No match for {prod_name} ({item.product_type}) in folder {f_id}", "info")
                item.last_ayon_version = 0 
                item.version_collision = None 
        
        # Refresh Version (9), Version User (10), Last Version (11), and Key Value Pairs (15) columns
        self.model.dataChanged.emit(
            self.model.index(0, 9), 
            self.model.index(len(self.model.items)-1, 15)
        )
        if self.spreadsheet._is_csv_mode:
            self.csv_preview_model._refresh_data()
        self.log_message(f"Version check complete. Updated {updated} items.", "success")
