"""Sketch / draw mode items."""
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
from gui.canvas.scene_items import BackdropItem


def draw_arrow(painter, p1, p2, thickness, color):
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    angle = math.atan2(dy, dx)
    arrow_size = max(20.0, thickness * 5.0)
    offset = min(length * 0.8, arrow_size * 0.5)
    p_line_end = p2 - QPointF(offset * math.cos(angle), offset * math.sin(angle))
    painter.drawLine(p1, p_line_end)
    ap1 = p2 - QPointF(arrow_size * math.cos(angle - math.pi/6), arrow_size * math.sin(angle - math.pi/6))
    ap2 = p2 - QPointF(arrow_size * math.cos(angle + math.pi/6), arrow_size * math.sin(angle + math.pi/6))
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    poly = QPolygonF([p2, ap1, ap2])
    painter.drawPolygon(poly)
    painter.restore()


def get_non_transparent_rect(image):
    pixmap = QPixmap.fromImage(image)
    mask = pixmap.mask()
    if mask.isNull():
        return QRectF().toRect()
    region = QRegion(mask)
    return region.boundingRect()


class DrawingCanvasItem(QGraphicsItem):
    def __init__(self, rect, thumb_area):
        super().__init__()
        self.canvas_rect = rect
        self.thumb_area = thumb_area
        self.toolbar = thumb_area.draw_toolbar
        
        self.setZValue(10000)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        
        self.strokes = []
        self.current_stroke = None
        
        self.active_tool = "brush"
        self.active_color = QColor(255, 0, 0)
        
        self.canvas_image = None
        self.base_image = None
        
        self.canvas_image = QImage(self.canvas_rect.size().toSize(), QImage.Format_ARGB32_Premultiplied)
        self.canvas_image.fill(Qt.transparent)
        
    @property
    def active_thickness(self):
        txt = self.toolbar.combo_thickness.currentText()
        try:
            return int(txt.split()[0])
        except Exception:
            return 5
            
    @property
    def active_style(self):
        return self.toolbar.combo_style.currentText().lower()
        
    def load_base_image(self, file_path, item_pos, item_width, item_height):
        base_pix = QPixmap(file_path)
        if base_pix.isNull():
            return
            
        self.canvas_image = QImage(self.canvas_rect.size().toSize(), QImage.Format_ARGB32_Premultiplied)
        self.canvas_image.fill(Qt.transparent)
        
        painter = QPainter(self.canvas_image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        local_pos = item_pos - self.canvas_rect.topLeft()
        painter.drawPixmap(
            QRectF(local_pos.x(), local_pos.y(), item_width, item_height),
            base_pix,
            QRectF(0, 0, base_pix.width(), base_pix.height())
        )
        painter.end()
        self.base_image = self.canvas_image.copy()
        self.update()
        
    def boundingRect(self):
        return self.canvas_rect
        
    def paint(self, painter, option, widget):
        if not self.canvas_image:
            self.canvas_image = self.render_canvas()
        painter.drawImage(self.canvas_rect, self.canvas_image)
        
    def render_canvas(self):
        image = QImage(self.canvas_rect.size().toSize(), QImage.Format_ARGB32_Premultiplied)
        if self.base_image:
            image = self.base_image.copy()
        else:
            image.fill(Qt.transparent)
            
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        
        for stroke in self.strokes:
            self.draw_stroke(painter, stroke)
            
        if self.current_stroke:
            self.draw_stroke(painter, self.current_stroke)
            
        painter.end()
        return image
        
    def draw_stroke(self, painter, stroke):
        tool = stroke["tool"]
        style = stroke["style"]
        color = stroke["color"]
        thickness = stroke["thickness"]
        points = stroke["points"]
        
        if not points:
            return
            
        painter.save()
        
        pen = QPen(color, thickness, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if tool == "eraser":
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen.setWidth(thickness * 3)
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            if style == "dashed":
                pen.setStyle(Qt.DashLine)
                
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        if tool == "eraser":
            path = QPainterPath()
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            painter.drawPath(path)
        elif tool == "circle":
            if len(points) >= 2:
                p1 = points[0]
                p2 = points[1]
                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()
                radius = (dx*dx + dy*dy)**0.5
                painter.drawEllipse(p1, radius, radius)
        elif tool == "rectangle":
            if len(points) >= 2:
                p1 = points[0]
                p2 = points[1]
                rect = QRectF(p1, p2).normalized()
                painter.drawRect(rect)
        elif tool == "arrow" or style == "arrow":
            if len(points) >= 2:
                p1 = points[0]
                p2 = points[-1]
                draw_arrow(painter, p1, p2, thickness, color)
        else:
            path = QPainterPath()
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            painter.drawPath(path)
                
        painter.restore()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.thumb_area.exit_draw_mode(save=True)
            event.accept()
            return
            
        if event.button() == Qt.LeftButton:
            canvas_p = event.pos() - self.canvas_rect.topLeft()
            self.current_stroke = {
                "tool": self.active_tool,
                "style": self.active_style,
                "color": self.active_color,
                "thickness": self.active_thickness,
                "points": [canvas_p]
            }
            self.canvas_image = None
            self.update()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if self.current_stroke:
            canvas_p = event.pos() - self.canvas_rect.topLeft()
            if self.current_stroke["tool"] in ("circle", "rectangle", "arrow"):
                p1 = self.current_stroke["points"][0]
                self.current_stroke["points"] = [p1, canvas_p]
            else:
                self.current_stroke["points"].append(canvas_p)
            self.canvas_image = None
            self.update()
            event.accept()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.current_stroke:
            canvas_p = event.pos() - self.canvas_rect.topLeft()
            if self.current_stroke["tool"] in ("circle", "rectangle", "arrow"):
                p1 = self.current_stroke["points"][0]
                self.current_stroke["points"] = [p1, canvas_p]
            else:
                self.current_stroke["points"].append(canvas_p)
            self.strokes.append(self.current_stroke)
            self.current_stroke = None
            self.canvas_image = None
            self.update()
            event.accept()


class DrawItem(QGraphicsObject):
    moving_started = Signal()
    moving_finished = Signal()
    
    def __init__(self, pos, file_path, width=200, height=200):
        super().__init__()
        self.setPos(pos)
        self.file_path = file_path
        self.width = width
        self.height = height
        self.uuid = str(uuid.uuid4())
        self.is_custom_size = False
        
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(6000)
        self.setCacheMode(QGraphicsItem.NoCache)
        
        self.pixmap = QPixmap(self.file_path)
        self._resizing = False
        self._resize_mode = None
        self._resize_start_pos = None
        self._resize_start_size = None
        
        self.setAcceptHoverEvents(True)
        
    def boundingRect(self):
        margin = 15
        return QRectF(-margin, -margin, self.width + margin*2, self.height + margin*2)
        
    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self.pixmap.isNull():
            painter.drawPixmap(
                QRectF(0, 0, self.width, self.height), 
                self.pixmap, 
                QRectF(0, 0, self.pixmap.width(), self.pixmap.height())
            )
            
        if self.isSelected():
            pen_w = 2
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#00bcd4"), pen_w, Qt.DashLine))
            painter.drawRect(0, 0, self.width, self.height)
            
            painter.setBrush(QColor("#00bcd4"))
            painter.setPen(QPen(Qt.white, 1))
            painter.drawEllipse(self.width - 8, self.height - 8, 10, 10)
            painter.drawRoundedRect(self.width - 5, self.height // 2 - 10, 5, 20, 2, 2)
            painter.drawRoundedRect(self.width // 2 - 10, self.height - 5, 20, 5, 2, 2)
        painter.restore()
        
    def mousePressEvent(self, event):
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
        try:
            super().mousePressEvent(event)
        except TypeError:
            pass
            
    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            
            new_w = self.width
            new_h = self.height
            if self._resize_mode in ["bottom_right", "right"]:
                new_w = max(20, self._resize_start_size[0] + delta.x())
            if self._resize_mode in ["bottom_right", "bottom"]:
                new_h = max(20, self._resize_start_size[1] + delta.y())
                
            if new_w != self.width or new_h != self.height:
                self.prepareGeometryChange()
                self.width = new_w
                self.height = new_h
                self.is_custom_size = True
                self.update()
            event.accept()
        else:
            try:
                super().mouseMoveEvent(event)
            except TypeError:
                pass
            
    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_mode = None
        if event.button() == Qt.LeftButton:
            self.moving_finished.emit()
        try:
            super().mouseReleaseEvent(event)
        except TypeError:
            pass
        
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemParentChange:
            if isinstance(value, BackdropItem):
                return None
        return super().itemChange(change, value)
