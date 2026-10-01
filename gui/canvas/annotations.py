"""Notes, backdrops and draw mode on the canvas.

Mixin of ThumbnailArea (gui/thumbnail_area.py).
"""
import os
import uuid
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject, 
                             QGraphicsTextItem, QMenu, QVBoxLayout, QWidget, QHBoxLayout, 
                             QPushButton, QCheckBox, QSpinBox, QLabel, QLineEdit, QSlider, 
                             QFrame, QDialog, QFormLayout, QRadioButton, QButtonGroup, QComboBox, QColorDialog)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize, QEvent, QTimer, QRegularExpression, QRunnable, QThreadPool, QObject
from PySide6.QtGui import (QPainter, QPen, QColor, QAction, QPixmap, QFontMetrics, 
                         QRegularExpressionValidator, QImage, QFont, QTextOption, 
                         QHelpEvent, QTextCharFormat, QTextCursor, QPainterPath, QPolygonF, QIcon)
from PySide6.QtWidgets import QToolTip
import math
from PySide6.QtGui import QBitmap, QRegion
from PySide6.QtCore import QPoint
from utils import generate_thumbnail_image
from gui.canvas.widgets import ColorButton, BackdropDialog, NoteToolbar, DrawToolbar, SequenceRenameDialog, ArrangeDialog
from gui.canvas.thumbnail_item import ThumbnailItem, ThumbnailWorkerSignals, ThumbnailWorker
from gui.canvas.scene_items import NoteTextItem, TextNoteItem, BackdropItem
from gui.canvas.drawing import draw_arrow, get_non_transparent_rect, DrawingCanvasItem, DrawItem


