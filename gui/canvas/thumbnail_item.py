"""ThumbnailItem: one footage item on the canvas, plus its background image loader."""
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


# Largest item size reachable by dragging the resize corner (was 1500)
MAX_ITEM_SIZE = 20000


class ThumbnailItem(QGraphicsObject):
    def __init__(self, item_data):
        super().__init__()
        self.data = item_data
        self.size = 150
        self.font_size = 10
        self.is_manually_moved = getattr(item_data, "is_manually_moved", False)
        self.is_custom_size = getattr(item_data, "is_custom_size", False)
        self.cached_bw = None
        self.is_editing = False
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.loading_sig_connected = False
        self.cached_label = ""
        self.setCacheMode(QGraphicsItem.NoCache)
        self.tooltip_templates = {}


    def update_tooltip(self, templates, model):
        self.tooltip_templates = templates
        if not model:
            return
            
        template = getattr(model, "tooltip_template", "")
        
        if not template and templates:
            cat = getattr(self.data, "category", "").lower()
            key = "other"
            if getattr(self.data, "is_ayon_item", False) or cat == "ayon":
                key = "ayon"
            elif "sequence" in cat: key = "sequences"
            elif "still" in cat: key = "stills"
            elif "video" in cat: key = "videos"
            template = templates.get(f"item_info_{key}", "")
            
        if template:
            if hasattr(model, "expand_tokens"):
                expanded = model.expand_tokens(template, self.data)
            else:
                expanded = model._expand_string(template, self.data, use_global_camel=False)
            self.setToolTip(expanded)
        else:
            self.setToolTip("")


    def _get_aspect_ratio(self):
        w = 1
        h = 1
        if self.data and isinstance(getattr(self.data, "metadata", None), dict):
            w = self.data.metadata.get("width", 1)
            h = self.data.metadata.get("height", 1)
        try:
            fw = float(w) if w is not None else 1.0
            fh = float(h) if h is not None else 1.0
        except (ValueError, TypeError):
            fw, fh = 1.0, 1.0

        if (fw <= 1.0 or fh <= 1.0) and self.data:
            thumb_img = getattr(self.data, "thumbnail_image", None)
            thumb_pix = getattr(self.data, "thumbnail", None)
            if thumb_img and not thumb_img.isNull():
                fw = float(thumb_img.width())
                fh = float(thumb_img.height())
            elif thumb_pix and not thumb_pix.isNull():
                fw = float(thumb_pix.width())
                fh = float(thumb_pix.height())

        aspect = fw / fh if fh > 0 else 1.0
        return aspect

    def boundingRect(self):
        # 1. Calculate aspect ratio
        aspect = self._get_aspect_ratio()
            
        # 2. Calculate height
        thumb_h = self.size / aspect
        
        # 3. Add label area if visible
        show_text = True
        if self.scene() and hasattr(self.scene(), "show_labels"):
            show_text = self.scene().show_labels
        
        label_area = 0
        if show_text:
            font_size = getattr(self, 'font_size', 10)
            line_height = font_size * 1.5
            label_area = line_height * 3.5 + 10
            
        return QRectF(0, 0, self.size + 20, thumb_h + 20 + label_area)

    def get_image_rect(self):
        """Get the QRectF of the drawn thumbnail image in item coordinates."""
        show_text = getattr(self.scene(), "show_labels", True) if self.scene() else True
        label_area = 0
        if show_text:
            font_size = getattr(self, 'font_size', 10)
            line_height = font_size * 1.5
            label_area = line_height * 3.5 + 10

        br = self.boundingRect()
        full_h = br.height() - label_area - 10
        rect = QRectF(5, 5, br.width() - 10, full_h)
        
        pixmap = self.data.thumbnail
        if pixmap:
            scaled = pixmap.size()
            scaled.scale(rect.size().toSize(), Qt.KeepAspectRatio)
            thumb_rect = QRectF(0, 0, scaled.width(), scaled.height())
        else:
            aspect = self._get_aspect_ratio()
            if aspect > (rect.width() / rect.height()):
                nw = rect.width()
                nh = nw / aspect
            else:
                nh = rect.height()
                nw = nh * aspect
            thumb_rect = QRectF(0, 0, nw, nh)

        thumb_rect.moveCenter(rect.center())
        return thumb_rect

    def paint(self, painter, option, widget):
        painter.save()
        # LOD check: skip complex stuff if tiny
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        
        pixmap = self.data.thumbnail
        if lod > 0.6:
            if self.data.high_res_thumbnail:
                pixmap = self.data.high_res_thumbnail
            elif not self.data.is_high_res_loading and not getattr(self.data, "high_res_failed", False):
                self.request_high_res()

        # 1. Calculate thumbnail area
        # Respect the dynamic height from boundingRect
        show_text = getattr(self.scene(), "show_labels", True) if self.scene() else True
        label_area = 0
        if show_text:
            font_size = getattr(self, 'font_size', 10)
            line_height = font_size * 1.5
            label_area = line_height * 3.5 + 10

        br = self.boundingRect()
        full_h = br.height() - label_area - 10
        rect = QRectF(5, 5, br.width() - 10, full_h)
        
        if pixmap:
            scaled = pixmap.size()
            scaled.scale(rect.size().toSize(), Qt.KeepAspectRatio)
            thumb_rect = QRectF(0, 0, scaled.width(), scaled.height())
        else:
            # Placeholder logic
            aspect = self._get_aspect_ratio()
            
            # Fit placeholder in rect with aspect ratio
            if aspect > (rect.width() / rect.height()):
                nw = rect.width()
                nh = nw / aspect
            else:
                nh = rect.height()
                nw = nh * aspect
            thumb_rect = QRectF(0, 0, nw, nh)

        thumb_rect.moveCenter(rect.center())

        # 2. Draw placeholder or pixmap
        if not pixmap:
            if getattr(self.data, "is_ayon_item", False):
                painter.fillRect(thumb_rect, QColor("#000000"))
            else:
                painter.fillRect(thumb_rect, QColor("#333333"))
        else:
            painter.drawPixmap(thumb_rect, pixmap, QRectF(pixmap.rect()))

        # 3. Draw Borders (Show Frames off: only around selected items)
        frames_on = getattr(self.scene(), "show_frames", True) or self.isSelected()
        base_w = 2
        if lod < 0.3:
            base_w = 6
        elif lod < 0.6:
            base_w = 4
            
        if not frames_on:
            pass
        elif getattr(self.data, "is_ayon_item", False):
            if self.isSelected():
                sel_width = base_w + 2
                pen = QPen(QColor("#00e5ff"), sel_width)
            else:
                pen = QPen(QColor("#00bcd4"), max(1, base_w // 2))
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(thumb_rect.adjusted(-2, -2, 2, 2))
        else:
            if self.isSelected():
                sel_width = base_w + 2
                # a paired review shows its selection dimmer than its main file
                is_paired_review = getattr(self.data, "pair_main", None) is not None
                pen = QPen(QColor("#6e6e6e") if is_paired_review else QColor("#ffffff"), sel_width)
                pen.setCosmetic(True)
                painter.setPen(pen)
            else:
                pen = QPen(QColor("#444444"), max(1, base_w // 2))
                pen.setCosmetic(True)
                painter.setPen(pen)
            painter.drawRect(thumb_rect.adjusted(-4, -4, 4, 4))

            # Inner Border (Tagging)
            if self.data.is_tagged:
                tag_color = QColor("#76ff03") if self.data.ayon_path else QColor("#558b2f")
            else:
                tag_color = QColor("#c62828")
            tag_pen = QPen(tag_color, max(1, base_w // 2))
            tag_pen.setCosmetic(True)
            painter.setPen(tag_pen)
            painter.drawRect(thumb_rect.adjusted(-2, -2, 2, 2))
        
        # 4. Label - at every zoom level (only the Show Text toggle hides it), not while editing
        if not self.is_editing and getattr(self.scene(), "show_labels", True):
            painter.setPen(QColor("#e0e0e0"))
            font = painter.font()
            
            base_size = getattr(self, 'font_size', 10)
            scale_factor = 1.0
            if lod < 0.9:
                scale_factor = min(1.0 / (lod ** 0.6), 5.0) # Cap growth at 5x
            
            font.setPointSizeF(base_size * scale_factor)
            painter.setFont(font)
            
            fm = QFontMetrics(font)
            line_height = fm.lineSpacing()
            label_height = line_height * 3.5 
            
            label_w = self.size
            label_x = (self.boundingRect().width() - label_w) / 2
            label_rect = QRectF(label_x, thumb_rect.bottom() + 5, label_w, label_height)
            
            if not self.cached_label:
                v_stack_enabled = getattr(self.data.model, "v_stack_enabled", False) if self.data.model else False
                key = self.data.model.get_version_stack_key(self.data) if (self.data.model and v_stack_enabled) else None
                stack = self.data.model.version_stacks.get(key) if (key and self.data.model) else None
                
                if v_stack_enabled and stack and len(stack["items"]) > 1:
                    self.cached_label = f"{self.data.label} <{stack['min']}-{stack['max']}>@{stack['picked']}"
                else:
                    self.cached_label = f"{self.data.label} (v{self.data.version})"
            
            t_opt = QTextOption(Qt.AlignLeft | Qt.AlignTop)
            t_opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            painter.drawText(label_rect, self.cached_label, t_opt)

        # Draw Ingest Check status triangle in top-left corner
        ingest_status = getattr(self.data, "ingest_status", "unknown")
        if ingest_status in ["OK", "Failed"]:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            tri_size = thumb_rect.height() * 0.20
            
            triangle = QPolygonF([
                QPointF(thumb_rect.left(), thumb_rect.top()),
                QPointF(thumb_rect.left() + tri_size, thumb_rect.top()),
                QPointF(thumb_rect.left(), thumb_rect.top() + tri_size)
            ])
            
            if ingest_status == "OK":
                tri_color = QColor(76, 175, 80, 230) # Green
            else:
                tri_color = QColor(244, 67, 54, 230) # Red
                
            painter.setPen(Qt.NoPen)
            painter.setBrush(tri_color)
            painter.drawPolygon(triangle)
            painter.restore()

        # 5. Draw resize handle grip in bottom-right corner (scaled with the hotspot);
        # with Show Frames off only on selected items, or while hovered
        if frames_on or getattr(self, "_hovered_handle", False):
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            is_hovered_handle = getattr(self, "_hovered_handle", False)
            if is_hovered_handle:
                color = QColor("#2196f3")
            elif self.isSelected():
                color = QColor("#ffffff")
            else:
                color = QColor("#888888")
            
            pen = QPen(color, 1.5)
            painter.setPen(pen)
            
            img_rect = self.get_image_rect()
            border_rect = img_rect.adjusted(-4, -4, 4, 4)
            r = border_rect.right()
            b = border_rect.bottom()
            
            k = self._handle_size() / 15.0  # grip drawn at the size of the hotspot
            pen.setWidthF(1.5 * k)
            painter.setPen(pen)
            painter.drawLine(QPointF(r - 12 * k, b - 4 * k), QPointF(r - 4 * k, b - 12 * k))
            painter.drawLine(QPointF(r - 8 * k, b - 4 * k), QPointF(r - 4 * k, b - 8 * k))
            painter.drawLine(QPointF(r - 4 * k, b - 4 * k), QPointF(r - 4 * k, b - 4 * k))
            painter.restore()
        
        painter.restore()

    def request_high_res(self):
        # We need to get back to the ThumbnailArea to start a worker
        # We can find it via the scene
        for view in self.scene().views():
            if hasattr(view.parent(), 'load_high_res'):
                view.parent().load_high_res(self)
                break

    def on_high_res_ready(self):
        self.update()

    def get_label_top(self):
        # Calculate the top of the label area (matches paint logic)
        rect = QRectF(5, 5, self.boundingRect().width() - 10, self.size + 10)
        pixmap = self.data.thumbnail
        if pixmap:
            scaled = pixmap.size()
            scaled.scale(rect.size().toSize(), Qt.KeepAspectRatio)
            thumb_rect = QRectF(0, 0, scaled.width(), scaled.height())
            thumb_rect.moveCenter(rect.center())
            return thumb_rect.bottom() + 5
        return rect.bottom() + 5

    def set_editing(self, editing):
        self.is_editing = editing
        self.cached_label = "" # Reset in case version changed
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            grabber = self.scene().mouseGrabberItem()
            is_user_move = False
            if grabber == self:
                is_user_move = True
            elif self.isSelected() and grabber and grabber.isSelected():
                is_user_move = True

            # If moved by user (interaction)
            if is_user_move:
                new_pos = value.toPointF() if hasattr(value, 'toPointF') else value
                
                # Only hide editor if this is a real drag, not a tiny wiggle during dblclick
                if grabber == self and (new_pos - self.pos()).manhattanLength() > 2:
                    for view in self.scene().views():
                        area = view.parent()
                        if hasattr(area, 'inline_editor') and area.inline_editor.isVisible():
                            # Use the proper finish method if possible
                            if hasattr(area, '_on_inline_editing_finished'):
                                area._on_inline_editing_finished()
                            else:
                                area.inline_editor.hide()

                self.is_manually_moved = True
                self.data.is_manually_moved = True
                self.data.position = (new_pos.x(), new_pos.y())
                self.data.has_placed_position = True
                for view in self.scene().views():
                    area = view.parent()
                    if hasattr(area, "item_positions") and hasattr(area, "_get_item_key"):
                        key = area._get_item_key(self.data)
                        if key:
                            area.item_positions[key] = (new_pos.x(), new_pos.y())

        if change in (QGraphicsItem.ItemPositionHasChanged, QGraphicsItem.ItemTransformHasChanged):
            if self.scene():
                for view in self.scene().views():
                    parent = view.parent()
                    while parent:
                        if hasattr(parent, "update_video_overlay_geometry"):
                            parent.update_video_overlay_geometry()
                            break
                        parent = parent.parent()

        return super().itemChange(change, value)

    # Resize corner: about this many screen pixels at any zoom (capped to a part of
    # the item, so small items keep most of their area for moving)
    HANDLE_SCREEN_PX = 18

    def _view_scale(self):
        sc = self.scene()
        if sc is not None and sc.views():
            s = sc.views()[0].transform().m11()
            if s > 0:
                return s
        return 1.0

    def _handle_size(self):
        """Size of the resize corner in item units: constant on screen, max 40% of the image."""
        img_rect = self.get_image_rect()
        size = self.HANDLE_SCREEN_PX / self._view_scale()
        cap = 0.4 * max(1.0, min(img_rect.width(), img_rect.height()))
        return max(15.0, min(size, cap))

    def _is_in_resize_handle(self, local_pos):
        img_rect = self.get_image_rect()
        border_rect = img_rect.adjusted(-4, -4, 4, 4)
        handle_size = self._handle_size()
        slack = 4 / self._view_scale()  # a few pixels outside the corner count too
        in_x = border_rect.right() - handle_size <= local_pos.x() <= border_rect.right() + slack
        in_y = border_rect.bottom() - handle_size <= local_pos.y() <= border_rect.bottom() + slack
        return in_x and in_y

    def hoverMoveEvent(self, event):
        in_handle = self._is_in_resize_handle(event.pos())
        if in_handle != getattr(self, "_hovered_handle", False):
            self._hovered_handle = in_handle
            self.update()
            
        if in_handle:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        try:
            super().hoverMoveEvent(event)
        except TypeError:
            pass

    def hoverLeaveEvent(self, event):
        if getattr(self, "_hovered_handle", False):
            self._hovered_handle = False
            self.update()
        self.setCursor(Qt.ArrowCursor)
        try:
            super().hoverLeaveEvent(event)
        except TypeError:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_in_resize_handle(event.pos()):
            self._resizing = True
            self._drag_start_pos = event.scenePos()
            self._drag_start_size = self.size
            
            # Collect other selected items and their start sizes
            self._selected_resizers = []
            if self.isSelected():
                for it in self.scene().selectedItems():
                    if isinstance(it, ThumbnailItem) and it != self:
                        self._selected_resizers.append((it, it.size))
            event.accept()
            return
            
        try:
            super().mousePressEvent(event)
        except TypeError:
            pass

    def mouseMoveEvent(self, event):
        if getattr(self, "_resizing", False):
            delta = event.scenePos() - self._drag_start_pos
            new_size = max(50, min(MAX_ITEM_SIZE, self._drag_start_size + delta.x()))
            
            self.prepareGeometryChange()
            self.size = new_size
            self.data.size = new_size
            self.cached_label = ""
            self.update()
            
            for it, start_size in getattr(self, "_selected_resizers", []):
                it.prepareGeometryChange()
                it_new_size = max(50, min(MAX_ITEM_SIZE, start_size + delta.x()))
                it.size = it_new_size
                it.data.size = it_new_size
                it.cached_label = ""
                it.update()
                
            event.accept()
            return
            
        try:
            super().mouseMoveEvent(event)
        except TypeError:
            pass

    def mouseReleaseEvent(self, event):
        if getattr(self, "_resizing", False):
            self._resizing = False
            
            # Save position and manual move state on all resized items
            self.data.position = (self.pos().x(), self.pos().y())
            self.data.is_manually_moved = True
            self.is_manually_moved = True
            self.data.is_custom_size = True
            self.is_custom_size = True
            
            for it, _ in getattr(self, "_selected_resizers", []):
                it.data.position = (it.pos().x(), it.pos().y())
                it.data.is_manually_moved = True
                it.is_manually_moved = True
                it.data.is_custom_size = True
                it.is_custom_size = True
                
            self._selected_resizers = []
            
            # Notify scene items changed
            if self.scene():
                self.scene().update()
                for view in self.scene().views():
                    view.viewport().update()
                    parent = view.parent()
                    while parent:
                        if hasattr(parent, "scene_items_changed"):
                            parent.scene_items_changed.emit()
                            break
                        parent = parent.parent()
            event.accept()
            return
            
        try:
            super().mouseReleaseEvent(event)
        except TypeError:
            pass


class ThumbnailWorkerSignals(QObject):
    finished = Signal(object, object) # item_data, pixmap


class ThumbnailWorker(QRunnable):
    def __init__(self, item_data, size=512):
        super().__init__()
        self.item_data = item_data
        self.size = size
        self.signals = ThumbnailWorkerSignals()

    def run(self):
        source = self.item_data.file_path
        if self.item_data.conversion_thumb_path and os.path.exists(self.item_data.conversion_thumb_path):
            source = self.item_data.conversion_thumb_path
        image = generate_thumbnail_image(source, self.size)
        self.signals.finished.emit(self.item_data, image)
