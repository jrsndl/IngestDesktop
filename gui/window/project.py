"""Project files (.yaml): new / open / save, recent folders.

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


class ProjectMixin:
    def _update_recent_menu(self):
        self.recent_menu.clear()
        recent = self.config.get("recent_folders", [])
        if not recent:
            act_none = QAction("No Recent Projects", self)
            act_none.setEnabled(False)
            self.recent_menu.addAction(act_none)
            return
            
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda p=path: self.start_scan(p))
            self.recent_menu.addAction(act)

    def perform_new_project(self):
        self.current_project_path = None
        self.thumb_area.clear_canvas()
        self.model.clear()
        self.top_bar.path_display.setText("")
        self.log_message("New project created. Select a folder to begin.")

    def perform_save_project(self):
        if self.current_project_path:
            self.save_project_files(self.current_project_path)
        else:
            self.perform_save_project_as()

    def perform_save_project_as(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As...", "", "IngestProject (*.yaml)"
        )
        if path:
            self.save_project_files(path)

    def save_project_files(self, yaml_path):
        import yaml
        self._gather_gui_state()
        
        project_data = {
            "source_folder": self.top_bar.path_display.text(),
            "items": [],
            "text_notes": [],
            "backdrops": [],
            "draw_items": []
        }
        
        # Gather items
        from PySide6.QtCore import QModelIndex
        for item in self.model.items:
            # Check if this item is selected in either the thumbnail view or table
            is_selected = False
            if hasattr(self, "thumb_area") and self.thumb_area:
                thumb = self.thumb_area.item_to_thumb.get(item)
                if thumb and thumb.isSelected():
                    is_selected = True
            if not is_selected and hasattr(self, "spreadsheet") and self.spreadsheet:
                try:
                    row = self.model.items.index(item)
                    selection_model = self.spreadsheet.table.selectionModel()
                    if selection_model and selection_model.isRowSelected(row, QModelIndex()):
                        is_selected = True
                except ValueError:
                    pass
                    
            item_dict = {
                "file_path": item.file_path,
                "label": item.label,
                "is_tagged": item.is_tagged,
                "version": item.version,
                "version_user": getattr(item, "version_user", ""),
                "comment": item.comment,
                "category": item.category,
                "variant": item.variant,
                "variant_user": getattr(item, "variant_user", ""),
                "product_type": item.product_type,
                "representation": item.representation,
                "colorspace": item.colorspace,
                "rep_tags": item.rep_tags,
                "ayon_path": item.ayon_path,
                "ayon_task_name": item.ayon_task_name,
                "conversion_thumb_path": item.conversion_thumb_path,
                "is_sequence": item.is_sequence,
                "is_selected": is_selected,
                "position": item.position,
                "size": getattr(item, "size", 150),
                "is_custom_size": getattr(item, "is_custom_size", False),
                "metadata": item.metadata,
                "ingest_status": item.ingest_status,
                "z_value": (self.thumb_area.item_to_thumb.get(item).zValue()
                             if self.thumb_area and self.thumb_area.item_to_thumb.get(item) else 0)
            }
            project_data["items"].append(item_dict)
            
        # Gather Text Notes and Backdrops
        from gui.thumbnail_area import TextNoteItem, BackdropItem, DrawItem
        for graphics_item in self.thumb_area.scene.items():
            if isinstance(graphics_item, TextNoteItem):
                parent_uuid = None
                note_center = graphics_item.sceneBoundingRect().center()
                parent_bd = None
                for item in self.thumb_area.scene.items():
                    if isinstance(item, BackdropItem):
                        if item.sceneBoundingRect().contains(note_center):
                            parent_uuid = item.uuid
                            parent_bd = item
                            break
                
                if parent_bd:
                    rel_pos = parent_bd.mapFromScene(graphics_item.scenePos())
                    note_x = rel_pos.x()
                    note_y = rel_pos.y()
                else:
                    note_x = graphics_item.scenePos().x()
                    note_y = graphics_item.scenePos().y()
                
                note_dict = {
                    "uuid": graphics_item.uuid,
                    "parent_uuid": parent_uuid,
                    "x": note_x,
                    "y": note_y,
                    "width": graphics_item.width,
                    "height": graphics_item.height,
                    "bg_color": graphics_item.bg_color.name(),
                    "text": graphics_item.text_item.toPlainText(),
                    "html": graphics_item.text_item.toHtml(),
                    "default_text_color": graphics_item.text_item.defaultTextColor().name()
                }
                project_data["text_notes"].append(note_dict)
            elif isinstance(graphics_item, DrawItem):
                draw_dict = {
                    "uuid": graphics_item.uuid,
                    "x": graphics_item.pos().x(),
                    "y": graphics_item.pos().y(),
                    "width": graphics_item.width,
                    "height": graphics_item.height,
                    "file_path": graphics_item.file_path,
                    "is_custom_size": graphics_item.is_custom_size
                }
                project_data["draw_items"].append(draw_dict)
            elif isinstance(graphics_item, BackdropItem):
                bd_dict = {
                    "uuid": graphics_item.uuid,
                    "x": graphics_item.pos().x(),
                    "y": graphics_item.pos().y(),
                    "width": graphics_item.width,
                    "height": graphics_item.height,
                    "name": graphics_item.name,
                    "label": graphics_item.label,
                    "label_size": graphics_item.label_size,
                    "label_color": graphics_item.label_color.name(),
                    "label_bold": graphics_item.label_bold,
                    "label_italic": graphics_item.label_italic,
                    "label_strike": graphics_item.label_strike,
                    "label_underline": graphics_item.label_underline,
                    "label_alignment": graphics_item.label_alignment,
                    "appearance": graphics_item.appearance,
                    "border_color": graphics_item.border_color.name(),
                    "fill_color": graphics_item.fill_color.name()
                }
                project_data["backdrops"].append(bd_dict)
                
        try:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(project_data, f, default_flow_style=False, sort_keys=False)
                
            # Save JSON preferences next to it
            json_path = os.path.splitext(yaml_path)[0] + ".json"
            clean_config = self.config.copy()
            if "ayon_api_key" in clean_config:
                del clean_config["ayon_api_key"]
            if "thumbnails_per_row" in clean_config:
                del clean_config["thumbnails_per_row"]
                
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(clean_config, f, indent=4)
                
            self.current_project_path = yaml_path
            self.log_message(f"Saved project successfully to {yaml_path}", "success")
        except Exception as e:
            self.log_message(f"Failed to save project: {e}", "error")

    def perform_open_project(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project...", "", "IngestProject (*.yaml)"
        )
        if not path:
            return
            
        import yaml
        try:
            # 1. Look for and load corresponding JSON config
            json_path = os.path.splitext(path)[0] + ".json"
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    new_config = json.load(f)
                
                # Apply preferences
                old_detect = self.config.get("detect_sequences")
                old_thumb = self.config.get("seq_thumb_frame")
                old_regex = self.config.get("version_regex")
                old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)
                
                self.config.update(new_config)
                self._apply_preferences(
                    self.config, self.secrets, old_detect, old_thumb, old_regex, old_exts,
                    show_message=False, save=False
                )
                self._restore_gui_state()
                
            # 2. Read YAML project file
            with open(path, "r", encoding="utf-8") as f:
                project_data = yaml.safe_load(f)
                
            self.current_project_path = path
            
            # 3. Reconstruct items
            from logic.image_model import ImageItem
            from PySide6.QtGui import QPixmap
            from utils import generate_thumbnail_image, generate_placeholder_thumbnail_image
            reconstructed_items = []
            
            thumb_size = self.config.get("thumbnail_size", 150)
            items_list = project_data.get("items", [])
            for it in items_list:
                item = ImageItem(
                    file_path=it.get("file_path"),
                    label=it.get("label"),
                    version=it.get("version", 1),
                    category=it.get("category", "Other"),
                    variant=it.get("variant"),
                    variant_user=it.get("variant_user", ""),
                    version_user=it.get("version_user", ""),
                    product_type=it.get("product_type"),
                    representation=it.get("representation"),
                    colorspace=it.get("colorspace"),
                    rep_tags=it.get("rep_tags"),
                    comment=it.get("comment", "")
                )
                # Populate additional parameters
                item.is_tagged = it.get("is_tagged", True)
                item.ayon_path = it.get("ayon_path", "")
                item.ayon_task_name = it.get("ayon_task_name", "")
                item.position = tuple(it.get("position", (0, 0)))
                item.size = it.get("size", 150)
                item.is_custom_size = it.get("is_custom_size", False)
                item.metadata = it.get("metadata", {})
                item.ingest_status = it.get("ingest_status", "unknown")
                item._z_value = it.get("z_value", 0)  # saved draw order
                
                # Check for standard model keys
                item.is_sequence = it.get("is_sequence", False)
                item.conversion_thumb_path = it.get("conversion_thumb_path", "")
                
                # Keep selected flag
                item.is_selected = it.get("is_selected", False)
                
                # Load thumbnail image
                thumb_source = item.file_path
                expected_pref_thumb = self.model._get_prefs_thumb_path(item)
                if item.conversion_thumb_path and os.path.exists(item.conversion_thumb_path):
                    thumb_source = item.conversion_thumb_path
                elif expected_pref_thumb and os.path.exists(expected_pref_thumb):
                    thumb_source = expected_pref_thumb
                elif item.category.lower().startswith("video"):
                    sidecar = item.file_path + "_thumbnail.png"
                    if os.path.exists(sidecar):
                        thumb_source = sidecar
                    else:
                        thumb_source = None
                elif item.is_sequence:
                    thumb_source = item.metadata.get("seq_thumbnail_path", item.file_path)
                
                if thumb_source and os.path.exists(thumb_source):
                    qimage = generate_thumbnail_image(thumb_source, thumb_size)
                    if qimage:
                        item.thumbnail = QPixmap.fromImage(qimage)
                        
                if not item.thumbnail:
                    # Gray placeholder
                    qimage = generate_placeholder_thumbnail_image(thumb_size, "#555555")
                    if qimage:
                        item.thumbnail = QPixmap.fromImage(qimage)
                
                reconstructed_items.append(item)
                
            # Save the loaded positions, selection states, and z-values before resetting the model
            saved_positions = {it.file_path: it.position for it in reconstructed_items}
            saved_selections = {it.file_path: it.is_selected for it in reconstructed_items}
            saved_z_values = {it.file_path: it._z_value for it in reconstructed_items if hasattr(it, "_z_value")}
            saved_sizes = {it.file_path: getattr(it, "size", 150) for it in reconstructed_items}

            # Update Model
            self.thumb_area.clear_canvas()
            self.model.clear()
            self.model.beginResetModel()
            self.model.items = reconstructed_items
            source_folder = project_data.get("source_folder", "")
            self.model.source_folder = source_folder
            self.top_bar.path_display.setText(source_folder)
            self.model.endResetModel()
            
            # Now restore backdrops and text notes
            from gui.thumbnail_area import TextNoteItem, BackdropItem
            from PySide6.QtCore import QPointF
            
            # Recreate backdrops first
            backdrops = project_data.get("backdrops", [])
            backdrop_map = {}
            for bd in backdrops:
                from PySide6.QtCore import QRectF
                rect = QRectF(bd.get("x", 0), bd.get("y", 0), bd.get("width", 300), bd.get("height", 300))
                bd_data = {
                    "name": bd.get("name", ""),
                    "label": bd.get("label", ""),
                    "label_size": bd.get("label_size", 200),
                    "label_color": bd.get("label_color", "white"),
                    "label_bold": bd.get("label_bold", True),
                    "label_italic": bd.get("label_italic", False),
                    "label_strike": bd.get("label_strike", False),
                    "label_underline": bd.get("label_underline", False),
                    "label_alignment": bd.get("label_alignment", "Top Left"),
                    "appearance": bd.get("appearance", "Border"),
                    "border_color": bd.get("border_color", "magenta"),
                    "fill_color": bd.get("fill_color", "#282828")
                }
                backdrop = BackdropItem(rect, bd_data)
                backdrop.uuid = bd.get("uuid", backdrop.uuid)
                backdrop.setZValue(-1000)
                self.thumb_area.scene.addItem(backdrop)
                backdrop.delete_requested.connect(self.thumb_area.delete_backdrop)
                backdrop_map[backdrop.uuid] = backdrop
                
            # Recreate text notes second
            text_notes = project_data.get("text_notes", [])
            for nt in text_notes:
                pos = QPointF(nt.get("x", 0), nt.get("y", 0))
                note = TextNoteItem(pos, nt.get("text", "New Note"))
                note._manual_size = True  # keep the size saved in the project
                note.uuid = nt.get("uuid", note.uuid)
                note.width = nt.get("width", 400)
                note.height = nt.get("height", 200)
                note.bg_color = QColor(nt.get("bg_color", "#1e1e1e"))
                
                # Restore HTML rich text and default colors if present
                if "html" in nt:
                    note.text_item.setHtml(nt["html"])
                if "default_text_color" in nt:
                    note.text_item.setDefaultTextColor(QColor(nt["default_text_color"]))
                
                # Apply restored size to text item wrapping
                note.text_item.setTextWidth(note.width - 20)
                note.setZValue(5000)  # Always above backdrops (-1000) and thumbnails (0)
                
                # Determine containing backdrop (no setParentItem)
                parent_uuid = nt.get("parent_uuid")
                parent_bd = backdrop_map.get(parent_uuid) if parent_uuid else None
                
                # Compatibility fallback for older files: check containment
                if not parent_bd:
                    # Older files stored absolute scene position in 'pos'
                    # We check if the note center falls inside any backdrop
                    note_center = QPointF(pos.x() + note.width/2, pos.y() + note.height/2)
                    for bd_item in backdrop_map.values():
                        if bd_item.sceneBoundingRect().contains(note_center):
                            parent_bd = bd_item
                            break
                            
                if parent_bd:
                    if parent_uuid:
                        # Loaded from new style: position was saved relative to parent
                        note.setPos(parent_bd.mapToScene(pos))
                    else:
                        # Loaded from old style: position was absolute scene coordinate
                        note.setPos(pos)
                else:
                    # Top-level note
                    note.setPos(pos)
                
                note.moving_started.connect(self.thumb_area.note_toolbar.hide)
                note.moving_finished.connect(self.thumb_area._update_note_toolbar)
                self.thumb_area.scene.addItem(note)
                
            # Recreate draw items
            from gui.thumbnail_area import DrawItem
            draw_items = project_data.get("draw_items", [])
            for di in draw_items:
                file_path = di.get("file_path", "")
                if not os.path.exists(file_path):
                    base_name = os.path.basename(file_path)
                    cache_dir = self.thumb_area.get_drawing_cache_dir()
                    alt_path = os.path.join(cache_dir, base_name)
                    if os.path.exists(alt_path):
                        file_path = alt_path
                    else:
                        source_folder = self.model.source_folder
                        if source_folder:
                            path_setting = self.config.get("drawing_cache_path", "_drawcache")
                            alt_path2 = os.path.join(source_folder, path_setting, base_name)
                            if os.path.exists(alt_path2):
                                file_path = alt_path2
                
                if os.path.exists(file_path):
                    pos = QPointF(di.get("x", 0), di.get("y", 0))
                    draw_item = DrawItem(
                        pos, 
                        file_path, 
                        di.get("width", 200), 
                        di.get("height", 200)
                    )
                    draw_item.uuid = di.get("uuid", draw_item.uuid)
                    draw_item.is_custom_size = di.get("is_custom_size", False)
                    self.thumb_area.scene.addItem(draw_item)
                
            # Restore manual positions on reconstructed items in the scene using saved states
            for item in self.model.items:
                thumb = self.thumb_area.item_to_thumb.get(item)
                if thumb:
                    pos = saved_positions.get(item.file_path)
                    if pos is not None:
                        item.position = pos
                        item.is_manually_moved = True
                        thumb.setPos(pos[0], pos[1])
                        thumb.is_manually_moved = True
                        
                    size = saved_sizes.get(item.file_path)
                    if size is not None:
                        item.size = size
                        thumb.prepareGeometryChange()
                        thumb.size = size
                        thumb.cached_label = ""
                        thumb.update()

                    z = saved_z_values.get(item.file_path, 0)
                    thumb.setZValue(z)
                    
                    is_sel = saved_selections.get(item.file_path, False)
                    item.is_selected = is_sel
                    thumb.setSelected(is_sel)
                        
            # Sync selection to table
            self._sync_selection_to_table()
            
            # Sync right panel filter scene items
            self._sync_scene_items_to_filter()
            
            # Re-run layout updates
            self.thumb_area.rearrange_items()
            
            self.log_message(f"Successfully loaded project {path}", "success")
        except Exception as e:
            self.log_message(f"Failed to load project: {e}", "error")

    def _add_to_recent(self, path):
        recent = self.config.get("recent_folders", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.config["recent_folders"] = recent[:10] # Keep last 10
        self.save_config()
        self._update_recent_menu()
