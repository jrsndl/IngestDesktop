"""Selection sync between canvas, spreadsheet and filter panel; filters, labels, replace, version stacks.

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


class SelectionMixin:
    def _items_for_table_rows(self, indexes):
        """ImageItems for selected spreadsheet rows, in either view (standard or CSV)."""
        if getattr(self.spreadsheet, "_is_csv_mode", False):
            rows_src = self.csv_preview_model.tagged_items
        else:
            rows_src = self.model.items
        out = []
        for idx in indexes:
            r = idx.row()
            if 0 <= r < len(rows_src):
                out.append(rows_src[r])
        return out

    def get_selected_items(self):
        selected_items = []
        if hasattr(self, 'thumb_area') and self.thumb_area.scene:
            selected_thumbs = [item for item in self.thumb_area.scene.selectedItems() if hasattr(item, 'data') and item.data]
            if selected_thumbs:
                selected_items = [thumb.data for thumb in selected_thumbs]
        if not selected_items and hasattr(self, 'spreadsheet') and self.spreadsheet.table:
            selection_model = self.spreadsheet.table.selectionModel()
            if selection_model:
                selected_items = self._items_for_table_rows(selection_model.selectedRows())
        return selected_items

    def _on_selection_changed(self, selected, deselected):
        pass # Handle via sync methods now

    def _sync_selection_to_thumbs(self):
        if self._selection_lock: return
        if not hasattr(self, 'thumb_area') or not self.thumb_area.scene: return
        
        self._selection_lock = True
        try:
            self.thumb_area.scene.clearSelection()
            
            # Identify which model is active in the spreadsheet
            is_csv = self.spreadsheet._is_csv_mode
            table_selection = self.spreadsheet.table.selectionModel().selectedRows()
            
            selected_paths = []
            for idx in table_selection:
                row = idx.row()
                if is_csv:
                    if row < len(self.csv_preview_model.tagged_items):
                        item_data = self.csv_preview_model.tagged_items[row]
                    else: continue
                else:
                    if row < len(self.model.items):
                        item_data = self.model.items[row]
                    else: continue
                
                if item_data in self.thumb_area.item_to_thumb:
                    self.thumb_area.item_to_thumb[item_data].setSelected(True)
                    selected_paths.append(os.path.normpath(os.path.abspath(item_data.file_path)))
            
            # Sync to FilterPanel
            self.filter_panel.select_paths(selected_paths)
            self._update_video_preview()
        finally:
            self._selection_lock = False

    def select_items(self, target_items):
        """Select a list of ImageItems across thumbnail view, spreadsheet table, and filter panel."""
        if not target_items:
            if hasattr(self, "thumb_area") and self.thumb_area.scene:
                self.thumb_area.scene.clearSelection()
            if hasattr(self, "spreadsheet") and self.spreadsheet.table and self.spreadsheet.table.selectionModel():
                self.spreadsheet.table.selectionModel().clearSelection()
            if hasattr(self, "filter_panel") and self.filter_panel.tree and self.filter_panel.tree.selectionModel():
                self.filter_panel.tree.selectionModel().clearSelection()
            return

        target_set = set(target_items)
        
        # 1. Select in Spreadsheet Table
        if hasattr(self, "spreadsheet") and self.spreadsheet.table:
            selection_model = self.spreadsheet.table.selectionModel()
            if selection_model:
                from PySide6.QtCore import QItemSelection, QItemSelectionModel
                selection = QItemSelection()
                
                is_csv = getattr(self.spreadsheet, "_is_csv_mode", False)
                items_list = self.csv_preview_model.tagged_items if (is_csv and hasattr(self, "csv_preview_model")) else self.model.items

                for row, item in enumerate(items_list):
                    if item in target_set:
                        idx = self.spreadsheet.table.model().index(row, 0)
                        selection.select(idx, idx)

                selection_model.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

        # 2. Select in Thumbnail Area (graphics scene)
        if hasattr(self, "thumb_area") and self.thumb_area.scene:
            self.thumb_area.scene.clearSelection()
            for item_data in target_items:
                thumb = self.thumb_area.item_to_thumb.get(item_data)
                if thumb and thumb.isVisible():
                    thumb.setSelected(True)
            if hasattr(self.thumb_area, "update_video_overlay_geometry"):
                self.thumb_area.update_video_overlay_geometry()

        # 3. Sync to FilterPanel
        if hasattr(self, "filter_panel"):
            selected_paths = [os.path.normpath(os.path.abspath(it.file_path)) for it in target_items if hasattr(it, "file_path") and it.file_path]
            self.filter_panel.select_paths(selected_paths)

    def _save_filter_toggles(self):
        old_v_stack = getattr(self.model, "v_stack_enabled", False)
        new_v_stack = self.filter_panel.btn_v_stack.isChecked()
        
        self.config["filter_toggles"] = self.filter_panel.get_toggle_states()
        self.save_config()
        self._connect_filter_selection_signal()
        self.model.v_stack_enabled = new_v_stack
        
        if old_v_stack != new_v_stack:
            if new_v_stack:
                # Transition: Version Stack Off -> Version Stack On
                # For every version stack, the highest stacked item (physically highest, i.e., min y coordinate)
                # is the "base position" that will be used for the stack.
                for key, stack in self.model.version_stacks.items():
                    highest_item = None
                    min_y = float('inf')
                    
                    for item in stack["items"]:
                        thumb = self.thumb_area.item_to_thumb.get(item)
                        pos = thumb.pos() if thumb else None
                        if pos is None:
                            pos = item.position
                            
                        if pos is not None:
                            y_val = pos.y() if hasattr(pos, 'y') else pos[1]
                            if y_val < min_y:
                                min_y = y_val
                                highest_item = item
                                
                    if highest_item:
                        picked_ver = stack["picked"]
                        picked_item = None
                        for item in stack["items"]:
                            if item.version == picked_ver:
                                picked_item = item
                                break
                        if not picked_item:
                            picked_item = stack["items"][0]
                            
                        h_thumb = self.thumb_area.item_to_thumb.get(highest_item)
                        pos_to_use = h_thumb.pos() if h_thumb else highest_item.position
                        is_manual = h_thumb.is_manually_moved if h_thumb else getattr(highest_item, "is_manually_moved", False)
                        
                        if pos_to_use is not None:
                            pos_tuple = (pos_to_use.x(), pos_to_use.y()) if hasattr(pos_to_use, 'x') else pos_to_use
                            picked_item.position = pos_tuple
                            picked_item.is_manually_moved = is_manual
                            
                            p_thumb = self.thumb_area.item_to_thumb.get(picked_item)
                            if p_thumb:
                                p_thumb.setPos(pos_tuple[0], pos_tuple[1])
                                p_thumb.is_manually_moved = is_manual
            else:
                # Transition: Version Stack On -> Version Stack Off
                # For every version stack, the stacked item (picked version) is the "base position",
                # and all other versions are positioned vertically below the base position in a way they are not overlapping.
                # All these items should be marked as manually moved so they don't reflow.
                # First pass: propagate size and scale to all stack versions
                for key, stack in self.model.version_stacks.items():
                    picked_ver = stack["picked"]
                    picked_item = None
                    for item in stack["items"]:
                        if item.version == picked_ver:
                            picked_item = item
                            break
                    if not picked_item: continue
                    
                    p_thumb = self.thumb_area.item_to_thumb.get(picked_item)
                    if p_thumb:
                        stack_size = p_thumb.size
                        stack_is_custom = p_thumb.is_custom_size
                    else:
                        stack_size = getattr(picked_item, "size", 150)
                        stack_is_custom = getattr(picked_item, "is_custom_size", False)
                        
                    for other_item in stack["items"]:
                        if other_item != picked_item:
                            other_item.size = stack_size
                            other_item.is_custom_size = stack_is_custom
                            
                            o_thumb = self.thumb_area.item_to_thumb.get(other_item)
                            if o_thumb:
                                o_thumb.prepareGeometryChange()
                                o_thumb.size = stack_size
                                o_thumb.is_custom_size = stack_is_custom

                # Second pass: calculate the new vertical gap size based on 40% of average thumbnail height of visible items
                age_enabled, age_val = self.thumb_area._last_age_filter
                search_term = self.thumb_area._last_search_text
                
                total_h = 0.0
                count = 0
                for item_data in self.model.items:
                    # Check if it has a thumbnail in the GUI
                    if item_data not in self.thumb_area.item_to_thumb:
                        continue
                        
                    is_tagged = item_data.is_tagged
                    item_abs = os.path.normpath(os.path.abspath(item_data.file_path))
                    filter_abs = os.path.normpath(os.path.abspath(self.thumb_area._path_filter))
                    in_path = not self.thumb_area._path_filter or (item_abs == filter_abs or item_abs.startswith(filter_abs + os.sep))
                    
                    show_by_tag = True
                    if self.thumb_area._tag_filter_state == "enabled": show_by_tag = is_tagged
                    elif self.thumb_area._tag_filter_state == "disabled": show_by_tag = not is_tagged
                    
                    is_young_enough = not age_enabled or (item_data.age_minutes <= age_val)
                    matches_search = (not search_term or 
                                      search_term in item_data.label.lower() or 
                                      search_term in item_data.filename.lower())
                    
                    # Since v_stack_enabled is False now:
                    is_visible_ver = True
                    
                    if show_by_tag and in_path and is_young_enough and matches_search and is_visible_ver:
                        w = item_data.metadata.get("width", None)
                        h = item_data.metadata.get("height", None)
                        try:
                            fw = float(w) if w is not None else 1.0
                            fh = float(h) if h is not None else 1.0
                            aspect = fw / fh if fh > 0 else 1.0
                        except (ValueError, TypeError):
                            aspect = 1.0
                            
                        item_size = getattr(item_data, "size", self.thumb_area.slider_thumb_size.value())
                        total_h += item_size / aspect
                        count += 1
                    
                if count > 0:
                    new_gap_v = int((total_h / count) * 0.20)
                    self.thumb_area._last_arrange_vals["gap_v"] = new_gap_v

                # Third pass: position the unstacked items vertically below the picked item using the new gap
                for key, stack in self.model.version_stacks.items():
                    picked_ver = stack["picked"]
                    picked_item = None
                    for item in stack["items"]:
                        if item.version == picked_ver:
                            picked_item = item
                            break
                    if not picked_item: continue
                    
                    p_thumb = self.thumb_area.item_to_thumb.get(picked_item)
                    base_pos = p_thumb.pos() if p_thumb else picked_item.position
                    if base_pos is None: continue
                    
                    base_x = base_pos.x() if hasattr(base_pos, 'x') else base_pos[0]
                    base_y = base_pos.y() if hasattr(base_pos, 'y') else base_pos[1]
                    
                    # Sort other versions descending (highest version to lowest version)
                    other_items = sorted([it for it in stack["items"] if it != picked_item], key=lambda it: it.version, reverse=True)
                    
                    current_y = base_y
                    prev_item = picked_item
                    prev_thumb = p_thumb
                    gap_v = self.thumb_area._last_arrange_vals.get("gap_v", 20)
                    
                    for other_item in other_items:
                        o_thumb = self.thumb_area.item_to_thumb.get(other_item)
                        
                        # Bounding height of prev_item
                        if prev_thumb:
                            prev_h = prev_thumb.boundingRect().height()
                        else:
                            # Calculate height fallback using the updated size of the item
                            prev_item_size = getattr(prev_item, "size", self.thumb_area.slider_thumb_size.value())
                            show_text = self.thumb_area.btn_show_text.isChecked()
                            font_size = self.thumb_area.slider_text_size.value()
                            line_height = font_size * 1.5
                            label_area = (line_height * 3.5) + 10 if show_text else 0
                            
                            w = prev_item.metadata.get("width", 1)
                            h = prev_item.metadata.get("height", 1)
                            try:
                                fw = float(w) if w is not None else 1.0
                                fh = float(h) if h is not None else 1.0
                                aspect = fw / fh if fh > 0 else 1.0
                            except (ValueError, TypeError):
                                aspect = 1.0
                            prev_h = (prev_item_size / aspect) + 20 + label_area
                            
                        current_y += prev_h + gap_v
                        
                        other_item.position = (base_x, current_y)
                        other_item.is_manually_moved = True
                        
                        if o_thumb:
                            o_thumb.setPos(base_x, current_y)
                            o_thumb.is_manually_moved = True
                            o_thumb.update()
                            
                        prev_item = other_item
                        prev_thumb = o_thumb
                        
        self.spreadsheet.update_filtering()
        self.thumb_area.rearrange_items()

    def _connect_filter_selection_signal(self):
        # Connect exactly once (disconnecting a never-connected slot only produced warnings)
        if self.filter_panel is not getattr(self, "_filter_sel_connected_to", None):
            self.filter_panel.selection_changed.connect(self._sync_selection_from_filter)
            self._filter_sel_connected_to = self.filter_panel
        if hasattr(self.filter_panel, "_reconnect_selection_signal"):
            self.filter_panel._reconnect_selection_signal()

    def _on_filter_sequences_toggled(self, enabled):
        if self.config.get("detect_sequences") == enabled:
            return
        self.config["detect_sequences"] = enabled
        self.save_config()
        
        # Trigger rescan if we have a current folder
        current = self.config.get("last_source_folder")
        if current:
            self.start_scan(current)

    def _sync_scene_items_to_filter(self):
        summaries = self.thumb_area.get_scene_item_summaries()
        # Rebuilding the right panel clears its selection; don't let that clear the
        # canvas selection (it deselected a note when clicking its toolbar).
        was_locked = self._selection_lock
        self._selection_lock = True
        try:
            self.filter_panel.set_scene_items(summaries)
        finally:
            self._selection_lock = was_locked
        if not was_locked:
            self._sync_selection_to_table()  # re-select the canvas selection in the panel

    def _sync_selection_to_table(self):
        if self._selection_lock: return
        if not hasattr(self, 'spreadsheet') or not self.spreadsheet.table.selectionModel(): return
        
        self._selection_lock = True
        try:
            self.spreadsheet.table.selectionModel().clearSelection()
            
            is_csv = self.spreadsheet._is_csv_mode
            selection = QItemSelection()
            selected_paths = []
            first_idx = None
            
            selected_items = self.thumb_area.scene.selectedItems()
            
            for item in selected_items:
                if hasattr(item, "uuid") and (not hasattr(item, "data") or callable(item.data)):
                    selected_paths.append(item.uuid)
                    continue
                if hasattr(item, "data") and getattr(item.data, "is_ayon_item", False):
                    path_val = item.data.file_path if item.data.file_path else (getattr(item.data, "ayon_path", "") or item.data.label or item.data.filename)
                    selected_paths.append(path_val)
                    continue
                try:
                    if is_csv:
                        # Only items that are in tagged_items exist in CSV mode
                        row = self.csv_preview_model.tagged_items.index(item.data)
                        idx = self.csv_preview_model.index(row, 0)
                        model = self.csv_preview_model
                    else:
                        row = self.model.items.index(item.data)
                        idx = self.model.index(row, 0)
                        model = self.model
                        
                    if first_idx is None or idx.row() < first_idx.row():
                        first_idx = idx
                        
                    tl = model.index(row, 0)
                    br = model.index(row, model.columnCount() - 1)
                    selection.select(tl, br)
                    selected_paths.append(os.path.normpath(os.path.abspath(item.data.file_path)))
                except (ValueError, AttributeError):
                    continue
            
            if not selection.isEmpty():
                self.spreadsheet.table.selectionModel().select(selection, QItemSelectionModel.Select)
                if first_idx:
                    self.spreadsheet.table.scrollTo(first_idx)
            
            # Sync to FilterPanel
            self.filter_panel.select_paths(selected_paths)
            self._update_video_preview()
        finally:
            self._selection_lock = False

    def _sync_selection_from_filter(self, selected=None, deselected=None, selected_paths=None):
        """Sync selection from FilterPanel tree to Thumbs and Table."""
        if self._selection_lock: return
        
        is_csv = self.spreadsheet._is_csv_mode
        if selected_paths is not None:
            paths = set(selected_paths)
        else:
            # Get selected paths from tree
            selected_indexes = self.filter_panel.tree.selectionModel().selectedIndexes()
            paths = set()
            for idx in selected_indexes:
                if idx.column() == 0:
                    source_idx = self.filter_panel.proxy.mapToSource(idx)
                    source_model = self.filter_panel.proxy.sourceModel()
                
                if hasattr(source_model, "filePath"):
                    path = source_model.filePath(source_idx)
                else:
                    path = source_idx.data(Qt.UserRole)
                
                if path:
                    is_scene_item = source_idx.data(Qt.UserRole + 1)
                    if is_scene_item:
                        paths.add(path)
                        continue
                        
                    is_path_model = hasattr(source_model, "filePath")
                    is_known_item_path = False
                    if isinstance(path, str):
                        norm_p = os.path.normpath(os.path.abspath(path)).lower()
                        items_list = self.csv_preview_model.tagged_items if is_csv else self.model.items
                        all_items_list = getattr(self.model, "all_items", items_list)
                        for it in all_items_list:
                            if getattr(it, "file_path", None) and os.path.normpath(os.path.abspath(it.file_path)).lower() == norm_p:
                                is_known_item_path = True
                                break
                    
                    if isinstance(path, str):
                        paths.add(path)
                        if is_path_model or os.path.isabs(path) or os.path.exists(path) or is_known_item_path:
                            try:
                                paths.add(os.path.normpath(os.path.abspath(path)))
                            except Exception:
                                pass
                    elif not isinstance(path, dict):
                        # Use only hashable IDs (ints/strings)
                        paths.add(path)
                    elif isinstance(path, dict) and "id" in path:
                        # Fallback for old model data if any
                        paths.add(path["id"])
        
        if not paths:
            self._selection_lock = True
            try:
                if hasattr(self, "spreadsheet") and self.spreadsheet.table and self.spreadsheet.table.selectionModel():
                    self.spreadsheet.table.selectionModel().clearSelection()
                if hasattr(self, "thumb_area") and self.thumb_area.scene:
                    self.thumb_area.scene.clearSelection()
            finally:
                self._selection_lock = False
            return
        
        self._selection_lock = True
        try:
            # 1. Sync to Table
            is_csv = self.spreadsheet._is_csv_mode
            self.spreadsheet.table.selectionModel().clearSelection()
            
            selection = QItemSelection()
            first_idx = None
            
            # 2. Sync to Thumbs
            self.thumb_area.scene.clearSelection()
            
            # We need to find which items in our model match these paths
            target_model = self.csv_preview_model if is_csv else self.model
            items_list = self.csv_preview_model.tagged_items if is_csv else self.model.items
            all_items_list = getattr(self.model, "all_items", items_list)
            
            target_items = set()
            proxy = getattr(self.filter_panel, "proxy", None)

            for p in paths:
                if not isinstance(p, str):
                    continue
                is_ayon_p = p.startswith("ayon://") or "ayon" in p.lower()
                p_norm = p.lower() if is_ayon_p else os.path.normpath(os.path.abspath(p)).lower()

                # Check AYON items in all_items_list
                for item in all_items_list:
                    if getattr(item, "is_ayon_item", False):
                        path_val = item.file_path if item.file_path else (getattr(item, "ayon_path", "") or item.label or item.filename)
                        lbl = item.label or item.filename
                        r_id = getattr(item, "repre_id", "")
                        if p in (path_val, lbl, r_id) or p_norm in (path_val.lower(), lbl.lower(), r_id.lower()):
                            target_items.add(item)
                            if item in self.thumb_area.item_to_thumb:
                                self.thumb_area.item_to_thumb[item].setSelected(True)

                if not is_ayon_p:
                    # 1. Check direct proxy cache map
                    if proxy and hasattr(proxy, "_path_to_item"):
                        for item_path, item in proxy._path_to_item.items():
                            item_norm = os.path.normpath(os.path.abspath(item_path)).lower()
                            if item_norm == p_norm or item_norm.startswith(p_norm + os.sep):
                                target_items.add(item)

                    # 2. Check items_list with normalized slash comparison & sequence matching
                    for item in items_list:
                        item_norm = os.path.normpath(os.path.abspath(item.file_path)).lower()
                        if item_norm == p_norm or item_norm.startswith(p_norm + os.sep) or p_norm.startswith(item_norm):
                            target_items.add(item)
                        else:
                            item_dir = os.path.dirname(item_norm)
                            p_dir = os.path.dirname(p_norm)
                            if item_dir == p_dir:
                                p_ext = os.path.splitext(p_norm)[1].lower()
                                it_ext = os.path.splitext(item_norm)[1].lower()
                                if p_ext == it_ext:
                                    from utils import strip_sequence_counter
                                    p_base = strip_sequence_counter(os.path.basename(p_norm))
                                    it_base = strip_sequence_counter(os.path.basename(item_norm))
                                    if p_base and it_base and p_base == it_base:
                                        target_items.add(item)

            for i, item in enumerate(items_list):
                if item in target_items:
                    # Select in table
                    idx = target_model.index(i, 0)
                    tl = target_model.index(i, 0)
                    br = target_model.index(i, target_model.columnCount() - 1)
                    selection.select(tl, br)
                    if first_idx is None: first_idx = idx
                    
                    # Select in thumbs
                    if item in self.thumb_area.item_to_thumb:
                        self.thumb_area.item_to_thumb[item].setSelected(True)
            
            # 3. Sync Scene Items (Backdrops/Notes) & AYON Items by path/ID
            for p in paths:
                if not isinstance(p, str) or not (os.path.isabs(p) or os.path.exists(p)):
                    # Check for scene items by UUID or AYON items
                    try:
                        for scene_item in self.thumb_area.scene.items():
                            if hasattr(scene_item, "uuid") and scene_item.uuid == p:
                                scene_item.setSelected(True)
                                break
                            if hasattr(scene_item, "data") and getattr(scene_item.data, "is_ayon_item", False):
                                it_data = scene_item.data
                                path_val = it_data.file_path if it_data.file_path else (getattr(it_data, "ayon_path", "") or it_data.label or it_data.filename)
                                lbl = it_data.label or it_data.filename
                                r_id = getattr(it_data, "repre_id", "")
                                if p in (path_val, lbl, r_id) or (isinstance(p, str) and p.lower() in (path_val.lower(), lbl.lower(), r_id.lower())):
                                    scene_item.setSelected(True)
                    except (RuntimeError, AttributeError):
                        continue
            
            if not selection.isEmpty():
                self.spreadsheet.table.selectionModel().select(selection, QItemSelectionModel.Select)
                if first_idx:
                    self.spreadsheet.table.scrollTo(first_idx)
            self._update_video_preview()
        finally:
            self._selection_lock = False

    def _get_single_selected_item(self):
        """Get the first selected ImageItem, if any."""
        # 1. Check spreadsheet selection first
        if hasattr(self, 'spreadsheet') and self.spreadsheet.table.selectionModel():
            rows = self.spreadsheet.table.selectionModel().selectedRows()
            if rows:
                row = rows[0].row()
                is_csv = self.spreadsheet._is_csv_mode
                if is_csv:
                    if row < len(self.csv_preview_model.tagged_items):
                        return self.csv_preview_model.tagged_items[row]
                else:
                    if row < len(self.model.items):
                        return self.model.items[row]
                        
        # 2. Check thumbnail selection as fallback
        if hasattr(self, 'thumb_area') and self.thumb_area.scene:
            selected_items = self.thumb_area.scene.selectedItems()
            if selected_items:
                from gui.thumbnail_area import ThumbnailItem
                # Try to find a ThumbnailItem
                for it in selected_items:
                    if isinstance(it, ThumbnailItem):
                        return it.data
                    
        return None

    def _update_video_preview(self):
        """Forward selection updates to the thumbnail overlay player."""
        if hasattr(self, 'thumb_area'):
            self.thumb_area.update_video_overlay_geometry()

    def _on_select_all(self):
        """Contextual Select All based on mouse hover."""
        # While a text note is being edited, Ctrl+A selects the note's text
        focus_item = self.thumb_area.scene.focusItem() if hasattr(self, "thumb_area") else None
        if focus_item is not None and hasattr(focus_item, "textCursor") and \
                focus_item.textInteractionFlags() & Qt.TextEditorInteraction:
            cursor = focus_item.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            focus_item.setTextCursor(cursor)
            return
        widget = QApplication.widgetAt(QCursor.pos())
        if not widget:
            return
            
        # Check if mouse is over Thumbnails, Spreadsheet, or Filter Panel
        panels = [self.thumb_area, self.spreadsheet, self.filter_panel]
        is_over = False
        for panel in panels:
            if panel.underMouse() or panel.isAncestorOf(widget):
                is_over = True
                break
        
        if is_over:
            self.spreadsheet.table.selectAll()
            # Selection sync will handle Thumbnails and FilterPanel

    def _on_f2_pressed(self):
        """F2 Rename for the currently selected item(s)."""
        # Get selected items
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        
        # Get unique rows from spreadsheet selection
        unique_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        # Check thumbnail area directly
        selected_thumbs = self.thumb_area.scene.selectedItems()
        
        if not unique_rows and selected_thumbs:
            for thumb in selected_thumbs:
                try:
                    row = self.model.items.index(thumb.data)
                    unique_rows.append(row)
                except ValueError:
                    pass
            unique_rows = sorted(list(set(unique_rows)))
            
        if len(unique_rows) > 1:
            # Multiselection rename: trigger sequence rename in thumbnail area
            self.thumb_area._on_sequence_rename()
            return
            
        if len(unique_rows) == 1:
            row = unique_rows[0]
            item_data = self.model.items[row]
            # Trigger the rename action with the specific row index
            self._on_label_action("rename", (row, item_data))

    def _on_replace_value(self, field, value):
        selection_model = self.spreadsheet.table.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            self.log_message(f"No items selected to replace {field}.", "warning")
            return
            
        selected_indexes = selection_model.selectedRows()
        if not selected_indexes:
            return
            
        is_csv = self.spreadsheet._is_csv_mode
        selected_items = []
        for idx in selected_indexes:
            row = idx.row()
            if is_csv:
                if row < len(self.csv_preview_model.tagged_items):
                    selected_items.append(self.csv_preview_model.tagged_items[row])
            else:
                if row < len(self.model.items):
                    selected_items.append(self.model.items[row])

        if not selected_items:
            return

        target_items = set(selected_items)
        
        # if Show Reviews button is off and replace is run on a group item that has a review,
        # the replaced values will be edited for the review too
        show_reviews = getattr(self, "show_reviews", True)
        if not show_reviews:
            all_items = self.model.items if not is_csv else self.csv_preview_model.tagged_items
            for item in selected_items:
                group_key = getattr(item, "group_key", None)
                if group_key:
                    for other in all_items:
                        if getattr(other, "group_key", None) == group_key and getattr(other, "is_review_repre", False):
                            target_items.add(other)

        count = 0
        for item in target_items:
            if field == "Comment":
                item.comment = value
            elif field == "Variant User":
                item.variant_user = value
            elif field == "Version User":
                item.version_user = str(value).strip()
            count += 1
            
        self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(self.model.rowCount() - 1, self.model.columnCount() - 1))
        self.model.layoutChanged.emit()
        if hasattr(self, "csv_preview_model") and self.csv_preview_model:
            self.csv_preview_model.layoutChanged.emit()

        self.log_message(f"Replaced {field} with '{value}' for {count} items.", "success")

    def _on_add_comment(self, comment):
        self._on_replace_value("Comment", comment)

    def _on_filter_search_changed(self, text):
        if self._selection_lock: return
        self._search_filter_text = text.lower()
        
        # Trigger re-filtering in both views
        self.spreadsheet.update_filtering(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=self._search_filter_text,
            ignore_text=getattr(self, "_ignore_filter_text", "")
        )
        self.thumb_area.rearrange_items(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=self._search_filter_text,
            ignore_text=getattr(self, "_ignore_filter_text", "")
        )
        
        # Save search state immediately
        self.config["filter_search_text"] = text
        self.save_config()

    def _on_filter_ignore_changed(self, text, enabled):
        if self._selection_lock: return
        self._ignore_filter_text = text if enabled else ""
        
        # Trigger re-filtering in both views
        self.spreadsheet.update_filtering(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=getattr(self, "_search_filter_text", ""),
            ignore_text=self._ignore_filter_text
        )
        self.thumb_area.rearrange_items(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=getattr(self, "_search_filter_text", ""),
            ignore_text=self._ignore_filter_text
        )
        
        # Save ignore state immediately
        self.config["filter_ignore_text"] = text
        self.config["filter_ignore_enabled"] = enabled
        self.save_config()

    def _on_rename_to_label_requested(self, paths):
        v_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        renamed_count = self.model.perform_rename_to_label(paths, v_regex)
        if renamed_count > 0:
            self.log_message(f"Renamed {renamed_count} files/sequences to their labels.", "success")
            
            # Automatically rescan source folder to reflect changed files on disk
            last_folder = self.config.get("last_source_folder")
            if last_folder and os.path.exists(last_folder):
                self.start_scan(last_folder)
        else:
            self.log_message("No items renamed. Check for collisions or items not in model.", "warning")

    def _on_filter_delete_scene_items(self, uuids):
        to_remove = []
        for item in self.thumb_area.scene.items():
            if hasattr(item, "uuid") and item.uuid in uuids:
                to_remove.append(item)
        if to_remove:
            for it in to_remove:
                self.thumb_area.scene.removeItem(it)
            self.thumb_area.scene_items_changed.emit()
            self.thumb_area._update_note_toolbar()
            self.log_message(f"Deleted {len(to_remove)} scene items from filter panel.", "info")

    def _on_filter_edit_scene_item(self, uuid_str):
        target_item = None
        for item in self.thumb_area.scene.items():
            if hasattr(item, "uuid") and item.uuid == uuid_str:
                target_item = item
                break
        if not target_item:
            return
            
        from gui.thumbnail_area import TextNoteItem, BackdropItem
        if isinstance(target_item, TextNoteItem):
            # Focus view on item
            self.thumb_area.view.ensureVisible(target_item)
            # Programmatically trigger inline editing
            self.thumb_area.scene.clearSelection()
            target_item.setSelected(True)
            target_item.text_item.setAcceptedMouseButtons(Qt.LeftButton)
            target_item.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
            target_item.text_item.setFocus()
            cursor = target_item.text_item.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            target_item.text_item.setTextCursor(cursor)
            self.thumb_area._update_note_toolbar()
        elif isinstance(target_item, BackdropItem):
            # Focus view on item
            self.thumb_area.view.ensureVisible(target_item)
            # Trigger Backdrop Settings Dialog
            self.thumb_area.edit_backdrop(target_item)

    def _on_filter_move_front_back(self, direction, paths):
        """Select the ThumbnailItems matching the given paths and move them front or back."""
        from gui.thumbnail_area import ThumbnailItem
        import os
        norm_paths = {os.path.normpath(os.path.abspath(p)) for p in paths}
        # Select matching thumbs temporarily, then call the area method
        prev_selection = self.thumb_area.scene.selectedItems()
        self.thumb_area.scene.clearSelection()
        for item in self.thumb_area.scene.items():
            if isinstance(item, ThumbnailItem):
                item_path = os.path.normpath(os.path.abspath(item.data.file_path))
                if item_path in norm_paths:
                    item.setSelected(True)
        if direction == "front":
            self.thumb_area.move_selected_to_front()
        else:
            self.thumb_area.move_selected_to_back()
        # Restore previous selection
        self.thumb_area.scene.clearSelection()
        for it in prev_selection:
            it.setSelected(True)



    def change_version_stack_picked_version(self, item, new_version):
        key = self.model.get_version_stack_key(item)
        stack = self.model.version_stacks.get(key)
        if not stack: return
        
        old_version = stack["picked"]
        if old_version == new_version: return
        
        # Get old picked item
        old_picked = None
        for it in stack["items"]:
            if it.version == old_version:
                old_picked = it
                break
                
        # Get new picked item
        new_picked = None
        for it in stack["items"]:
            if it.version == new_version:
                new_picked = it
                break
                
        if not new_picked: return
        
        # Track selection state of old thumbnail
        was_selected = False
        old_thumb = self.thumb_area.item_to_thumb.get(old_picked) if old_picked else None
        if old_thumb:
            was_selected = old_thumb.isSelected()
        
        # Synchronize tag
        if old_picked:
            new_picked.is_tagged = old_picked.is_tagged
            
            # Copy position and manual move state from old_picked to new_picked
            new_thumb = self.thumb_area.item_to_thumb.get(new_picked)
            
            pos = old_thumb.pos() if old_thumb else old_picked.position
            is_manual = old_thumb.is_manually_moved if old_thumb else getattr(old_picked, "is_manually_moved", False)
            
            if pos is not None:
                pos_val = (pos.x(), pos.y()) if hasattr(pos, 'x') else pos
                new_picked.position = pos_val
                new_picked.is_manually_moved = is_manual
                if new_thumb:
                    new_thumb.setPos(pos_val[0], pos_val[1])
                    new_thumb.is_manually_moved = is_manual
            
        # Set new picked version
        stack["picked"] = new_version
        
        # Set review status to waiting if review is enabled in presets
        p_data = new_picked.preset_data or {}
        if p_data.get("Convert Review", True):
            new_picked.review_status = "waiting"
        else:
            new_picked.review_status = "do not convert"
            
        # Refresh UI
        self.model.layoutChanged.emit()
        self.spreadsheet.update_filtering()
        
        # Reset cached labels in all ThumbnailItems and rearrange
        for graphics_item in self.thumb_area.scene.items():
            if hasattr(graphics_item, "cached_label"):
                graphics_item.cached_label = ""
        self.thumb_area.rearrange_items()
        
        # Preserve selection
        if was_selected:
            new_thumb = self.thumb_area.item_to_thumb.get(new_picked)
            if new_thumb:
                new_thumb.setSelected(True)
        
        # Rebuild filter proxy cache
        self.filter_panel.proxy._rebuild_cache()
        
        # Start conversion for the newly picked item
        self.start_conversions([new_picked], force=False, force_review=True)

    def _on_label_action(self, action, data):
        if action in ["tag", "enable"]:
            self._on_tag_selection()
            return

        if action == "rename_done":
            row, new_label = data
            idx = self.model.index(row, 2)
            self.model.dataChanged.emit(idx, idx)
            return

        if action == "search_replace":
            dialog = SearchReplaceDialog(self)
            if dialog.exec():
                search_str, replace_str = dialog.get_values()
                if search_str:
                    self.model.modify_labels(self.spreadsheet.table.selectionModel(), "search_replace", (search_str, replace_str))
                    self.log_message(f"Replaced '{search_str}' with '{replace_str}' in selected labels.", "success")
            return

        if action in ["trim_length", "trim_right", "trim_left"]:
            titles = {
                "trim_length": "Trim to Length",
                "trim_right": "Trim from Right",
                "trim_left": "Trim from Left"
            }
            labels = {
                "trim_length": "Keep first N characters:",
                "trim_right": "Remove N characters from right:",
                "trim_left": "Remove N characters from left:"
            }
            
            n, ok = QInputDialog.getInt(self, titles[action], labels[action], 1, 1, 1000)
            if ok:
                self.model.modify_labels(self.spreadsheet.table.selectionModel(), action, n)
                self.log_message(f"Applied {titles[action]} ({n}) to selected labels.", "success")
            return

        if action in ["prefix", "suffix", "rename"]:
            initial_text = ""
            if action == "rename":
                row_idx = -1
                # Handle both (row, item) and just item data
                if isinstance(data, tuple):
                    row_idx, item = data
                    initial_text = item.label
                else:
                    initial_text = getattr(data, 'label', "")
                    # Find row index if not provided
                    for i, item in enumerate(self.model.items):
                        if item == data:
                            row_idx = i
                            break

                dialog = RenameDialog(initial_text, self)
                if dialog.exec():
                    new_label = dialog.get_text()
                    if new_label and row_idx != -1:
                        old_label = initial_text
                        idx = self.model.index(row_idx, 2)
                        if self.model.setData(idx, new_label, Qt.EditRole):
                            self.log_message(f"Renamed '{old_label}' -> '{new_label}'", "success")
                            self.spreadsheet.table.resizeColumnToContents(2)
                return
            else:
                title = f"Add {action.capitalize()}"
                text, ok = QInputDialog.getText(self, title, "Enter text:")
                if not ok or not text: return
                data = text
        
        self.model.modify_labels(self.spreadsheet.table.selectionModel(), action, data)
        self.log_message(f"Applied bulk action '{action}' with data '{data}' to selection.")

    def _on_tag_selection(self):
        """Unified tagging handler for both views."""
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        if not rows:
            # Check thumbnails fallback
            selected_thumbs = self.thumb_area.scene.selectedItems()
            for thumb in selected_thumbs:
                try:
                    row = self.model.items.index(thumb.data)
                    rows.append(row)
                except ValueError: continue
            rows = sorted(list(set(rows)))

        if not rows: return
        
        self.model.toggle_tag_selection(selection_model)
        
        # Log details
        count = len(rows)
        # Check current state of first item to report action
        sample_item = self.model.items[rows[0]]
        action_str = "Enabled (Selected for ingest)" if sample_item.is_tagged else "Disabled (Excluded from ingest)"
        level = "success" if sample_item.is_tagged else "info"
        self.log_message(f"{action_str}: {count} items.", level)

    def _on_show_reviews_toggled(self, checked):
        was_off = not getattr(self, "show_reviews", True)
        self.config["show_reviews"] = checked
        self.show_reviews = checked

        rev_repres = [r.strip().lower().lstrip(".") for r in self.config.get("review_representations", ["mp4", "mov"]) if r.strip()]
        is_csv = getattr(self.spreadsheet, "_is_csv_mode", False) if hasattr(self, "spreadsheet") else False
        items_source = self.csv_preview_model.tagged_items if (is_csv and hasattr(self, "csv_preview_model")) else (self.model.items if hasattr(self, "model") else [])

        review_items = []
        for item in items_source:
            is_rev = getattr(item, "is_review_repre", False)
            if not is_rev:
                repre = repre_of(item)
                if repre in rev_repres or getattr(item, "category", "") == "Review" or (item.metadata and item.metadata.get("is_paired_review", False)):
                    is_rev = True
                    item.is_review_repre = True
            if is_rev:
                review_items.append(item)

        if hasattr(self, "thumb_area"):
            self.thumb_area.set_show_reviews(checked)
            self.thumb_area.rearrange_items()
        if hasattr(self, "spreadsheet"):
            self.spreadsheet.update_filtering()

        if checked and was_off:
            # Deselect all first, then select all review items across desktop, spreadsheet, and filter panel
            self.select_items(review_items)