class CanvasAnnotationsMixin:
    def _update_note_toolbar(self):
        if hasattr(self, "_draw_mode_active") and self._draw_mode_active:
            self.note_toolbar.hide()
            return
        selected = self.scene.selectedItems()
        notes = [it for it in selected if isinstance(it, TextNoteItem)]
        
        if notes:
            self.note_toolbar.current_items = notes
            # Use the first note for initial sync values
            note = notes[0]
            
            # Sync toolbar state
            cursor = note.text_item.textCursor()
            size = cursor.charFormat().fontPointSize()
            if size <= 0: # Fallback to default
                size = note.text_item.font().pointSize()
                
            self.note_toolbar.spin_size.blockSignals(True)
            self.note_toolbar.spin_size.setValue(int(size))
            self.note_toolbar.spin_size.blockSignals(False)
                
            color = note.text_item.defaultTextColor()
            self.note_toolbar.btn_color.setStyleSheet(f"border-bottom: 3px solid {color.name()}; font-weight: bold; font-size: 18px;")
            self.note_toolbar.btn_bg_color.setStyleSheet(f"color: {note.bg_color.name()}; font-size: 14px;")
            
            # Position above the selection (average position or first note)
            if len(notes) == 1:
                pos = self.view.mapFromScene(note.scenePos())
            else:
                # Find top-left of selection
                min_x = min(n.scenePos().x() for n in notes)
                min_y = min(n.scenePos().y() for n in notes)
                pos = self.view.mapFromScene(QPointF(min_x, min_y))

            global_pos = self.view.viewport().mapToGlobal(pos)
            self.note_toolbar.move(global_pos.x(), global_pos.y() - 55)
            self.note_toolbar.show()
        else:
            self.note_toolbar.hide()
            self.note_toolbar.current_items = []

    def notify_scene_items_changed(self):
        if self.scene.mouseGrabberItem() is not None:
            self._deferred_scene_items_change = True
        else:
            self.scene_items_changed.emit()

    def _process_deferred_scene_items_changed(self):
        if getattr(self, "_deferred_scene_items_change", False):
            self._deferred_scene_items_change = False
            self.scene_items_changed.emit()

    def get_scene_item_summaries(self):
        res = []
        for item in self.scene.items():
            if isinstance(item, TextNoteItem):
                text = item.text_item.toPlainText()
                res.append({"type": "note", "name": text[:20], "label": "Note", "id": item.uuid, "full_text": text})
            elif isinstance(item, BackdropItem):
                res.append({"type": "backdrop", "name": item.name or item.label, "label": "Backdrop", "id": item.uuid})
        return res

    def _exit_active_note_edit(self):
        """Force any currently-editing TextNoteItem to leave edit mode."""
        focus_item = self.scene.focusItem()
        if focus_item is None:
            return
        # Walk up: the focusItem is the NoteTextItem child; its parent is the TextNoteItem
        candidate = focus_item
        while candidate:
            if isinstance(candidate, TextNoteItem):
                candidate.on_text_focus_out(None)
                candidate.clearFocus()
                break
            candidate = candidate.parentItem() if hasattr(candidate, 'parentItem') else None

    def add_text_note(self, pos=None):
        # Create at last click position or center of view
        if hasattr(self, "_last_click_scene_pos"):
            scene_pos = self._last_click_scene_pos
        else:
            v_rect = self.view.viewport().rect()
            center_view = v_rect.center()
            scene_pos = self.view.mapToScene(center_view)
        
        # Default font size and the tight frame come from TextNoteItem itself
        # (NOTE_DEFAULT_FONT_PT / NOTE_PADDING in gui/canvas/scene_items.py)
        note = TextNoteItem(scene_pos)
        note.fit_to_text()
        
        # Connect signals for dragging behavior
        note.moving_started.connect(self.note_toolbar.hide)
        note.moving_finished.connect(self._update_note_toolbar)
        
        if note.scene() is None:
            self.scene.addItem(note)
            
        self.scene_items_changed.emit()
        
        # Select and edit immediately
        self.scene.clearSelection()
        note.setSelected(True)
        note.text_item.setAcceptedMouseButtons(Qt.LeftButton)
        note.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        note.text_item.setFocus()
        
        # Select all so it's ready to be overwritten
        # We need to do this via a timer or after focus is settled in some environments
        def select_all():
            cursor = note.text_item.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            note.text_item.setTextCursor(cursor)
            
        QTimer.singleShot(10, select_all)
        
    def remove_backdrop_safely(self, backdrop):
        self.scene.removeItem(backdrop)

    def delete_selected_notes(self):
        selected = self.scene.selectedItems()
        to_remove = [it for it in selected if isinstance(it, (TextNoteItem, BackdropItem, DrawItem))]
        if not to_remove: return
        
        for it in to_remove:
            if isinstance(it, BackdropItem):
                self.remove_backdrop_safely(it)
            elif isinstance(it, DrawItem):
                self.delete_draw_item_safely(it)
            else:
                self.scene.removeItem(it)
        self.scene_items_changed.emit()
        self._update_note_toolbar()

    def get_drawing_cache_dir(self):
        config = self.get_config()
        location = config.get("drawing_cache_location", "relative to source folder")
        path_setting = config.get("drawing_cache_path", "_drawcache")
        
        if location == "relative to source folder":
            source_folder = ""
            if self.model and hasattr(self.model, "source_folder") and self.model.source_folder:
                source_folder = self.model.source_folder
            elif hasattr(self, "parent") and self.parent() and hasattr(self.parent(), "model") and self.parent().model and hasattr(self.parent().model, "source_folder"):
                source_folder = self.parent().model.source_folder
                
            if not source_folder:
                source_folder = os.getcwd()
            
            cache_dir = os.path.join(source_folder, path_setting)
        else:
            if not path_setting:
                path_setting = "_drawcache"
            if os.path.isabs(path_setting):
                cache_dir = path_setting
            else:
                cache_dir = os.path.abspath(path_setting)
                
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def enter_draw_mode(self):
        if self._draw_mode_active:
            return
            
        self.note_toolbar.hide()
        
        self._draw_mode_active = True
        self.view.setDragMode(QGraphicsView.NoDrag)
        
        selected = self.scene.selectedItems()
        self._edit_draw_item = None
        if len(selected) == 1 and isinstance(selected[0], DrawItem):
            self._edit_draw_item = selected[0]
            self._edit_draw_item.setVisible(False)
            
        visible_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        if self._edit_draw_item:
            self.canvas_rect = visible_rect.united(self._edit_draw_item.sceneBoundingRect())
        else:
            self.canvas_rect = visible_rect
            
        self._canvas_item = DrawingCanvasItem(self.canvas_rect, self)
        
        if self._edit_draw_item:
            self._canvas_item.load_base_image(
                self._edit_draw_item.file_path, 
                self._edit_draw_item.pos(), 
                self._edit_draw_item.width, 
                self._edit_draw_item.height
            )
            
        self.scene.addItem(self._canvas_item)
        
        cfg = self.get_config()
        default_color_hex = cfg.get("draw_default_color", "#ff0000")
        default_thickness = cfg.get("draw_default_thickness", "5 px")
        default_style = cfg.get("draw_default_style", "Normal")
        
        default_color = QColor(default_color_hex)
        if not default_color.isValid():
            default_color = QColor(255, 0, 0)

        self.draw_toolbar.btn_brush.setChecked(True)
        self.draw_toolbar.btn_eraser.setChecked(False)
        self.draw_toolbar.btn_circle.setChecked(False)
        self.draw_toolbar.btn_arrow.setChecked(False)
        self.draw_toolbar.btn_rect.setChecked(False)
        self._canvas_item.active_tool = "brush"
        self._canvas_item.active_color = default_color
        self.draw_toolbar.update_color_button(default_color)
        
        self.draw_toolbar.combo_thickness.blockSignals(True)
        self.draw_toolbar.combo_style.blockSignals(True)
        self.draw_toolbar.combo_thickness.setCurrentText(default_thickness)
        self.draw_toolbar.combo_style.setCurrentText(default_style)
        self.draw_toolbar.combo_thickness.blockSignals(False)
        self.draw_toolbar.combo_style.blockSignals(False)
        
        vp_rect = self.view.viewport().geometry()
        self.draw_toolbar.adjustSize()
        global_pos = self.view.viewport().mapToGlobal(
            QPoint(vp_rect.width() // 2 - self.draw_toolbar.width() // 2, 20)
        )
        self.draw_toolbar.move(global_pos)
        self.draw_toolbar.show()
        self.view.setFocus()

    def exit_draw_mode(self, save=True):
        if not self._draw_mode_active:
            return
            
        self._draw_mode_active = False
        self.draw_toolbar.hide()
        
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        
        if self._canvas_item:
            final_image = self._canvas_item.render_canvas()
            rect = get_non_transparent_rect(final_image)
            
            self.scene.removeItem(self._canvas_item)
            self._canvas_item = None
            
            cache_dir = self.get_drawing_cache_dir()
            
            if save and rect.isValid() and not rect.isEmpty():
                cropped_image = final_image.copy(rect)
                width = rect.width()
                height = rect.height()
                scene_pos = self.canvas_rect.topLeft() + rect.topLeft()
                
                if self._edit_draw_item:
                    file_path = self._edit_draw_item.file_path
                    cropped_image.save(file_path, "PNG")
                    
                    self._edit_draw_item.prepareGeometryChange()
                    self._edit_draw_item.setPos(scene_pos)
                    self._edit_draw_item.width = width
                    self._edit_draw_item.height = height
                    self._edit_draw_item.pixmap = QPixmap(file_path)
                    self._edit_draw_item.setVisible(True)
                    self._edit_draw_item.update()
                else:
                    item_uuid = str(uuid.uuid4())
                    file_path = os.path.join(cache_dir, f"drawing_{item_uuid}.png")
                    cropped_image.save(file_path, "PNG")
                    
                    draw_item = DrawItem(scene_pos, file_path, width, height)
                    draw_item.uuid = item_uuid
                    self.scene.addItem(draw_item)
            else:
                if self._edit_draw_item:
                    if save:
                        self.delete_draw_item_safely(self._edit_draw_item)
                    else:
                        self._edit_draw_item.setVisible(True)
                        
            self._edit_draw_item = None
            
        self.scene_items_changed.emit()

    def delete_draw_item_safely(self, item):
        if item in self.scene.items():
            self.scene.removeItem(item)
        if os.path.exists(item.file_path):
            try:
                os.remove(item.file_path)
            except Exception as e:
                print(f"Failed to delete drawing cache file: {e}")

    def clear_canvas_drawings(self):
        if self._canvas_item:
            self._canvas_item.strokes = []
            self._canvas_item.base_image = None
            self._canvas_item.canvas_image = None
            self._canvas_item.update()

    def add_backdrop(self):
        # 1. Calculate geometry
        selected = self.scene.selectedItems()
        # Filter for top-level visible items (ThumbnailItem, TextNoteItem)
        groupable = [it for it in selected if not it.parentItem()]
        
        margin = 250
        has_selection = bool(groupable)
        if groupable:
            # Enclose selected items
            rect = groupable[0].sceneBoundingRect()
            for it in groupable[1:]:
                rect = rect.united(it.sceneBoundingRect())
            
            # Add margin (larger on top for the title bar)
            rect = rect.adjusted(-margin, -margin - 150, margin, margin)
        else:
            # Default at cursor or center
            if hasattr(self, "_last_click_scene_pos"):
                scene_pos = self._last_click_scene_pos
            else:
                v_rect = self.view.viewport().rect()
                scene_pos = self.view.mapToScene(v_rect.center())
            rect = QRectF(scene_pos.x(), scene_pos.y(), 800, 600)
            
        # 2. Show Dialog
        dialog = BackdropDialog(self)
        
        # Creation context: apply doesn't make much sense until created, 
        # but we can handle it by creating a temporary item or just letting them hit Done.
        temp_item = None
        
        def apply_to_temp(vals):
            nonlocal temp_item
            if not temp_item:
                temp_item = BackdropItem(rect, vals)
                self.scene.addItem(temp_item)
                temp_item.delete_requested.connect(self.delete_backdrop)
            else:
                temp_item.set_data(vals)
        
        dialog.applyRequested.connect(apply_to_temp)
        
        if dialog.exec():
            data = dialog.get_values()

            # 3. Extend rect based on label alignment when items were selected
            final_rect = QRectF(rect)  # copy
            if has_selection:
                alignment = data.get("label_alignment", "")
                extension = final_rect.height() * 0.20
                if "Top" in alignment:
                    # Extend the top edge upward
                    final_rect.setTop(final_rect.top() - extension)
                elif "Bottom" in alignment:
                    # Extend the bottom edge downward
                    final_rect.setBottom(final_rect.bottom() + extension)

            if not temp_item:
                backdrop = BackdropItem(final_rect, data)
                self.scene.addItem(backdrop)
                backdrop.delete_requested.connect(self.delete_backdrop)
                self.scene_items_changed.emit()
            else:
                # Reposition temp_item to reflect final_rect
                temp_item.prepareGeometryChange()
                temp_item.setPos(final_rect.topLeft())
                temp_item.width = final_rect.width()
                temp_item.height = final_rect.height()
                temp_item.set_data(data)
                backdrop = temp_item
            
            # Select it
            self.scene.clearSelection()
            backdrop.setSelected(True)
        else:
            if temp_item:
                self.scene.removeItem(temp_item)

    def edit_backdrop(self, backdrop):
        data = {
            "name": backdrop.name,
            "label": backdrop.label,
            "label_size": backdrop.label_size,
            "label_color": backdrop.label_color.name(),
            "label_bold": backdrop.label_bold,
            "label_italic": backdrop.label_italic,
            "label_strike": backdrop.label_strike,
            "label_underline": backdrop.label_underline,
            "label_alignment": backdrop.label_alignment,
            "appearance": backdrop.appearance,
            "border_color": backdrop.border_color.name(),
            "fill_color": backdrop.fill_color.name()
        }
        dialog = BackdropDialog(self, data)
        dialog.applyRequested.connect(backdrop.set_data)
        if dialog.exec():
            new_data = dialog.get_values()
            backdrop.set_data(new_data)

    def delete_selected_backdrops(self):
        selected = self.scene.selectedItems()
        to_remove = [it for it in selected if isinstance(it, BackdropItem)]
        for it in to_remove:
            self.remove_backdrop_safely(it)

    def delete_backdrop(self, backdrop):
        selected_backdrops = [it for it in self.scene.selectedItems() if isinstance(it, BackdropItem)]
        if backdrop in selected_backdrops:
            for it in selected_backdrops:
                self.remove_backdrop_safely(it)
        else:
            self.remove_backdrop_safely(backdrop)
        self.scene_items_changed.emit()
