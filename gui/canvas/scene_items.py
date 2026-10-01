"""Text notes and backdrops (they reference each other, so they live together)."""
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
from gui.canvas.thumbnail_item import ThumbnailItem


class CanvasScene(QGraphicsScene):
    """QGraphicsScene that keeps the Python side of every item it holds alive.

    Items written in Python (notes, backdrops, drawings) are a C++ object plus a
    Python wrapper that holds paint()/boundingRect(). PySide does not always keep
    that wrapper alive just because the item is in a scene: once nothing in Python
    referenced a note (e.g. after it was deselected and the note toolbar let go of
    it), the garbage collector dropped the wrapper. The C++ item stayed in the
    scene (still listed in the right panel) but drew nothing and could not be
    clicked - the "note disappears" bug. Holding a reference here fixes that.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._py_items = {}

    def addItem(self, item):
        super().addItem(item)
        self._py_items[id(item)] = item

    def removeItem(self, item):
        self._py_items.pop(id(item), None)
        super().removeItem(item)

    def clear(self):
        super().clear()
        self._py_items.clear()


# Text note defaults (one place): font size in points, padding between text and frame in px
NOTE_DEFAULT_FONT_PT = 216
NOTE_PADDING = 24


class NoteTextItem(QGraphicsTextItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        parent = self.parentItem()
        if isinstance(parent, TextNoteItem):
            parent.on_text_focus_out(event)


class TextNoteItem(QGraphicsObject):
    moving_started = Signal()
    moving_finished = Signal()
    
    def __init__(self, pos, text="New Note"):
        super().__init__()
        self.setPos(pos)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(5000)  # Always above backdrops (-1000) and thumbnails (0)
        self.uuid = str(uuid.uuid4())
        self.setCacheMode(QGraphicsItem.NoCache) # Prevent clipping artifacts
        
        self.width = 400
        self.height = 200
        # False: the frame follows the text (grows and shrinks). True after the user
        # resizes the note by hand (or it was loaded with a saved size): keep the
        # size and wrap the text inside it instead.
        self._manual_size = False

        self.text_item = NoteTextItem(self)
        self.text_item.setDefaultTextColor(QColor("#e0e0e0"))
        font = QFont("Arial", NOTE_DEFAULT_FONT_PT)
        self.text_item.setFont(font)
        self.text_item.setPos(NOTE_PADDING, NOTE_PADDING)
        self.text_item.setPlainText(text)
        self.bg_color = QColor(30, 30, 30, 230)
        self._resizing = False
        self._resize_mode = None # "bottom_right", "right", "bottom"
        self._resize_start_pos = None
        self._resize_start_size = None
        
        self.setAcceptHoverEvents(True)
        self.text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        # Pass clicks to parent for moving
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)
        self.text_item.document().contentsChanged.connect(self._on_text_changed)
        
    def fit_to_text(self):
        """Make the frame hug the text (no wrapping), with NOTE_PADDING around it."""
        self.text_item.setTextWidth(-1)  # natural width, no wrapping
        br = self.text_item.boundingRect()
        new_w = max(40.0, br.width() + 2 * NOTE_PADDING)
        new_h = max(30.0, br.height() + 2 * NOTE_PADDING)
        if (new_w, new_h) != (self.width, self.height):
            self.prepareGeometryChange()
            self.width, self.height = new_w, new_h
            self.update()
            parent = self.parentItem()
            if isinstance(parent, BackdropItem):
                parent.child_geometry_changed()

    def _on_text_changed(self):
        if not getattr(self, "_manual_size", False):
            self.fit_to_text()
            self.setCursor(Qt.PointingHandCursor)
            return
        # Hand-sized note: only grow when the text overflows
        br = self.text_item.boundingRect()
        needed_w = br.width() + 40
        needed_h = br.height() + 40
        
        if needed_w > self.width or needed_h > self.height:
            self.prepareGeometryChange()
            self.width = max(self.width, needed_w)
            self.height = max(self.height, needed_h)
            self.text_item.setTextWidth(self.width - 20)
            self.update()
            
            parent = self.parentItem()
            if isinstance(parent, BackdropItem):
                parent.child_geometry_changed()
        
        # Increase click area for grabbing
        self.setCursor(Qt.PointingHandCursor)
        
    def boundingRect(self):
        # Very generous margin to ensure borders and handles are never clipped
        margin = 30
        return QRectF(-margin, -margin, self.width + margin*2, self.height + margin*2)
        
    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen_w = 6 if self.isSelected() else 2
        
        # 1. Fill background (no pen to avoid edge artifacts)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.bg_color)
        painter.drawRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        # 2. Border only while selected (a deselected note shows just its background)
        if self.isSelected():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#00bcd4"), pen_w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
            # Inset the border path slightly to avoid clipping at edge of itemsBoundingRect
            path = QPainterPath()
            path.addRoundedRect(pen_w/2, pen_w/2, self.width - pen_w, self.height - pen_w, 10, 10)
            painter.drawPath(path)
        
        # Draw resize handles if selected
        if self.isSelected():
            painter.setBrush(QColor("#00bcd4"))
            painter.setPen(QPen(Qt.white, 1))
            
            # Bottom-right corner handle (circle)
            painter.drawEllipse(self.width - 10, self.height - 10, 12, 12)
            
            # Right edge handle (pill)
            painter.drawRoundedRect(self.width - 6, self.height // 2 - 15, 6, 30, 3, 3)
            
            # Bottom edge handle (pill)
            painter.drawRoundedRect(self.width // 2 - 15, self.height - 6, 30, 6, 3, 3)
            
        painter.restore()

    def mousePressEvent(self, event):
        # Resize logic
        if self.isSelected():
            x, y = event.pos().x(), event.pos().y()
            margin = 15
            
            if x > self.width - margin and y > self.height - margin:
                self._resizing = True
                self._resize_mode = "bottom_right"
            elif x > self.width - margin:
                self._resizing = True
                self._resize_mode = "right"
            elif y > self.height - margin:
                self._resizing = True
                self._resize_mode = "bottom"
                
            if self._resizing:
                self._resize_start_pos = event.scenePos()
                self._resize_start_size = (self.width, self.height)
                event.accept()
                return
                
        if event.button() == Qt.LeftButton:
            self.moving_started.emit()
        super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            
            new_w = self.width
            new_h = self.height
            if self._resize_mode in ["bottom_right", "right"]:
                new_w = max(100, self._resize_start_size[0] + delta.x())
            if self._resize_mode in ["bottom_right", "bottom"]:
                new_h = max(50, self._resize_start_size[1] + delta.y())

            if new_w != self.width or new_h != self.height:
                self.prepareGeometryChange()
                self.width = new_w
                self.height = new_h
                self.update()
            
            parent = self.parentItem()
            if isinstance(parent, BackdropItem):
                parent.child_geometry_changed()
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        if self._resizing:
            # Finalise text wrapping now that the drag is done; from now on keep this size
            self._manual_size = True
            self.text_item.setTextWidth(self.width - 2 * NOTE_PADDING)
            self.update()
        self._resizing = False
        self._resize_mode = None
        if event.button() == Qt.LeftButton:
            self.moving_finished.emit()
        super().mouseReleaseEvent(event)

        
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemParentChange:
            # Never allow a text note to become a child of a BackdropItem;
            # that would place it in the backdrop's stacking context (z=-1000)
            # and make it appear behind thumbnails.
            if isinstance(value, BackdropItem):
                return None  # reject reparenting
        elif change == QGraphicsItem.ItemSelectedChange:
            if not value:  # Deselected
                QTimer.singleShot(0, self._safe_deselect)
        return super().itemChange(change, value)

    def _safe_deselect(self):
        if not self.isSelected():
            self.on_text_focus_out(None)
            if self.text_item.hasFocus():
                self.text_item.clearFocus()
        
    def mouseDoubleClickEvent(self, event):
        self.text_item.setAcceptedMouseButtons(Qt.LeftButton)
        self.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.text_item.setFocus()
        # Select all text on double click
        cursor = self.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.text_item.setTextCursor(cursor)
        super().mouseDoubleClickEvent(event)

    def on_text_focus_out(self, event):
        if self.text_item.textInteractionFlags() == Qt.NoTextInteraction:
            return
        self.text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)
        # Clear the text cursor selection
        cursor = self.text_item.textCursor()
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        self.update()
        
        # Notify that scene items changed (updates filter tree view label)
        scene = self.scene()
        if scene:
            parent = scene.parent()
            if parent and hasattr(parent, "notify_scene_items_changed"):
                parent.notify_scene_items_changed()
            elif parent and hasattr(parent, "scene_items_changed"):
                parent.scene_items_changed.emit()

    def focusOutEvent(self, event):
        self.on_text_focus_out(event)
        super().focusOutEvent(event)


class BackdropItem(QGraphicsObject):
    delete_requested = Signal(object)  # emits self

    def __init__(self, rect, data):
        super().__init__()
        self.setPos(rect.topLeft())
        self.width = rect.width()
        self.height = rect.height()
        self.set_data(data)
        
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(-1000) # Behind thumbnails
        self.uuid = str(uuid.uuid4())
        
        self._resizing = False
        self._resize_corner = None # "top_left", "top_right", "bottom_left", "bottom_right"
        self._resize_start_rect = None
        self._move_start_pos = None
        self._content_offsets = {} # item -> offset
        self._is_dragging_top_bar = False
        
        self.top_bar_height = 150
        self.corner_size = 150
        
    def set_data(self, data):
        self.prepareGeometryChange()
        self.name = data.get("name", "")
        self.label = data.get("label", "")
        self.label_size = data.get("label_size", 200)
        self.label_color = QColor(data.get("label_color", "white"))
        self.label_bold = data.get("label_bold", True)
        self.label_italic = data.get("label_italic", False)
        self.label_strike = data.get("label_strike", False)
        self.label_underline = data.get("label_underline", False)
        self.label_alignment = data.get("label_alignment", "Top Left")
        self.appearance = data.get("appearance", "Border")
        self.border_color = QColor(data.get("border_color", "magenta"))
        self.fill_color = QColor(data.get("fill_color", "#282828"))
        self.setZValue(-1000) # Ensure backdrop is always behind thumbnails and notes
        self.update()

    def child_geometry_changed(self):
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self):
        base_rect = QRectF(-2, -2, self.width + 4, self.height + 4)
        children_rect = self.childrenBoundingRect()
        if not children_rect.isEmpty():
            return base_rect.united(children_rect)
        return base_rect

    def shape(self):
        path = QPainterPath()
        cs = self.corner_size
        # Top bar is interactive, shrunk horizontally so corner triangles are accessible
        path.addRect(cs, 0, self.width - 2 * cs, self.top_bar_height)
        # Corners are interactive for resizing (and TL acts as delete)
        path.addRect(0, 0, cs, cs) # TL
        path.addRect(self.width - cs, 0, cs, cs) # TR
        path.addRect(0, self.height - cs, cs, cs) # BL
        path.addRect(self.width - cs, self.height - cs, cs, cs) # BR
        return path

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        base_w = 2
        if lod < 0.3: base_w = 6
        elif lod < 0.6: base_w = 4
        
        # 1. Background
        if self.appearance == "Fill":
            painter.setBrush(self.fill_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(0, 0, self.width, self.height)
        else:
            painter.setBrush(Qt.NoBrush)
            
        # 2. Border
        pen_w = max(1, base_w // 2)
        if self.isSelected():
            pen_w += 2
            pen = QPen(Qt.white, pen_w) # White border when selected for clarity
        else:
            pen = QPen(self.border_color, pen_w)
            
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width, self.height)
        
        cs = self.corner_size

        # 3. Top Bar (Name area) — shrunk horizontally so corner triangles remain visible
        top_bar_rect = QRectF(cs, 0, self.width - 2 * cs, self.top_bar_height)
        painter.setBrush(self.border_color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(top_bar_rect)
        
        # 4. Name Text
        if self.name:
            painter.setPen(Qt.black if self.border_color.lightness() > 128 else Qt.white)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(60) # 6x bigger than 10
            painter.setFont(font)
            painter.drawText(top_bar_rect, Qt.AlignCenter, self.name)
            
        # 5. Label Text
        if self.label:
            painter.setPen(self.label_color)
            font = painter.font()
            font.setPointSize(self.label_size)
            font.setBold(self.label_bold)
            font.setItalic(self.label_italic)
            font.setStrikeOut(self.label_strike)
            font.setUnderline(self.label_underline)
            painter.setFont(font)
            
            # Alignment logic
            align = Qt.AlignLeft | Qt.AlignTop
            if "Center" in self.label_alignment: align = (align & ~Qt.AlignHorizontal_Mask) | Qt.AlignHCenter
            if "Right" in self.label_alignment: align = (align & ~Qt.AlignHorizontal_Mask) | Qt.AlignRight
            if "Middle" in self.label_alignment: align = (align & ~Qt.AlignVertical_Mask) | Qt.AlignVCenter
            if "Bottom" in self.label_alignment: align = (align & ~Qt.AlignVertical_Mask) | Qt.AlignBottom
            
            # Padding for text (Space between border and text)
            padding = 100
            text_rect = QRectF(padding, self.top_bar_height + padding, 
                               self.width - (padding * 2), 
                               self.height - self.top_bar_height - (padding * 2))
            painter.drawText(text_rect, align, self.label)
            
        # 6. Corner Handles (Triangles)
        painter.setBrush(self.border_color)
        painter.setPen(Qt.NoPen)
        
        # Top-left
        painter.drawPolygon([QPointF(0,0), QPointF(cs, 0), QPointF(0, cs)])
        # Top-right
        painter.drawPolygon([QPointF(self.width,0), QPointF(self.width - cs, 0), QPointF(self.width, cs)])
        # Bottom-left
        painter.drawPolygon([QPointF(0, self.height), QPointF(cs, self.height), QPointF(0, self.height - cs)])
        # Bottom-right
        painter.drawPolygon([QPointF(self.width, self.height), QPointF(self.width - cs, self.height), QPointF(self.width, self.height - cs)])

        # 7. Delete × symbol on the top bar's right end
        btn_x = self.width - cs - self.top_bar_height
        cross_cx = btn_x + self.top_bar_height / 2
        cross_cy = self.top_bar_height / 2
        cross_r = self.top_bar_height * 0.2
        
        # Decide contrast color
        contrast_color = Qt.black if self.border_color.lightness() > 128 else Qt.white
        
        # Draw separator line
        sep_pen = QPen(contrast_color, 2)
        painter.setPen(sep_pen)
        painter.drawLine(QPointF(btn_x, 0), QPointF(btn_x, self.top_bar_height))
        
        # Draw the × cross
        cross_pen = QPen(contrast_color, max(3, self.top_bar_height * 0.06))
        cross_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(cross_pen)
        painter.drawLine(QPointF(cross_cx - cross_r, cross_cy - cross_r),
                         QPointF(cross_cx + cross_r, cross_cy + cross_r))
        painter.drawLine(QPointF(cross_cx + cross_r, cross_cy - cross_r),
                         QPointF(cross_cx - cross_r, cross_cy + cross_r))
        
        painter.restore()

    def _is_in_delete_zone(self, x, y):
        """Check if (x, y) is within the top-bar right-side delete × area."""
        cs = self.corner_size
        button_w = self.top_bar_height
        return (self.width - cs - button_w <= x <= self.width - cs) and (0 <= y <= self.top_bar_height)

    def mousePressEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        cs = self.corner_size
        print(f"DEBUG PRESS: x={x}, y={y}, is_movable={self.flags() & QGraphicsItem.ItemIsMovable}")
        
        # Check delete button first
        if self._is_in_delete_zone(x, y):
            event.accept()
            self.delete_requested.emit(self)
            return

        # Check resize corners
        if x < cs and y < cs:
            self._resizing = True
            self._resize_corner = "top_left"
        elif x > self.width - cs and y < cs:
            self._resizing = True
            self._resize_corner = "top_right"
        elif x < cs and y > self.height - cs:
            self._resizing = True
            self._resize_corner = "bottom_left"
        elif x > self.width - cs and y > self.height - cs:
            self._resizing = True
            self._resize_corner = "bottom_right"
            
        if self._resizing:
            self._resize_start_rect = QRectF(self.pos().x(), self.pos().y(), self.width, self.height)
            self._move_start_pos = event.scenePos()
            event.accept()
            return
            
        # Check top bar (shrunken: between cs and width-cs)
        if y < self.top_bar_height and cs <= x <= self.width - cs:
            self._is_dragging_top_bar = True
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self._content_offsets = {}
            if not (event.modifiers() & Qt.ControlModifier):
                backdrop_rect = self.sceneBoundingRect()
                # Populating offsets for items inside the backdrop (like thumbnails and text notes)
                for item in self.scene().items(backdrop_rect):
                    if item == self or item.parentItem(): continue
                    if not isinstance(item, (ThumbnailItem, TextNoteItem)):
                        continue
                    if item.isSelected() and self.isSelected(): continue
                    if backdrop_rect.contains(item.sceneBoundingRect().center()):
                        self._content_offsets[item] = item.pos() - self.pos()
        else:
            self._is_dragging_top_bar = False
            self.setFlag(QGraphicsItem.ItemIsMovable, False)
            
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._move_start_pos
            r = self._resize_start_rect
            
            new_x, new_y, new_w, new_h = r.x(), r.y(), r.width(), r.height()
            
            min_w, min_h = 100, 100
            
            if self._resize_corner == "top_left":
                new_x = min(r.right() - min_w, r.x() + delta.x())
                new_y = min(r.bottom() - min_h, r.y() + delta.y())
                new_w = r.right() - new_x
                new_h = r.bottom() - new_y
            elif self._resize_corner == "top_right":
                new_y = min(r.bottom() - min_h, r.y() + delta.y())
                new_w = max(min_w, r.width() + delta.x())
                new_h = r.bottom() - new_y
            elif self._resize_corner == "bottom_left":
                new_x = min(r.right() - min_w, r.x() + delta.x())
                new_w = r.right() - new_x
                new_h = max(min_h, r.height() + delta.y())
            elif self._resize_corner == "bottom_right":
                new_w = max(min_w, r.width() + delta.x())
                new_h = max(min_h, r.height() + delta.y())
                
            self.prepareGeometryChange()
            self.setPos(new_x, new_y)
            self.width = new_w
            self.height = new_h
            self.update()
            return

        # If dragging top bar, move contents too
        if self._is_dragging_top_bar:
            # Let standard QGraphicsItem handle the backdrop movement itself
            # We just need to sync the contents if we are the one being dragged
            if self.scene().mouseGrabberItem() == self:
                super().mouseMoveEvent(event)
                # Move contents based on their offsets relative to us
                for item, offset in self._content_offsets.items():
                    item.setPos(self.pos() + offset)
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_corner = None
        self._is_dragging_top_bar = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True) # Restore for selection/other uses
        super().mouseReleaseEvent(event)
        self._content_offsets = {}

    def itemChange(self, change, value):
        return super().itemChange(change, value)
