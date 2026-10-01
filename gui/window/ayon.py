"""AYON connection, hierarchy, assignment, thumbnails, representations, auto-assign.

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


class AyonMixin:
    def _on_project_changed(self, project_name):
        """Called when user selects a different project in the top bar."""
        if not project_name or not self.ayon.is_connected:
            return
            
        # Clear "not available" states
        self.ayon_thumb_states = {k: v for k, v in self.ayon_thumb_states.items() if v != "not available"}
        self.save_ayon_thumb_states()
        
        # Save last project to config
        self.config["ayon_project"] = project_name
        self.config["last_ayon_project"] = project_name
        self.save_config()
        
        self.refresh_hierarchy_async(project_name)

    def refresh_ayon(self):
        self.refresh_ayon_async(reconnect=False)

    def refresh_ayon_async(self, reconnect=False):
        """Asynchronously connect and refresh AYON projects list."""
        if hasattr(self, "_conn_thread") and self._conn_thread.isRunning():
            return
            
        # Clear "not available" states so we can retry them
        self.ayon_thumb_states = {k: v for k, v in self.ayon_thumb_states.items() if v != "not available"}
        self.save_ayon_thumb_states()
            
        # Force a reconnect if we aren't connected yet
        if not self.ayon.is_connected:
            reconnect = True
            
        self.ayon_panel.set_connection_status(self.ayon.is_connected, self.ayon.server_url)
        
        # A previous connection attempt may still be running: never drop the last
        # reference to a running QThread (Qt aborts), and ignore its late result.
        if getattr(self, "_conn_thread", None) is not None and self._conn_thread.isRunning():
            try:
                self._conn_thread.finished.disconnect()
            except Exception:
                pass
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._conn_thread)

        class ConnectionThread(QThread):
            finished = Signal(bool, list)
            def __init__(self, ayon, url, key, do_connect):
                super().__init__()
                self.ayon = ayon
                self.url = url
                self.key = key
                self.do_connect = do_connect
            def run(self):
                import time
                start_t = time.perf_counter()
                print("[Timer] Starting to pull projects list from AYON...")
                if self.do_connect:
                    print(f"[Timer] Connecting to AYON server at {self.url}...")
                    self.ayon.connect(self.url, self.key)
                projects = self.ayon.get_projects()
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling projects list from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(self.ayon.is_connected, projects)

        server_url = self.secrets.get("ayon_server_url", "").strip()
        api_key = self.secrets.get("ayon_api_key", "").strip()
        if not api_key: # Fallback
            api_key = self.config.get("ayon_api_key", "").strip()
        
        self._conn_thread = ConnectionThread(self.ayon, server_url, api_key, reconnect)
        self._conn_thread.finished.connect(self._on_ayon_refreshed)
        self._conn_thread.start()

    def _on_ayon_refreshed(self, is_connected, projects):
        """Called when project list refresh is done."""
        self.ayon_panel.set_connection_status(is_connected, self.ayon.server_url)
        
        # Block signals to avoid feedback loop when setting project list
        self.ayon_panel.combo_project.blockSignals(True)
        current = self.ayon_panel.combo_project.currentText()
        if not current:
            current = self.config.get("ayon_project") or self.config.get("last_ayon_project")
            
        self.ayon_panel.set_projects(projects)
        if current in projects:
            self.ayon_panel.combo_project.setCurrentText(current)
        self.ayon_panel.combo_project.blockSignals(False)
        
        if is_connected:
            project = self.ayon_panel.combo_project.currentText()
            if project:
                self.refresh_hierarchy_async(project)
 
    def refresh_hierarchy_async(self, project_name):
        """Asynchronously fetch folder hierarchy for a specific project."""
        if hasattr(self, "_last_fetched_project") and self._last_fetched_project == project_name:
            if hasattr(self, "_hier_thread") and self._hier_thread.isRunning():
                return
        self._last_fetched_project = project_name
        
        if hasattr(self, "_hier_thread") and self._hier_thread.isRunning():
            try:
                self._hier_thread.finished.disconnect()
            except Exception:
                pass
            # (no terminate(): killing a thread mid-request can corrupt the AYON connection;
            #  it is disconnected above and kept alive below until it finishes)
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._hier_thread)
            
        class HierarchyThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project):
                super().__init__()
                self.ayon = ayon
                self.project = project
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull folder hierarchy for project '{self.project}' from AYON...")
                hierarchy = self.ayon.get_project_hierarchy(self.project)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling folder hierarchy for project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(hierarchy)
 
        self._hier_thread = HierarchyThread(self.ayon, project_name)
        self._hier_thread.finished.connect(self.ayon_panel.set_hierarchy)
        self._hier_thread.finished.connect(self._update_ayon_visuals)
        self._hier_thread.finished.connect(self._restore_ayon_selection)
        self._hier_thread.finished.connect(self._refresh_ayon_panel_icons)
        self._hier_thread.finished.connect(self.trigger_ayon_thumbnail_downloads)
        self._hier_thread.start()

    def _restore_ayon_selection(self):
        folder = self.config.get("ayon_selected_folder")
        task = self.config.get("ayon_selected_task")
        if folder:
            self.ayon_panel.select_path(folder, task)

    def _on_ayon_task_selected(self, folder_path, task_name, task_type, assignee="", task_data=None):
        """Assign AYON path to selected items."""
        # Get selected rows robustly
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        if not selected_rows:
            # Check thumbnails fallback
            selected_thumbs = self.thumb_area.scene.selectedItems()
            if selected_thumbs:
                for thumb in selected_thumbs:
                    try:
                        row = self.model.items.index(thumb.data)
                        selected_rows.append(row)
                    except ValueError: continue
                selected_rows = sorted(list(set(selected_rows)))

        if not selected_rows:
            self.log_message("No images selected to assign path to.", "warning")
            return
            
        ayon_path = f"{folder_path}/{task_name}"
        for row in selected_rows:
            item = self.model.items[row]
            item.ayon_path = ayon_path
            item.ayon_task_name = task_name
            item.ayon_task_type = task_type
            item.ayon_task_assignee = assignee
            
            item.metadata["folder_path"] = folder_path
            if task_data:
                item.metadata["folder_name"] = task_data.get("folder_name") or task_data.get("name", "")
                item.metadata["folder_type"] = task_data.get("folder_type", "")
                item.metadata["folder_status"] = task_data.get("folder_status", "")
                item.metadata["folder_description"] = task_data.get("folder_description", "")
                item.metadata["task_name"] = task_data.get("task_name") or task_data.get("name") or task_name
                item.metadata["task_type"] = task_data.get("task_type") or task_data.get("type") or task_type
                item.metadata["task_description"] = task_data.get("task_description") or task_data.get("description") or task_data.get("attrib", {}).get("description", "")
                item.metadata["task_status"] = task_data.get("task_status") or task_data.get("status", "")
            if hasattr(item, "remember_ayon_context"):
                item.remember_ayon_context()
            
        # Notify the model that the AYON Path column (14) has changed for these rows
        start_idx = self.model.index(min(selected_rows), 14)
        end_idx = self.model.index(max(selected_rows), 14)
        self.model.dataChanged.emit(start_idx, end_idx)
        
        # Feedback
        self.log_message(f"Assigned '{ayon_path}' to {len(selected_rows)} items.")

    def _on_ayon_product_selected(self, folder_path, task_name, task_type, variant, task_data=None):
        """Assign AYON path AND update label to variant for selected items."""
        # 1. Set the AYON path (reuse existing logic)
        self._on_ayon_task_selected(folder_path, task_name, task_type, task_data=task_data)
        
        # 2. Update the labels for the same selected items
        # Re-fetching selection to be safe, though _on_ayon_task_selected doesn't clear it
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        # Fallback to thumbs selection
        if not selected_rows:
            selected_thumbs = self.thumb_area.scene.selectedItems()
            if selected_thumbs:
                for thumb in selected_thumbs:
                    try:
                        row = self.model.items.index(thumb.data)
                        selected_rows.append(row)
                    except ValueError: continue
                selected_rows = sorted(list(set(selected_rows)))
                
        if not selected_rows:
            return
            
        for row in selected_rows:
            item = self.model.items[row]
            item.label = variant
            
        # Notify model that Label column (2) has changed
        start_idx = self.model.index(min(selected_rows), 2)
        end_idx = self.model.index(max(selected_rows), 2)
        self.model.dataChanged.emit(start_idx, end_idx)
        
        # Feedback
        self.log_message(f"Updated labels to '{variant}' for {len(selected_rows)} items.", "success")

    def _update_ayon_visuals(self):
        """Highlight assigned tasks in the AYON panel."""
        assigned_paths = set(item.ayon_path for item in self.model.items if item.ayon_path)
        if hasattr(self, "_last_assigned_paths") and self._last_assigned_paths == assigned_paths:
            self.update_ayon_thumbnails()
            return
        self._last_assigned_paths = assigned_paths
        self.ayon_panel.update_assigned_status(assigned_paths)
        self.update_ayon_thumbnails()

    def _on_ayon_unassign(self, ayon_path):
        """Clear AYON path for all items assigned to this path."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path == ayon_path:
                item.clear_ayon_assignment()
                affected += 1
        
        if affected:
            self.model.dataChanged.emit(self.model.index(0, 9), self.model.index(len(self.model.items)-1, 9))
            self.log_message(f"Unassigned '{ayon_path}' from {affected} items.")
            # Bold status will update via dataChanged signal -> _update_ayon_visuals

    def _on_ayon_select_assigned(self, ayon_path):
        """Select all items that have this AYON path."""
        is_csv = self.spreadsheet._is_csv_mode
        target_model = self.csv_preview_model if is_csv else self.model
        items_list = self.csv_preview_model.tagged_items if is_csv else self.model.items
        
        selection_model = self.spreadsheet.table.selectionModel()
        selection_model.clearSelection()
        
        selection = QItemSelection()
        first_idx = None
        count = 0
        
        for i, item in enumerate(items_list):
            if item.ayon_path == ayon_path:
                idx = target_model.index(i, 0)
                # Select the full row
                tl = target_model.index(i, 0)
                br = target_model.index(i, target_model.columnCount() - 1)
                selection.select(tl, br)
                if first_idx is None: first_idx = idx
                count += 1
        
        if not selection.isEmpty():
            selection_model.select(selection, QItemSelectionModel.Select)
            if first_idx:
                self.spreadsheet.table.scrollTo(first_idx)
            self.log_message(f"Selected {count} items assigned to '{ayon_path}'.")
            
            # Sync to Thumbs and Filter Panel
            self._sync_selection_to_thumbs()
        else:
            self.log_message(f"No items assigned to '{ayon_path}' found.", "warning")

    def _on_ayon_clear_all(self):
        """Reset all AYON path assignments."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path:
                item.clear_ayon_assignment()
                affected += 1
        
        if affected:
            # Column 14 is AYON Path
            self.model.dataChanged.emit(self.model.index(0, 14), self.model.index(len(self.model.items)-1, 14))
            self.log_message(f"Cleared all AYON assignments from {affected} items.", "warning")

    def _on_ayon_info_requested(self, folder_id):
        """Lazy load products for the selected folder."""
        project = self.ayon_panel.combo_project.currentText()
        if not project: return
        
        if hasattr(self, "_prod_thread") and self._prod_thread.isRunning():
            try:
                self._prod_thread.finished.disconnect()
            except Exception:
                pass
            # (no terminate(): killing a thread mid-request can corrupt the AYON connection;
            #  it is disconnected above and kept alive below until it finishes)
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._prod_thread)

        class ProductThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project, f_id):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.f_id = f_id
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull products for folder ID '{self.f_id}' in project '{self.project}' from AYON...")
                products = self.ayon.get_products_for_folder(self.project, self.f_id)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling products for folder ID '{self.f_id}' in project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(products)

        self._prod_thread = ProductThread(self.ayon, project, folder_id)
        self._prod_thread.finished.connect(self.ayon_panel.set_products)
        self._prod_thread.start()

    def _on_show_thumbs_toggled(self, checked):
        print(f"[Debug] Show Thumbs toggled: {checked}")
        self.log_message(f"[Debug] Show Thumbs toggled: {checked}", "info")
        self.model.show_thumbs = checked
        if checked:
            self.update_ayon_thumbnails()
            self.trigger_ayon_thumbnail_downloads()
        self.model.layoutChanged.emit()
        self._refresh_ayon_panel_icons()

    def _get_ayon_thumb_cache_root(self):
        cache_root = self.secrets.get("ayon_thumbnails_cache", "")
        if not cache_root:
            cache_root = "_ayon_thumbs_cache"
        from utils import expand_env_vars
        cache_root = expand_env_vars(cache_root)
        if not os.path.isabs(cache_root):
            cache_root = os.path.abspath(cache_root)
        return cache_root

    def _refresh_ayon_panel_icons(self):
        show_thumbs = self.ayon_panel.btn_show_thumbs.isChecked()
        cache_root = self._get_ayon_thumb_cache_root()
        
        project_name = self.ayon_panel.combo_project.currentText()
        if project_name:
            self.ayon_panel.refresh_icons(show_thumbs, cache_root, project_name)

    def trigger_ayon_thumbnail_downloads(self):
        if not self.config.get("get_ayon_thumbnails", True):
            self.log_message("AYON task thumbnails download is disabled in preferences.", "info")
            return

        if not self.ayon_panel.btn_show_thumbs.isChecked():
            return

        project_name = self.ayon_panel.combo_project.currentText()
        if not project_name:
            return

        # Find all task thumbnail IDs from the current tree
        tasks_info = []
        def _recurse_model(parent_item):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item:
                    continue
                data = item.data(Qt.UserRole)
                if data and "folderId" in data: # It's a task!
                    thumb_id = data.get("thumbnailId")
                    if thumb_id:
                        tasks_info.append({
                            "name": data.get("name"),
                            "thumbnailId": thumb_id
                        })
                _recurse_model(item)

        _recurse_model(self.ayon_panel.model.invisibleRootItem())
        
        if not tasks_info:
            return
            
        if hasattr(self, "_ayon_thumb_download_thread") and self._ayon_thumb_download_thread.isRunning():
            return # Let the current run finish
            
        cache_root = self._get_ayon_thumb_cache_root()
        project_cache_dir = os.path.join(cache_root, project_name)
        
        # Filter tasks_info based on local disk state and known states
        filtered_tasks_info = []
        changed = False
        for info in tasks_info:
            thumb_id = info["thumbnailId"]
            target_path = os.path.join(project_cache_dir, f"{thumb_id}.jpg")
            
            if os.path.exists(target_path):
                if self.ayon_thumb_states.get(thumb_id) != "cached":
                    self.ayon_thumb_states[thumb_id] = "cached"
                    changed = True
                continue
                
            state = self.ayon_thumb_states.get(thumb_id)
            if state in ("not available", "downloading"):
                continue
                
            filtered_tasks_info.append(info)
            self.ayon_thumb_states[thumb_id] = "downloading"
            changed = True
            
        if changed:
            self.save_ayon_thumb_states()
            
        if not filtered_tasks_info:
            self._refresh_ayon_panel_icons()
            return
            
        self._ayon_thumb_download_thread = AyonThumbnailDownloadThread(
            project_name, filtered_tasks_info, project_cache_dir
        )
        self._ayon_thumb_download_thread.log.connect(lambda msg: self.log_message(msg, "info"))
        self._ayon_thumb_download_thread.state_changed.connect(self._on_task_thumb_state_changed)
        self._ayon_thumb_download_thread.finished.connect(self._refresh_ayon_panel_icons)
        self._ayon_thumb_download_thread.start()

    def load_ayon_thumb_states(self):
        cache_root = self._get_ayon_thumb_cache_root()
        os.makedirs(cache_root, exist_ok=True)
        
        path = os.path.join(cache_root, "ayon_thumb_states.json")
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    self.ayon_thumb_states = json.load(f)
                print(f"[Prefs] Loaded AYON thumbnail states from: {path}")
            except Exception as e:
                print(f"Error loading AYON thumbnail states: {e}")
                self.ayon_thumb_states = {}
        else:
            self.ayon_thumb_states = {}

    def save_ayon_thumb_states(self):
        cache_root = self._get_ayon_thumb_cache_root()
        os.makedirs(cache_root, exist_ok=True)
        
        path = os.path.join(cache_root, "ayon_thumb_states.json")
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.ayon_thumb_states, f, indent=4)
        except Exception as e:
            print(f"Error saving AYON thumbnail states: {e}")

    def _on_task_thumb_state_changed(self, thumb_id, state):
        self.ayon_thumb_states[thumb_id] = state
        self.save_ayon_thumb_states()


    def update_ayon_thumbnails(self):
        if not getattr(self.model, "show_thumbs", False):
            return
            
        project = self.ayon_panel.combo_project.currentText()
        if not project:
            return
            
        path_map = self.ayon_panel.get_path_to_id_map()
        if not path_map:
            return
            
        changed = False
        for item in self.model.items:
            if not item.ayon_path:
                print(f"debug: ayon_path is empty for item: {item}")
                continue
                
            # ayon_path is /Project/Folder/Task - we need the folder path
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            
            if not f_id:
                print(f"debug: f_id not found for folder path '{folder_path}' in path_map")
                continue
                
            if f_id in self.ayon_thumb_cache:
                print(f"debug: f_id '{f_id}' found in ayon_thumb_cache for item: {item}")
                item.ayon_thumbnail = self.ayon_thumb_cache[f_id]
                continue
                
            # Check local file first
            try:
                local_thumb_path = self._get_ayon_thumb_path(item)
                if os.path.exists(local_thumb_path):
                    from PySide6.QtGui import QPixmap
                    pixmap = QPixmap(local_thumb_path)
                    if not pixmap.isNull():
                        self.ayon_thumb_cache[f_id] = pixmap
                        if self.ayon_thumb_states.get(f_id) != "cached":
                            self.ayon_thumb_states[f_id] = "cached"
                            changed = True
                        item.ayon_thumbnail = pixmap
                        item.thumbnail = pixmap
                        continue
            except Exception as e:
                print(f"Error checking/loading local thumbnail: {e}")
                
            state = self.ayon_thumb_states.get(f_id)
            if state in ("not available", "downloading", "downloaded", "cached"):
                continue
                
            # If not cached and not currently downloading, start download
            print(f"Downloading thumbnail for folder ID '{f_id}' in project '{project}' from AYON...")
            self.ayon_thumb_states[f_id] = "downloading"
            changed = True
            self.ayon_thumb_downloading.add(f_id)
            
            # Start background thread
            thread = AyonFolderThumbnailThread(self.ayon, project, f_id)
            thread.download_finished.connect(self._on_ayon_thumbnail_downloaded)
            # Keep thread reference
            self._thumb_threads.append(thread)
            thread.start()

        if changed:
            self.save_ayon_thumb_states()

    def _get_ayon_thumb_path(self, item):
        """Construct a thumbnail path using AYON folder path, replacing slashes with dashes, adding suffix '_thumbAyon'."""
        import os
        source_file = item.file_path.replace("\\", "/")
        base_dir = os.path.dirname(source_file)
        
        target_dir = base_dir
        thumb_loc = self.config.get("thumb_location", "Relative to Source Folder")
        thumb_loc_path = self.config.get("thumb_location_path", "_thumbs")
        
        if thumb_loc == "Relative to Source Folder":
            if self.model.source_folder:
                target_dir = os.path.join(self.model.source_folder, thumb_loc_path).replace("\\", "/")
        elif thumb_loc == "Custom":
            target_dir = thumb_loc_path.replace("\\", "/")
            
        # Get AYON folder path
        folder_path = "/".join(item.ayon_path.split("/")[:-1])
        clean_path = folder_path.strip("/")
        dashed_path = clean_path.replace("/", "-")
        
        # Suffix and format
        ext = self.config.get("thumb_format", ".jpg")
        target_filename = f"{dashed_path}_thumbAyon{ext}"
        
        return os.path.join(target_dir, target_filename).replace("\\", "/")

    def _on_ayon_thumbnail_downloaded(self, folder_id, data):
        # Remove completed threads from tracking
        self._thumb_threads = [t for t in self._thumb_threads if t.isRunning()]
        
        if folder_id in self.ayon_thumb_downloading:
            self.ayon_thumb_downloading.remove(folder_id)
            
        if data:
            from PySide6.QtGui import QImage, QPixmap
            image = QImage()
            if image.loadFromData(data):
                pixmap = QPixmap.fromImage(image)
                # Cache it
                self.ayon_thumb_cache[folder_id] = pixmap
                self.ayon_thumb_states[folder_id] = "downloaded"
                
                # Assign to all items with matching folder path
                path_map = self.ayon_panel.get_path_to_id_map()
                if path_map:
                    for item in self.model.items:
                        if item.ayon_path:
                            folder_path = "/".join(item.ayon_path.split("/")[:-1])
                            f_id = path_map.get(folder_path)
                            if f_id == folder_id:
                                item.ayon_thumbnail = pixmap
                                try:
                                    local_thumb_path = self._get_ayon_thumb_path(item)
                                    import os
                                    os.makedirs(os.path.dirname(local_thumb_path), exist_ok=True)
                                    print(f"[Debug] Storing AYON thumbnail locally to: {local_thumb_path}")
                                    self.log_message(f"[Debug] Storing AYON thumbnail locally to: {local_thumb_path}", "info")
                                    with open(local_thumb_path, "wb") as f:
                                        f.write(data)
                                    item.thumbnail = pixmap
                                except Exception as e:
                                    print(f"Failed to save AYON thumbnail locally: {e}")
                
                # Refresh views
                self.model.layoutChanged.emit()
                if self.spreadsheet._is_csv_mode:
                    self.csv_preview_model._refresh_data()
            else:
                self.ayon_thumb_states[folder_id] = "not available"
        else:
            self.ayon_thumb_states[folder_id] = "not available"
        self.save_ayon_thumb_states()

    def _on_ayon_representations_requested(self, project, product_id):
        """Asynchronously load representations for the selected product."""
        if not project or not product_id:
            return
            
        if hasattr(self, "_repre_thread") and self._repre_thread.isRunning():
            try:
                self._repre_thread.finished.disconnect()
            except Exception:
                pass
            # (no terminate(): killing a thread mid-request can corrupt the AYON connection;
            #  it is disconnected above and kept alive below until it finishes)
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._repre_thread)

        class RepreThread(QThread):
            finished = Signal(list)
            def __init__(self, ayon, project, prod_id):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.prod_id = prod_id
            def run(self):
                import time
                import ayon_api
                try:
                    start_t = time.perf_counter()
                    print(f"[Timer] Starting to pull representations for product ID '{self.prod_id}' in project '{self.project}' from AYON...")
                    
                    # 1. Fetch versions for this product
                    versions = list(ayon_api.get_versions(self.project, product_ids=[self.prod_id]))
                    v_ids = [v.get('id') for v in versions]
                    
                    # 2. Fetch representations
                    repres = []
                    if v_ids:
                        repres = list(ayon_api.get_representations(self.project, version_ids=v_ids))
                        
                    elapsed = time.perf_counter() - start_t
                    print(f"[Timer] Pulling representations took {elapsed:.4f} seconds.")
                    self.finished.emit(repres)
                except Exception as e:
                    print(f"Error fetching representations in thread: {e}")
                    self.finished.emit([])

        self._repre_thread = RepreThread(self.ayon, project, product_id)
        self._repre_thread.finished.connect(self.ayon_panel.set_representations)
        self._repre_thread.start()

    def _on_ayon_task_status_change(self, project_name, task_id, task_name, current_status):
        """Handle task status change request from AYON panel."""
        if not project_name or not task_id:
            return
            
        statuses = self.ayon.get_project_statuses(project_name)
        if not statuses:
            # Fallback default statuses if server query returns empty or unconnected
            statuses = [
                {"name": "Not Started", "color": "#707070"},
                {"name": "In Progress", "color": "#2196F3"},
                {"name": "Pending Review", "color": "#FF9800"},
                {"name": "Approved", "color": "#4CAF50"},
                {"name": "Blocked", "color": "#F44336"}
            ]
            
        from gui.ayon_panel import TaskStatusDialog
        from PySide6.QtWidgets import QDialog
        
        dialog = TaskStatusDialog(current_status, statuses, task_name=task_name, parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_status = dialog.get_selected_status()
            if new_status and new_status != current_status:
                success = self.ayon.update_task_status(project_name, task_id, new_status)
                if success:
                    self.ayon_panel.update_task_status_in_tree(task_id, new_status)
                    self.log_message(f"Updated status for task '{task_name}' to '{new_status}'.", "success")
                else:
                    self.log_message(f"Failed to update status for task '{task_name}' in AYON.", "error")

    def _on_ayon_version_status_change(self, project_name, version_id, display_title, current_status, task_id, task_name, row):
        """Handle version status change request from AYON panel product section."""
        if not project_name or not version_id:
            return
            
        statuses = self.ayon.get_project_statuses(project_name)
        if not statuses:
            statuses = [
                {"name": "Not Started", "color": "#707070"},
                {"name": "In Progress", "color": "#2196F3"},
                {"name": "Pending Review", "color": "#FF9800"},
                {"name": "Approved", "color": "#4CAF50"},
                {"name": "Blocked", "color": "#F44336"}
            ]
            
        from gui.ayon_panel import TaskStatusDialog
        from PySide6.QtWidgets import QDialog
        
        dialog = TaskStatusDialog(current_status, statuses, task_name=display_title, show_task_checkbox=True, parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_status = dialog.get_selected_status()
            if new_status:
                if new_status != current_status:
                    success = self.ayon.update_version_status(project_name, version_id, new_status)
                    if success:
                        self.ayon_panel.update_version_status_in_product_list(row, new_status)
                        self.log_message(f"Updated status for version '{display_title}' to '{new_status}'.", "success")
                    else:
                        self.log_message(f"Failed to update status for version '{display_title}' in AYON.", "error")
                
                # Check if "Set the same status to Task" is checked
                if dialog.should_update_task() and task_id:
                    task_success = self.ayon.update_task_status(project_name, task_id, new_status)
                    if task_success:
                        self.ayon_panel.update_task_status_in_tree(task_id, new_status)
                        self.log_message(f"Updated status for task '{task_name or task_id}' to '{new_status}'.", "success")

    def _on_get_folder_repres(self, folder_list):
        proj_name = self.ayon_panel.combo_project.currentText()
        if not proj_name or not folder_list:
            return
        if not hasattr(self, "_ayon_repre_threads"):
            self._ayon_repre_threads = []
        thread = AyonGetRepreThread(self.ayon, proj_name, "folder", folder_list, self.config, secrets=self.secrets)
        thread.finished_items.connect(self._on_ayon_items_resolved)
        self._ayon_repre_threads.append(thread)
        thread.start()

    def _on_get_task_repre(self, task_data):
        proj_name = self.ayon_panel.combo_project.currentText()
        if not proj_name or not task_data:
            return
        if not hasattr(self, "_ayon_repre_threads"):
            self._ayon_repre_threads = []
        thread = AyonGetRepreThread(self.ayon, proj_name, "task", task_data, self.config, secrets=self.secrets)
        thread.finished_items.connect(self._on_ayon_items_resolved)
        self._ayon_repre_threads.append(thread)
        thread.start()

    def _on_get_product_repre(self, product_data):
        proj_name = self.ayon_panel.combo_project.currentText()
        if not proj_name or not product_data:
            return
        if not hasattr(self, "_ayon_repre_threads"):
            self._ayon_repre_threads = []
        thread = AyonGetRepreThread(self.ayon, proj_name, "product", product_data, self.config, secrets=self.secrets)
        thread.finished_items.connect(self._on_ayon_items_resolved)
        self._ayon_repre_threads.append(thread)
        thread.start()

    def _on_get_repre_repre(self, repre_data):
        proj_name = self.ayon_panel.combo_project.currentText()
        if not proj_name or not repre_data:
            return
        if not hasattr(self, "_ayon_repre_threads"):
            self._ayon_repre_threads = []
        thread = AyonGetRepreThread(self.ayon, proj_name, "repre", repre_data, self.config, secrets=self.secrets)
        thread.finished_items.connect(self._on_ayon_items_resolved)
        self._ayon_repre_threads.append(thread)
        thread.start()

    def _on_ayon_items_resolved(self, items):
        if not items:
            return

        sec_cfg = dict(self.config or {})
        sec_cfg.update(getattr(self, "secrets", {}) or {})
        proj_name = self.ayon_panel.combo_project.currentText() if hasattr(self, "ayon_panel") else ""
        for item in items:
            if getattr(item, "is_ayon_item", False) and not getattr(item, "thumbnail_image", None) and not getattr(item, "thumbnail", None):
                try:
                    from utils import ensure_repre_middle_frame_thumbnail
                    ensure_repre_middle_frame_thumbnail(item, proj_name, sec_cfg, ayon_client=getattr(self, "ayon", None))
                except Exception:
                    pass

        existing_all = getattr(self.model, "all_items", self.model.items)
        existing_keys = set()
        for item in existing_all:
            if getattr(item, "is_ayon_item", False):
                r_id = getattr(item, "repre_id", "")
                f_path = (item.file_path or "").lower()
                lbl = (item.label or "").lower()
                if r_id:
                    existing_keys.add(f"id:{r_id}")
                if f_path:
                    existing_keys.add(f"path:{f_path}")
                if lbl:
                    existing_keys.add(f"lbl:{lbl}")

        unique_items = []
        for item in items:
            r_id = getattr(item, "repre_id", "")
            f_path = (item.file_path or "").lower()
            lbl = (item.label or "").lower()

            is_dup = False
            if r_id and f"id:{r_id}" in existing_keys:
                is_dup = True
            elif f_path and f"path:{f_path}" in existing_keys:
                is_dup = True
            elif lbl and f"lbl:{lbl}" in existing_keys:
                is_dup = True

            if not is_dup:
                if r_id: existing_keys.add(f"id:{r_id}")
                if f_path: existing_keys.add(f"path:{f_path}")
                if lbl: existing_keys.add(f"lbl:{lbl}")
                unique_items.append(item)

        if not unique_items:
            return

        self.model.add_items(unique_items)
        if hasattr(self, "thumb_area") and self.thumb_area:
            self.thumb_area.rearrange_items()
            
        if hasattr(self, "filter_panel") and self.filter_panel:
            self.filter_panel.refresh_views_if_active()

    def perform_auto_assign(self):
        """Automatically match scanned items to AYON paths based on leaf folder names."""
        if not self.ayon.is_connected:
            self.log_message("AYON is not connected. Cannot auto-assign.", "error")
            return
            
        # 1. Get items to process (selection or all)
        items_to_process = []
        selected_thumbs = self.thumb_area.scene.selectedItems()
        if selected_thumbs:
            items_to_process = [thumb.data for thumb in selected_thumbs]
        else:
            # Check table selection
            selection_model = self.spreadsheet.table.selectionModel()
            selected_indexes = selection_model.selectedRows()
            if selected_indexes:
                items_to_process = self._items_for_table_rows(selected_indexes)
            else:
                # Process all items
                items_to_process = self.model.items
        
        if not items_to_process:
            self.log_message("No items to auto-assign.", "warning")
            return
            
        multi_match = self.config.get("auto_assign_multi_match", False)
        fallback_task = self.config.get("auto_assign_fallback_task", False)
        
        count = 0
        for item in items_to_process:
            # 1. Parse tags from filename
            self._parse_item_tags(item)
            
            # 2. Get names for matching
            folder_name = item.metadata.get("folder_name")
            if not folder_name:
                # Fallback to leaf folder name of the local path
                folder_name = os.path.basename(os.path.dirname(item.file_path))
                from utils import apply_capitalization
                folder_name = apply_capitalization(folder_name, self.config.get("folder_capitalization", "Keep Original"))
                item.metadata["folder_name"] = folder_name
            
            if not folder_name:
                continue
                
            if self.config.get("fixed_task_name_enabled", False):
                task_name = self.config.get("fixed_task_name", "")
            else:
                task_name = item.metadata.get("task_name")
                
            match = self.ayon_panel.find_best_match(
                folder_name, 
                task_name=task_name,
                multi_match=multi_match, 
                fallback_task=fallback_task
            )
            
            if match:
                ayon_path = f"{match['folder_path']}/{match['task_name']}"
                if item.ayon_path != ayon_path:
                    item.ayon_path = ayon_path
                    item.ayon_task_name = match.get("task_name", "")
                    item.ayon_task_type = match.get("task_type", "")
                    item.ayon_task_assignee = match.get("assignee", "")
                    count += 1
        
        if count:
            # Column 14 is AYON Path
            self.model.dataChanged.emit(self.model.index(0, 14), self.model.index(len(self.model.items)-1, 14))
            self.log_message(f"Auto-assigned {count} items based on folder name matches.", "success")
            self._update_ayon_visuals()
        else:
            self.log_message("No automatic matches found.")
