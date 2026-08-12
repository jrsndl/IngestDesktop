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
        
        self.text_item = NoteTextItem(self)
        self.text_item.setDefaultTextColor(QColor("#e0e0e0"))
        # Default font: 3x the original 24pt = 72pt
        font = QFont("Arial", 72)
        self.text_item.setFont(font)
        self.text_item.setPlainText(text)
        self.text_item.setPos(10, 10)
        
        self.width = 400
        self.height = 200
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
        
    def _on_text_changed(self):
        # Auto-expand if text overflows
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
        
        # 2. Draw border on top of background using a path for precision
        painter.setBrush(Qt.NoBrush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#00bcd4"), pen_w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        else:
            painter.setPen(QPen(QColor("#444444"), pen_w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
            
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
            # Finalise text wrapping now that the drag is done
            self.text_item.setTextWidth(self.width - 20)
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

class ColorButton(QPushButton):
    colorChanged = Signal(QColor)

    def __init__(self, color=Qt.white, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(60, 25)
        self.clicked.connect(self.choose_color)
        self.update_style()

    def choose_color(self):
        color = QColorDialog.getColor(self._color, self)
        if color.isValid():
            self.set_color(color)

    def set_color(self, color):
        self._color = QColor(color)
        self.update_style()
        self.colorChanged.emit(self._color)

    def color(self):
        return self._color

    def update_style(self):
        self.setStyleSheet(f"background-color: {self._color.name()}; border: 1px solid #555; border-radius: 3px;")

class BackdropDialog(QDialog):
    applyRequested = Signal(dict)

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Backdrop Settings")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Label (Top control)
        self.label_edit = QLineEdit()
        
        # Label Styling
        self.label_size = QSpinBox()
        self.label_size.setRange(8, 2000)
        self.label_size.setValue(200)
        
        self.label_color_btn = ColorButton(QColor("white"))
        
        style_layout = QHBoxLayout()
        self.chk_bold = QCheckBox("Bold")
        self.chk_italic = QCheckBox("Italic")
        self.chk_strike = QCheckBox("Strike")
        self.chk_underline = QCheckBox("Underline")
        style_layout.addWidget(self.chk_bold)
        style_layout.addWidget(self.chk_italic)
        style_layout.addWidget(self.chk_strike)
        style_layout.addWidget(self.chk_underline)
        style_layout.addStretch()

        self.alignment_combo = QComboBox()
        self.alignment_combo.addItems([
            "Top Left", "Top Center", "Top Right", 
            "Middle Left", "Middle Center", "Middle Right", 
            "Bottom Left", "Bottom Center", "Bottom Right"
        ])

        # Name / Appearance
        self.name_edit = QLineEdit()
        
        self.appearance_group = QButtonGroup(self)
        self.radio_border = QRadioButton("Border")
        self.radio_fill = QRadioButton("Fill")
        self.appearance_group.addButton(self.radio_border)
        self.appearance_group.addButton(self.radio_fill)
        
        appearance_layout = QHBoxLayout()
        appearance_layout.addWidget(self.radio_border)
        appearance_layout.addWidget(self.radio_fill)
        appearance_layout.addStretch()
        
        self.border_color_btn = ColorButton(QColor("magenta"))
        self.fill_color_btn = ColorButton(QColor(40, 40, 40))
        
        form.addRow("Label Text:", self.label_edit)
        form.addRow("Label Size:", self.label_size)
        form.addRow("Label Color:", self.label_color_btn)
        form.addRow("Label Style:", style_layout)
        form.addRow("Label Alignment:", self.alignment_combo)
        
        form.addRow(QLabel("")) # Spacer
        
        form.addRow("Name (Title):", self.name_edit)
        form.addRow("Appearance:", appearance_layout)
        form.addRow("Border Color:", self.border_color_btn)
        form.addRow("Fill Color:", self.fill_color_btn)
        
        layout.addLayout(form)
        
        # Default values
        self.radio_border.setChecked(True)
        self.label_color_btn.set_color(QColor("white"))
        
        if data:
            self.label_edit.setText(data.get("label", ""))
            self.label_size.setValue(data.get("label_size", 48))
            self.label_color_btn.set_color(QColor(data.get("label_color", "white")))
            self.chk_bold.setChecked(data.get("label_bold", True))
            self.chk_italic.setChecked(data.get("label_italic", False))
            self.chk_strike.setChecked(data.get("label_strike", False))
            self.chk_underline.setChecked(data.get("label_underline", False))
            self.alignment_combo.setCurrentText(data.get("label_alignment", "Top Left"))
            
            self.name_edit.setText(data.get("name", ""))
            if data.get("appearance") == "Fill":
                self.radio_fill.setChecked(True)
            else:
                self.radio_border.setChecked(True)
            self.border_color_btn.set_color(QColor(data.get("border_color", "magenta")))
            self.fill_color_btn.set_color(QColor(data.get("fill_color", "#282828")))
            
        btns = QHBoxLayout()
        self.btn_done = QPushButton("Done")
        self.btn_done.setObjectName("IngestButton")
        self.btn_done.setMinimumHeight(40)
        self.btn_done.clicked.connect(self.accept)
        
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setMinimumHeight(40)
        self.btn_apply.clicked.connect(self.on_apply_clicked)
        
        btns.addWidget(self.btn_done)
        btns.addWidget(self.btn_apply)
        layout.addLayout(btns)

        # Enter key behavior
        self.label_edit.returnPressed.connect(self.accept)
        
        # Focus
        self.label_edit.setFocus()

    def on_apply_clicked(self):
        self.applyRequested.emit(self.get_values())

    def get_values(self):
        return {
            "name": self.name_edit.text().strip(),
            "label": self.label_edit.text().strip(),
            "label_size": self.label_size.value(),
            "label_color": self.label_color_btn.color().name(),
            "label_bold": self.chk_bold.isChecked(),
            "label_italic": self.chk_italic.isChecked(),
            "label_strike": self.chk_strike.isChecked(),
            "label_underline": self.chk_underline.isChecked(),
            "label_alignment": self.alignment_combo.currentText(),
            "appearance": "Fill" if self.radio_fill.isChecked() else "Border",
            "border_color": self.border_color_btn.color().name(),
            "fill_color": self.fill_color_btn.color().name()
        }

class NoteToolbar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoteToolbar")
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setStyleSheet("""
            #NoteToolbar {
                background-color: #1e1e1e;
                border: 1px solid #444444;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
                font-size: 16px;
                padding: 4px 5px;
                min-width: 25px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton#CloseBtn:hover {
                background-color: #c62828;
            }
            QLabel {
                color: #666666;
                padding: 0 1px;
            }
            QLabel#Handle {
                color: #888888;
                font-size: 18px;
                padding-right: 2px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        
        self.handle = QLabel("⠿")
        self.handle.setObjectName("Handle")
        self.handle.setCursor(Qt.SizeAllCursor)
        
        self.btn_bold = QPushButton("B")
        self.btn_bold.setFocusPolicy(Qt.NoFocus)
        self.btn_bold.setStyleSheet("font-weight: bold; font-size: 18px;")
        self.btn_italic = QPushButton("I")
        self.btn_italic.setFocusPolicy(Qt.NoFocus)
        self.btn_italic.setStyleSheet("font-style: italic; font-size: 18px;")
        self.btn_underline = QPushButton("U")
        self.btn_underline.setFocusPolicy(Qt.NoFocus)
        self.btn_underline.setStyleSheet("text-decoration: underline; font-size: 18px;")
        self.btn_strike = QPushButton("S")
        self.btn_strike.setFocusPolicy(Qt.NoFocus)
        self.btn_strike.setStyleSheet("text-decoration: line-through; font-size: 18px;")
        
        sep1 = QLabel("|")
        
        self.btn_color = QPushButton("A")
        self.btn_color.setFocusPolicy(Qt.NoFocus)
        self.btn_color.setStyleSheet("border-bottom: 3px solid #00bcd4; font-weight: bold; font-size: 18px;")
        
        self.btn_bg_color = QPushButton("⬛")
        self.btn_bg_color.setFocusPolicy(Qt.NoFocus)
        self.btn_bg_color.setStyleSheet("font-size: 14px;")
        
        self.spin_size = QSpinBox()
        self.spin_size.setRange(8, 5000)
        self.spin_size.setValue(24)
        self.spin_size.setFixedWidth(65)
        self.spin_size.setStyleSheet("background: #2b2b2b; color: white; border: 1px solid #444444; font-size: 14px;")
        
        sep2 = QLabel("|")
        
        self.btn_delete = QPushButton("🗑")
        self.btn_delete.setFocusPolicy(Qt.NoFocus)
        self.btn_delete.setObjectName("CloseBtn")
        self.btn_delete.setStyleSheet("font-size: 18px;")
        
        layout.addWidget(self.handle)
        layout.addWidget(self.btn_bold)
        layout.addWidget(self.btn_italic)
        layout.addWidget(self.btn_underline)
        layout.addWidget(self.btn_strike)
        layout.addWidget(sep1)
        layout.addWidget(self.btn_color)
        layout.addWidget(self.btn_bg_color)
        layout.addWidget(self.spin_size)
        layout.addWidget(sep2)
        layout.addStretch()
        layout.addWidget(self.btn_delete)
        
        self.current_items = []
        self._drag_pos = None
        
        self.btn_bold.clicked.connect(lambda: self.apply_format("bold"))
        self.btn_italic.clicked.connect(lambda: self.apply_format("italic"))
        self.btn_underline.clicked.connect(lambda: self.apply_format("underline"))
        self.btn_strike.clicked.connect(lambda: self.apply_format("strikeout"))
        self.btn_color.clicked.connect(self.pick_color)
        self.btn_bg_color.clicked.connect(self.pick_bg_color)
        self.spin_size.valueChanged.connect(self.change_font_size)

    def pick_bg_color(self):
        if not self.current_items: return
        from PySide6.QtWidgets import QColorDialog
        # Use first item's color as initial
        color = QColorDialog.getColor(self.current_items[0].bg_color, self, "Select Note Background Color")
        if color.isValid():
            if color.alpha() == 255:
                color.setAlpha(230)
            for item in self.current_items:
                item.bg_color = color
                item.update()
            self.btn_bg_color.setStyleSheet(f"color: {color.name()}; font-size: 14px;")

    def change_font_size(self, size):
        if not self.current_items: return
        for item in self.current_items:
            cursor = item.text_item.textCursor()
            if not cursor.hasSelection():
                    cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(size)
            cursor.mergeCharFormat(fmt)
            item.text_item.setTextCursor(cursor)
            # Re-check dimensions after size change
            item._on_text_changed()

    def pick_color(self):
        if not self.current_items: return
        from PySide6.QtWidgets import QColorDialog
        # Use first item's current color as initial
        initial_color = self.current_items[0].text_item.defaultTextColor()
        color = QColorDialog.getColor(initial_color, self, "Select Text Color")
        if color.isValid():
            for item in self.current_items:
                # Set default for new text
                item.text_item.setDefaultTextColor(color)
                # Apply to selection or whole document
                cursor = item.text_item.textCursor()
                if not cursor.hasSelection():
                        cursor.select(QTextCursor.SelectionType.Document)
                fmt = QTextCharFormat()
                fmt.setForeground(color)
                cursor.mergeCharFormat(fmt)
                item.text_item.setTextCursor(cursor)
                
            self.btn_color.setStyleSheet(f"border-bottom: 3px solid {color.name()}; font-weight: bold;")

    def apply_format(self, fmt_type):
        if not self.current_items: return
        
        for item in self.current_items:
            cursor = item.text_item.textCursor()
            if not cursor.hasSelection():
                    cursor.select(QTextCursor.SelectionType.Document)
                
            fmt = QTextCharFormat()
            if fmt_type == "bold":
                is_bold = cursor.charFormat().fontWeight() == QFont.Bold
                fmt.setFontWeight(QFont.Normal if is_bold else QFont.Bold)
            elif fmt_type == "italic":
                fmt.setFontItalic(not cursor.charFormat().fontItalic())
            elif fmt_type == "underline":
                fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
            elif fmt_type == "strikeout":
                fmt.setFontStrikeOut(not cursor.charFormat().fontStrikeOut())
                
            cursor.mergeCharFormat(fmt)
            item.text_item.setTextCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()
            
    def mouseMoveEvent(self, event):
        if self._drag_pos:
            delta = event.globalPos() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPos()
            
    def mouseReleaseEvent(self, event):
        self._drag_pos = None

import math
from PySide6.QtGui import QPolygonF, QBitmap, QRegion
from PySide6.QtCore import QPoint

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

class DrawToolbar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumb_area = parent
        self.setObjectName("DrawToolbar")
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setStyleSheet("""
            #DrawToolbar {
                background-color: #1e1e1e;
                border: 1px solid #444444;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
                font-size: 16px;
                padding: 4px 6px;
                min-width: 25px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:checked {
                background-color: #555555;
                color: white;
            }
            QPushButton#CloseBtn:hover {
                background-color: #c62828;
            }
            QPushButton#RectBtn {
                font-size: 19px;
            }
            QLabel {
                color: #666666;
                padding: 0 1px;
            }
            QLabel#Handle {
                color: #888888;
                font-size: 18px;
                padding-right: 2px;
            }
            QComboBox {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 2px 4px;
                font-size: 13px;
                min-width: 60px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        self.handle = QLabel("⠿")
        self.handle.setObjectName("Handle")
        self.handle.setCursor(Qt.SizeAllCursor)
        
        self.btn_brush = QPushButton("✎")
        self.btn_brush.setCheckable(True)
        self.btn_brush.setChecked(True)
        self.btn_brush.setFocusPolicy(Qt.NoFocus)
        self.btn_brush.setToolTip("Brush (B)")
        
        self.btn_eraser = QPushButton("▱")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.setFocusPolicy(Qt.NoFocus)
        self.btn_eraser.setToolTip("Eraser (E)")
        
        self.btn_circle = QPushButton("◯")
        self.btn_circle.setCheckable(True)
        self.btn_circle.setFocusPolicy(Qt.NoFocus)
        self.btn_circle.setToolTip("Circle")
        
        self.btn_arrow = QPushButton("↗")
        self.btn_arrow.setCheckable(True)
        self.btn_arrow.setFocusPolicy(Qt.NoFocus)
        self.btn_arrow.setToolTip("Arrow (A)")
        
        self.btn_rect = QPushButton("▭")
        self.btn_rect.setObjectName("RectBtn")
        self.btn_rect.setCheckable(True)
        self.btn_rect.setFocusPolicy(Qt.NoFocus)
        self.btn_rect.setToolTip("Rectangle")
        
        self.btn_brush.clicked.connect(self._on_brush_clicked)
        self.btn_eraser.clicked.connect(self._on_eraser_clicked)
        self.btn_circle.clicked.connect(self._on_circle_clicked)
        self.btn_arrow.clicked.connect(self._on_arrow_clicked)
        self.btn_rect.clicked.connect(self._on_rect_clicked)
        
        sep1 = QLabel("|")
        
        self.btn_color = QPushButton("")
        self.btn_color.setObjectName("ColorBtn")
        self.btn_color.setFocusPolicy(Qt.NoFocus)
        self.btn_color.setToolTip("Brush Color (C)")
        self.btn_color.clicked.connect(self._on_pick_color)
        
        cfg = self.thumb_area.get_config() if self.thumb_area else {}
        default_color_hex = cfg.get("draw_default_color", "#ff0000")
        default_thickness = cfg.get("draw_default_thickness", "5 px")
        default_style = cfg.get("draw_default_style", "Normal")
        
        default_color = QColor(default_color_hex)
        if not default_color.isValid():
            default_color = QColor(255, 0, 0)
        self.update_color_button(default_color)
        
        self.combo_thickness = QComboBox()
        self.combo_thickness.addItems(["2 px", "5 px", "10 px", "20 px"])
        self.combo_thickness.setCurrentText(default_thickness)
        self.combo_thickness.setFocusPolicy(Qt.NoFocus)
        self.combo_thickness.setToolTip("Brush Thickness ([ / ])")
        
        self.combo_style = QComboBox()
        self.combo_style.addItems(["Normal", "Dashed"])
        self.combo_style.setCurrentText(default_style)
        self.combo_style.setFocusPolicy(Qt.NoFocus)
        self.combo_style.setToolTip("Stroke Style")
        
        self.combo_thickness.currentTextChanged.connect(self._on_thickness_changed)
        self.combo_style.currentTextChanged.connect(self._on_style_changed)
        
        sep2 = QLabel("|")
        
        self.btn_delete = QPushButton("✕")
        self.btn_delete.setFocusPolicy(Qt.NoFocus)
        self.btn_delete.setToolTip("Delete Drawing (Delete)")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        
        self.btn_close = QPushButton("✓")
        self.btn_close.setFocusPolicy(Qt.NoFocus)
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setToolTip("Done (Esc / Right Click)")
        self.btn_close.clicked.connect(self._on_close_clicked)
        
        layout.addWidget(self.handle)
        layout.addWidget(self.btn_brush)
        layout.addWidget(self.btn_eraser)
        layout.addWidget(self.btn_circle)
        layout.addWidget(self.btn_arrow)
        layout.addWidget(self.btn_rect)
        layout.addWidget(sep1)
        layout.addWidget(self.btn_color)
        layout.addWidget(self.combo_thickness)
        layout.addWidget(self.combo_style)
        layout.addWidget(sep2)
        layout.addWidget(self.btn_delete)
        layout.addWidget(self.btn_close)
        
        self._drag_pos = None
        
    def update_color_button(self, color):
        self.btn_color.setStyleSheet(f"""
            QPushButton#ColorBtn {{
                background-color: {color.name()};
                border: 1px solid #555555;
                border-radius: 3px;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
                padding: 0px;
            }}
            QPushButton#ColorBtn:hover {{
                border-color: #888888;
            }}
        """)
        
    def _on_brush_clicked(self):
        self.btn_brush.setChecked(True)
        self.btn_eraser.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_arrow.setChecked(False)
        self.btn_rect.setChecked(False)
        if self.thumb_area and self.thumb_area._canvas_item:
            self.thumb_area._canvas_item.active_tool = "brush"
            
    def _on_eraser_clicked(self):
        self.btn_eraser.setChecked(True)
        self.btn_brush.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_arrow.setChecked(False)
        self.btn_rect.setChecked(False)
        if self.thumb_area and self.thumb_area._canvas_item:
            self.thumb_area._canvas_item.active_tool = "eraser"

    def _on_circle_clicked(self):
        self.btn_circle.setChecked(True)
        self.btn_brush.setChecked(False)
        self.btn_eraser.setChecked(False)
        self.btn_arrow.setChecked(False)
        self.btn_rect.setChecked(False)
        if self.thumb_area and self.thumb_area._canvas_item:
            self.thumb_area._canvas_item.active_tool = "circle"

    def _on_arrow_clicked(self):
        self.btn_arrow.setChecked(True)
        self.btn_brush.setChecked(False)
        self.btn_eraser.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_rect.setChecked(False)
        if self.thumb_area and self.thumb_area._canvas_item:
            self.thumb_area._canvas_item.active_tool = "arrow"

    def _on_rect_clicked(self):
        self.btn_rect.setChecked(True)
        self.btn_brush.setChecked(False)
        self.btn_eraser.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_arrow.setChecked(False)
        if self.thumb_area and self.thumb_area._canvas_item:
            self.thumb_area._canvas_item.active_tool = "rectangle"
            
    def _on_pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(self.thumb_area._canvas_item.active_color, self, "Select Brush Color")
        if color.isValid():
            self.thumb_area._canvas_item.active_color = color
            self.update_color_button(color)
            if self.thumb_area:
                cfg = self.thumb_area.get_config()
                cfg["draw_default_color"] = color.name()
                self.thumb_area.save_config_if_possible()

    def _on_thickness_changed(self, text):
        if self.thumb_area:
            cfg = self.thumb_area.get_config()
            cfg["draw_default_thickness"] = text
            self.thumb_area.save_config_if_possible()

    def _on_style_changed(self, text):
        if self.thumb_area:
            cfg = self.thumb_area.get_config()
            cfg["draw_default_style"] = text
            self.thumb_area.save_config_if_possible()
            
    def _on_delete_clicked(self):
        if self.thumb_area:
            self.thumb_area.clear_canvas_drawings()
            
    def _on_close_clicked(self):
        if self.thumb_area:
            self.thumb_area.exit_draw_mode(save=True)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()
            
    def mouseMoveEvent(self, event):
        if self._drag_pos:
            delta = event.globalPos() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPos()
            
    def mouseReleaseEvent(self, event):
        self._drag_pos = None

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

from utils import generate_thumbnail_image

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

        # 3. Draw Borders (always)
        base_w = 2
        if lod < 0.3:
            base_w = 6
        elif lod < 0.6:
            base_w = 4
            
        if getattr(self.data, "is_ayon_item", False):
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
                pen = QPen(QColor("#ffffff"), sel_width)
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
        
        # 4. Label - Only if zoomed in and NOT editing
        if lod > 0.05 and not self.is_editing and getattr(self.scene(), "show_labels", True):
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

        # 5. Draw resize handle grip in bottom-right corner
        if lod > 0.4:
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
            
            painter.drawLine(QPointF(r - 12, b - 4), QPointF(r - 4, b - 12))
            painter.drawLine(QPointF(r - 8, b - 4), QPointF(r - 4, b - 8))
            painter.drawLine(QPointF(r - 4, b - 4), QPointF(r - 4, b - 4))
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

    def _is_in_resize_handle(self, local_pos):
        img_rect = self.get_image_rect()
        border_rect = img_rect.adjusted(-4, -4, 4, 4)
        handle_size = 15
        in_x = border_rect.right() - handle_size <= local_pos.x() <= border_rect.right() + 4
        in_y = border_rect.bottom() - handle_size <= local_pos.y() <= border_rect.bottom() + 4
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
            new_size = max(50, min(1500, self._drag_start_size + delta.x()))
            
            self.prepareGeometryChange()
            self.size = new_size
            self.data.size = new_size
            self.cached_label = ""
            self.update()
            
            for it, start_size in getattr(self, "_selected_resizers", []):
                it.prepareGeometryChange()
                it_new_size = max(50, min(1500, start_size + delta.x()))
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

class SequenceRenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Rename")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.prefix = QLineEdit("img")
        
        self.chk_add_counter = QCheckBox("Add Counter")
        self.chk_add_counter.setChecked(True)
        self.chk_add_counter.toggled.connect(self._on_toggle_counter)
        
        self.counter_start = QSpinBox()
        self.counter_start.setRange(0, 999999)
        self.counter_start.setValue(1)
        
        self.counter_zeroes = QSpinBox()
        self.counter_zeroes.setRange(1, 10)
        self.counter_zeroes.setValue(3)
        
        self.suffix = QLineEdit("")
        
        form.addRow("Prefix:", self.prefix)
        form.addRow("", self.chk_add_counter)
        form.addRow("Counter Start:", self.counter_start)
        form.addRow("Counter Zeroes:", self.counter_zeroes)
        form.addRow("Suffix:", self.suffix)
        
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Rename")
        self.btn_ok.setObjectName("IngestButton")
        self.btn_ok.setMinimumHeight(40)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)
        
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

    def _on_toggle_counter(self, checked):
        self.counter_start.setEnabled(checked)
        self.counter_zeroes.setEnabled(checked)

    def get_values(self):
        return {
            "prefix": self.prefix.text().strip(),
            "start": self.counter_start.value(),
            "zeroes": self.counter_zeroes.value(),
            "suffix": self.suffix.text().strip(),
            "add_counter": self.chk_add_counter.isChecked()
        }

class ArrangeDialog(QDialog):
    valuesChanged = Signal(dict)

    def __init__(self, mode="grid", initial_values=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("Arrange" if mode == "grid" else f"Arrange {mode.capitalize()}")
        self.setMinimumWidth(300)
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout(self)
        
        init_cols = initial_values.get("cols", 10) if initial_values else 10
        init_gap_h = initial_values.get("gap_h", 50) if initial_values else 50
        init_gap_v = initial_values.get("gap_v", 50) if initial_values else 50
        init_thumb_size = initial_values.get("thumb_size", 150) if initial_values else 150
        init_sort = initial_values.get("sort_by", "File Name") if initial_values else "File Name"
        init_reverse = initial_values.get("reverse", False) if initial_values else False
        init_group_cols = initial_values.get("group_cols", False) if initial_values else False

        # Sort Row
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort By:"))
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["File Name", "Label", "Version", "File Size", "Width", "Height", "Age", "File Type"])
        idx = self.combo_sort.findText(init_sort)
        if idx >= 0: self.combo_sort.setCurrentIndex(idx)
        self.combo_sort.currentIndexChanged.connect(self._emit_changed)
        sort_layout.addWidget(self.combo_sort)
        
        self.chk_reverse = QCheckBox("Reverse")
        self.chk_reverse.setChecked(init_reverse)
        self.chk_reverse.toggled.connect(self._emit_changed)
        sort_layout.addWidget(self.chk_reverse)
        layout.addLayout(sort_layout)
        
        layout.addSpacing(5)

        # Thumb Size
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Thumb Size:"))
        self.slider_thumb_size = QSlider(Qt.Horizontal)
        self.slider_thumb_size.setRange(20, 2048)
        self.slider_thumb_size.setValue(init_thumb_size)
        self.lbl_thumb_size = QLabel(str(init_thumb_size))
        self.slider_thumb_size.valueChanged.connect(lambda v: self.lbl_thumb_size.setText(str(v)))
        self.slider_thumb_size.valueChanged.connect(self._emit_changed)
        size_layout.addWidget(self.slider_thumb_size)
        size_layout.addWidget(self.lbl_thumb_size)
        layout.addLayout(size_layout)

        # Columns (only for grid)
        self.slider_cols = None
        if mode == "grid":
            col_layout = QHBoxLayout()
            col_layout.addWidget(QLabel("Columns:"))
            self.slider_cols = QSlider(Qt.Horizontal)
            self.slider_cols.setRange(1, 50)
            self.slider_cols.setValue(init_cols)
            self.lbl_cols = QLabel(str(init_cols))
            self.slider_cols.valueChanged.connect(lambda v: self.lbl_cols.setText(str(v)))
            self.slider_cols.valueChanged.connect(self._emit_changed)
            col_layout.addWidget(self.slider_cols)
            col_layout.addWidget(self.lbl_cols)
            
            self.chk_group_cols = QCheckBox("Group to Columns")
            self.chk_group_cols.setChecked(init_group_cols)
            self.chk_group_cols.toggled.connect(self._emit_changed)
            col_layout.addWidget(self.chk_group_cols)
            
            layout.addLayout(col_layout)
            
        # Gap (Horizontal) - only for horizontal or grid
        self.slider_gap_h = None
        if mode in ["horizontal", "grid"]:
            gap_h_layout = QHBoxLayout()
            gap_h_label = "Gap:" if mode != "grid" else "Horizontal Gap:"
            gap_h_layout.addWidget(QLabel(gap_h_label))
            self.slider_gap_h = QSlider(Qt.Horizontal)
            self.slider_gap_h.setRange(0, 10000)
            self.slider_gap_h.setValue(init_gap_h)
            self.lbl_gap_h = QLabel(str(init_gap_h))
            self.slider_gap_h.valueChanged.connect(lambda v: self.lbl_gap_h.setText(str(v)))
            self.slider_gap_h.valueChanged.connect(self._emit_changed)
            gap_h_layout.addWidget(self.slider_gap_h)
            gap_h_layout.addWidget(self.lbl_gap_h)
            layout.addLayout(gap_h_layout)
        
        # Gap (Vertical) - only for vertical or grid
        self.slider_gap_v = None
        if mode in ["vertical", "grid"]:
            gap_v_layout = QHBoxLayout()
            gap_v_label = "Gap:" if mode == "vertical" else "Vertical Gap:"
            gap_v_layout.addWidget(QLabel(gap_v_label))
            self.slider_gap_v = QSlider(Qt.Horizontal)
            self.slider_gap_v.setRange(0, 1000)
            self.slider_gap_v.setValue(init_gap_v)
            self.lbl_gap_v = QLabel(str(init_gap_v))
            self.slider_gap_v.valueChanged.connect(lambda v: self.lbl_gap_v.setText(str(v)))
            self.slider_gap_v.valueChanged.connect(self._emit_changed)
            gap_v_layout.addWidget(self.slider_gap_v)
            gap_v_layout.addWidget(self.lbl_gap_v)
            layout.addLayout(gap_v_layout)
            
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Apply")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

    def _emit_changed(self, _=None):
        self.valuesChanged.emit(self.get_values())

    def get_values(self):
        vals = {
            "thumb_size": self.slider_thumb_size.value() if hasattr(self, "slider_thumb_size") and self.slider_thumb_size else 150,
            "gap_h": self.slider_gap_h.value() if self.slider_gap_h else 0,
            "gap_v": self.slider_gap_v.value() if self.slider_gap_v else 0,
            "cols": self.slider_cols.value() if self.slider_cols else 1,
            "sort_by": self.combo_sort.currentText(),
            "reverse": self.chk_reverse.isChecked(),
            "group_cols": self.chk_group_cols.isChecked() if hasattr(self, "chk_group_cols") else False
        }
        return vals

class ThumbnailArea(QWidget):
    tag_toggle_requested = Signal()
    label_action_requested = Signal(str, object)
    maximize_toggle_requested = Signal()
    paste_requested = Signal()
    queue_requested = Signal()
    scene_items_changed = Signal()
    change_version_requested = Signal(object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State Initialization
        config = {}
        if parent and hasattr(parent, "config") and parent.config:
            config = parent.config
        
        default_cols = config.get("default_columns", 12)
        default_text_size = config.get("default_text_size", 10)
        default_thumb_size = config.get("default_thumb_size", 150)
        
        default_gap_h = int(default_thumb_size * 0.20)
        default_gap_v = int(default_thumb_size * 0.20)

        self.item_to_thumb = {}
        self._last_arrange_vals = {
            "cols": default_cols, "gap_h": default_gap_h, "gap_v": default_gap_v,
            "sort_by": "File Name", "reverse": False
        }
        self._arrange_dialog = None
        self.model = None
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)
        self._has_selection = False
        self._path_filter = ""
        self._last_age_filter = (False, 0)
        self._last_search_text = ""
        self._last_ignore_text = ""
        self.tooltip_templates = {}
        self._deferred_scene_items_change = False
        self._marked_placement_pos = None
        self.item_positions = {}
        
        self.player_mode = "stop" # "stop", "selected", "all"
        self.show_reviews = True
        self.active_players = {} # mapping: ThumbnailItem -> VideoPlayerOverlay
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Controls Bar
        self.controls = QWidget()
        self.controls.setObjectName("ThumbnailControls")
        self.controls_layout = QHBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(5, 5, 5, 5)
        
        self.btn_frame_all = QPushButton("Frame All")
        self.btn_frame_all.clicked.connect(self.frame_all)
        
        self.btn_frame_sel = QPushButton("Frame Selection")
        self.btn_frame_sel.clicked.connect(self.frame_selection)
        
        

        self.slider_text_size = QSlider(Qt.Horizontal)
        self.slider_text_size.setRange(4, 64)
        self.slider_text_size.setValue(default_text_size)
        self.slider_text_size.setFixedWidth(100)
        self.slider_text_size.valueChanged.connect(self.update_font_size)
        self.slider_thumb_size = QSlider(Qt.Horizontal)
        self.slider_thumb_size.setRange(20, 2048)
        self.slider_thumb_size.setValue(default_thumb_size)
        self.slider_thumb_size.setFixedWidth(100)
        self.slider_thumb_size.valueChanged.connect(self.update_thumb_size)

        self.btn_tag_filter = QPushButton("Filter: All")
        self.btn_tag_filter.clicked.connect(self._cycle_tag_filter)
        self._tag_filter_state = "all" # all, enabled, disabled

        self.btn_paste = QPushButton("Paste Image")
        self.btn_paste.clicked.connect(self.paste_requested.emit)

        self.btn_maximize = QPushButton("Maximize")
        self.btn_maximize.setCheckable(True)
        self.btn_maximize.clicked.connect(self.maximize_toggle_requested.emit)

        self.btn_queue = QPushButton("Conversion Queue: waiting to start")
        self.btn_queue.clicked.connect(self.queue_requested.emit)

        def add_v_line(layout):
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("color: #444444; margin: 2px;")
            layout.addWidget(line)

        self.btn_show_text = QPushButton("Show Text")
        self.btn_show_text.setCheckable(True)
        self.btn_show_text.setChecked(True)
        self.btn_show_text.clicked.connect(self._on_show_text_toggled)

        self.controls_layout.addWidget(self.btn_frame_all)
        self.controls_layout.addWidget(self.btn_frame_sel)
        add_v_line(self.controls_layout)
        
        self.controls_layout.addWidget(self.btn_show_text)
        add_v_line(self.controls_layout)
        self.controls_layout.addWidget(QLabel("Text:"))
        self.controls_layout.addWidget(self.slider_text_size)
        self.controls_layout.addWidget(QLabel("Thumb:"))
        self.controls_layout.addWidget(self.slider_thumb_size)
        
        add_v_line(self.controls_layout)
        self.btn_player_mode = QPushButton("Player: Stop")
        self.btn_player_mode.clicked.connect(self._cycle_player_mode)
        self.controls_layout.addWidget(self.btn_player_mode)
        
        self.controls_layout.addStretch()
        self.controls_layout.addWidget(self.btn_paste)
        self.controls_layout.addWidget(self.btn_tag_filter)
        self.controls_layout.addWidget(self.btn_queue)
        self.controls_layout.addWidget(self.btn_maximize)
        
        self.layout.addWidget(self.controls)
        
        # Clipboard polling timer
        self._clip_timer = QTimer(self)
        self._clip_timer.timeout.connect(self._update_paste_button_state)
        self._clip_timer.start(1000)

        # Note Toolbar
        self.note_toolbar = NoteToolbar(self)
        self.note_toolbar.hide()
        self.note_toolbar.btn_delete.clicked.connect(self.delete_selected_notes)
        self._clip_timer.start(1000)

        # Draw Mode State
        self._draw_mode_active = False
        self._canvas_item = None
        self._edit_draw_item = None
        self.draw_toolbar = DrawToolbar(self)
        self.draw_toolbar.hide()

        # Graphics View
        self.view = QGraphicsView()
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        
        # Use OpenGL for performance only if inline video is disabled
        from gui.video_player import is_multimedia_available
        if not is_multimedia_available():
            self.gl_widget = QOpenGLWidget()
            self.view.setViewport(self.gl_widget)
        
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.scene.setSceneRect(-50000, -50000, 100000, 100000)
        self.view.setScene(self.scene)
        self.scene.show_labels = True
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.scene.changed.connect(lambda rects: self.update_video_overlay_geometry())
        self.view.setBackgroundBrush(QColor("#1e1e1e"))
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.NoAnchor)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self) # For key logic
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_fast_tooltip)
        self._last_tooltip_pos = None
        self._last_tooltip_local_pos = None
        
        self._is_panning = False
        self._last_pan_pos = None
        
        self.inline_editor = QLineEdit(self.view.viewport())
        self.inline_editor.setAlignment(Qt.AlignCenter)
        self.inline_editor.hide()
        
        # Instantiate overlay video player directly on top of viewport
        from gui.video_player import VideoPlayerOverlay
        self.video_player = VideoPlayerOverlay(self.view.viewport())
        self.video_player.hide()
        
        # Connect view scrollbars to update video overlay position on the fly
        self.view.horizontalScrollBar().valueChanged.connect(self.update_video_overlay_geometry)
        self.view.verticalScrollBar().valueChanged.connect(self.update_video_overlay_geometry)
        
        # Add character validation: A-Z, a-z, 0-9, -, _, ., space
        # regex = QRegularExpression("^[a-zA-Z0-9_\\-\\.\\s]*$")
        # validator = QRegularExpressionValidator(regex, self.inline_editor)
        # self.inline_editor.setValidator(validator)
        
        self.inline_editor.editingFinished.connect(self._on_inline_editing_finished)
        self.inline_editor.installEventFilter(self)
        self._editing_item = None

        self.lbl_zoom = QLabel("100%", self.view) # Parent to view, not viewport
        self.lbl_zoom.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_zoom.setFixedWidth(60)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.raise_()
        self.update_zoom_indicator()
        
        self.grabGesture(Qt.PinchGesture)
        self.view.viewport().grabGesture(Qt.PinchGesture)
        
        self.setFocusPolicy(Qt.StrongFocus)
        self.view.setFocusPolicy(Qt.StrongFocus)
        
        self.layout.addWidget(self.view)
        

    def set_tooltip_templates(self, templates):
        self.tooltip_templates = templates
        self.refresh_tooltips()

    def refresh_tooltips(self):
        if not self.model: return
        for item in self.item_to_thumb.values():
            item.update_tooltip(self.tooltip_templates, self.model)

    def _on_sequence_rename(self):
        selected_thumbs = self.scene.selectedItems()
        if not selected_thumbs:
            return
            
        dialog = SequenceRenameDialog(self)
        if dialog.exec():
            vals = dialog.get_values()
            
            # Sort thumbs: Top-to-Bottom, then Left-to-Right
            def sort_key(thumb):
                # Using a rounded Y to group items in the same row
                # Line height is roughly font_size * 1.5 + size
                row_h = self.slider_thumb_size.value() + 50 
                return (round(thumb.y() / row_h), thumb.x())
            
            sorted_thumbs = sorted(selected_thumbs, key=sort_key)
            
            prefix = vals["prefix"]
            start = vals["start"]
            zeroes = vals["zeroes"]
            suffix = vals["suffix"]
            add_counter = vals.get("add_counter", True)
            
            for i, thumb in enumerate(sorted_thumbs):
                if add_counter:
                    counter = start + i
                    new_label = f"{prefix}{counter:0{zeroes}d}{suffix}"
                else:
                    new_label = f"{prefix}{suffix}"
                
                try:
                    all_items = getattr(self.model, "all_items", self.model.items)
                    row = all_items.index(thumb.data)
                    idx = self.model.index(row, 2) # Column 2 is Label
                    self.model.setData(idx, new_label, Qt.EditRole)
                except ValueError:
                    continue
            
            self.model.layoutChanged.emit()

    def _show_fast_tooltip(self):
        if not self._last_tooltip_local_pos: return
        item = self.view.itemAt(self._last_tooltip_local_pos)
        if item and hasattr(item, "toolTip"):
            tip = item.toolTip()
            if tip:
                QToolTip.showText(self._last_tooltip_pos, tip, self.view)

    def set_show_reviews(self, show):
        self.show_reviews = bool(show)
        self.update_video_overlay_geometry()

    def find_media_path(self, item_data):
        """Finds any playable review video or media file for the given item."""
        if not item_data:
            return None
            
        MEDIA_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".ogg", ".ogv", ".mxf")
        
        # 0. Check attached review_file_path if available
        rev_fp = getattr(item_data, "review_file_path", None)
        if rev_fp and os.path.exists(rev_fp) and rev_fp.lower().endswith(MEDIA_EXTENSIONS):
            return rev_fp

        # 0b. Check grouped items sharing the same group_key
        g_key = getattr(item_data, "group_key", None)
        all_items = getattr(self.model, "all_items", getattr(self.model, "items", [])) if hasattr(self, "model") and self.model else []
        if g_key and all_items:
            for other in all_items:
                if getattr(other, "group_key", None) == g_key:
                    o_fp = getattr(other, "file_path", "")
                    if o_fp and os.path.exists(o_fp) and o_fp.lower().endswith(MEDIA_EXTENSIONS):
                        item_data.review_file_path = o_fp
                        return o_fp
                    o_rev = getattr(other, "review_file_path", None)
                    if o_rev and os.path.exists(o_rev) and o_rev.lower().endswith(MEDIA_EXTENSIONS):
                        item_data.review_file_path = o_rev
                        return o_rev

        # 1. Direct path check
        if item_data.file_path.lower().endswith(MEDIA_EXTENSIONS):
            return item_data.file_path
            
        # 2. Check preset review path
        try:
            review_path = self.model._get_prefs_review_path(item_data)
            if review_path and os.path.exists(review_path) and review_path.lower().endswith(MEDIA_EXTENSIONS):
                return review_path
        except Exception:
            pass
            
        # 3. Sequence fallback search
        try:
            from logic.image_model import strip_sequence_counter
            name_no_ext, _ = os.path.splitext(item_data.filename)
            base_seq_name = strip_sequence_counter(name_no_ext)
            base_dir = os.path.dirname(item_data.file_path)
            
            possible_dirs = [
                base_dir,
                os.path.join(base_dir, "_reviews"),
                os.path.join(base_dir, "reviews"),
            ]
            if hasattr(self.model, "source_folder") and self.model.source_folder:
                src_f = self.model.source_folder
                possible_dirs.append(src_f)
                if os.path.exists(src_f):
                    for sub in os.listdir(src_f):
                        subp = os.path.join(src_f, sub)
                        if os.path.isdir(subp):
                            possible_dirs.append(subp)

            possible_basenames = [
                base_seq_name,
                f"{base_seq_name}_review",
                f"{base_seq_name}_review_converted"
            ]
            
            for p_dir in possible_dirs:
                if os.path.exists(p_dir):
                    for p_base in possible_basenames:
                        for ext in MEDIA_EXTENSIONS:
                            test_path = os.path.join(p_dir, f"{p_base}{ext}").replace("\\", "/")
                            if os.path.exists(test_path):
                                item_data.review_file_path = test_path
                                return test_path
        except Exception:
            pass
            
        return None

    def _cycle_player_mode(self):
        if self.player_mode == "selected":
            self.player_mode = "all"
            self.btn_player_mode.setText("Player: All")
        elif self.player_mode == "all":
            self.player_mode = "stop"
            self.btn_player_mode.setText("Player: Stop")
        else:
            self.player_mode = "selected"
            self.btn_player_mode.setText("Player: Selected")
            
        self.update_video_overlay_geometry()

    def update_video_overlay_geometry(self):
        """Position and size the video player overlays perfectly based on current player mode."""
        if not hasattr(self, 'video_player'):
            return
            
        from gui.video_player import is_multimedia_available
        if not is_multimedia_available():
            self.video_player.clear_video()
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
            return
            
        # 1. Stop Mode
        if self.player_mode == "stop":
            self.video_player.clear_video()
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
            return
            
        # 2. Selected Mode
        if self.player_mode == "selected":
            # Clear all multiple active players
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
            
            selected = self.scene.selectedItems()
            selected_thumb = None
            for it in selected:
                if isinstance(it, ThumbnailItem) and it.isVisible():
                    selected_thumb = it
                    break
                    
            if not selected_thumb or not self.model:
                self.video_player.clear_video()
                return
                
            item_data = selected_thumb.data
            video_path = self.find_media_path(item_data)
                    
            if not video_path or not os.path.exists(video_path):
                self.video_player.clear_video()
                return
                
            image_rect_scene = selected_thumb.mapToScene(selected_thumb.get_image_rect()).boundingRect()
            viewport_rect = self.view.mapFromScene(image_rect_scene).boundingRect()
            
            self.video_player.setGeometry(viewport_rect)
            self.video_player.load_video(video_path, item_data.filename)
            return

        # 3. All Mode
        if self.player_mode == "all":
            self.video_player.clear_video()
            
            # Get viewport scene rect
            viewport_rect_scene = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
            
            # Find all visible thumbnail items that have a playable video
            visible_video_thumbs = []
            for item in self.scene.items():
                if isinstance(item, ThumbnailItem) and item.isVisible():
                    if item.sceneBoundingRect().intersects(viewport_rect_scene):
                        video_path = self.find_media_path(item.data)
                        if video_path and os.path.exists(video_path):
                            visible_video_thumbs.append((item, video_path))
            
            # Rebuild dynamic players mapping
            new_active_players = {}
            for thumb_item, video_path in visible_video_thumbs:
                image_rect_scene = thumb_item.mapToScene(thumb_item.get_image_rect()).boundingRect()
                viewport_rect = self.view.mapFromScene(image_rect_scene).boundingRect()
                
                if thumb_item in self.active_players:
                    player = self.active_players[thumb_item]
                    player.setGeometry(viewport_rect)
                    if not player.is_playing:
                        player.load_video(video_path, thumb_item.data.filename)
                    else:
                        player.show()
                    new_active_players[thumb_item] = player
                else:
                    from gui.video_player import VideoPlayerOverlay
                    player = VideoPlayerOverlay(self.view.viewport())
                    player.setGeometry(viewport_rect)
                    player.load_video(video_path, thumb_item.data.filename)
                    new_active_players[thumb_item] = player
            
            # Clean up out of view or deleted players
            for thumb_item, player in list(self.active_players.items()):
                if thumb_item not in new_active_players:
                    player.clear_video()
                    player.deleteLater()
                    
            self.active_players = new_active_players
            return

    def _on_scene_selection_changed(self):
        self._has_selection = bool(self.scene.selectedItems())
        # Note: Qt automatically schedules repaints for selection changes;
        # calling scene.update() here would cause a race with in-progress
        # item updates (e.g. QGraphicsTextItem cursor changes) and make notes disappear.
        self._update_note_toolbar()
        self.update_video_overlay_geometry()

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

    def setModel(self, model):
        self.model = model
        self.model.rowsInserted.connect(self._on_rows_inserted)
        self.model.rowsAboutToBeRemoved.connect(self._on_rows_removed)
        self.model.modelReset.connect(self.add_items)
        self.model.dataChanged.connect(self._on_data_changed)

    def _get_item_key(self, item_data):
        if not item_data:
            return None
        if getattr(item_data, "file_path", None):
            return item_data.file_path
        if getattr(item_data, "ayon_path", None):
            return item_data.ayon_path
        return id(item_data)

    def clear_canvas(self):
        """Completely clear the scene of all elements, including thumbnails, notes, and backdrops."""
        if hasattr(self, "active_players"):
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
        if hasattr(self, "video_player"):
            self.video_player.clear_video()
        self.scene.clear()
        self.item_to_thumb.clear()
        self.scene_items_changed.emit()

    def add_items(self, items=None):
        """Initial populate or full reset."""
        if hasattr(self, "active_players"):
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
        if hasattr(self, "video_player"):
            self.video_player.clear_video()

        # Remove only ThumbnailItem instances from the scene, preserving notes/backdrops
        for item in list(self.scene.items()):
            if isinstance(item, ThumbnailItem):
                self.scene.removeItem(item)
        self.item_to_thumb.clear()
        
        if items is None and self.model:
            items = getattr(self.model, "all_items", self.model.items)
            
        if not items: return

        # Cache current sizes to apply to new items
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()

        for item_data in items:
            thumb = ThumbnailItem(item_data)
            is_custom = getattr(item_data, "is_custom_size", False)
            if not is_custom:
                size_to_use = thumb_size
                item_data.size = thumb_size
            else:
                size_to_use = getattr(item_data, "size", thumb_size)
            thumb.size = size_to_use
            thumb.is_custom_size = is_custom
            thumb.font_size = font_size
            thumb.update_tooltip(self.tooltip_templates, self.model)
            self.scene.addItem(thumb)
            self.item_to_thumb[item_data] = thumb
            
        self.rearrange_items()
        self.frame_all()

    def _on_rows_inserted(self, parent, first, last):
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()
        all_items = getattr(self.model, "all_items", self.model.items)
        
        for row in range(first, last + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data not in self.item_to_thumb:
                    thumb = ThumbnailItem(item_data)
                    is_custom = getattr(item_data, "is_custom_size", False)
                    if not is_custom:
                        size_to_use = thumb_size
                        item_data.size = thumb_size
                    else:
                        size_to_use = getattr(item_data, "size", thumb_size)
                    thumb.size = size_to_use
                    thumb.is_custom_size = is_custom
                    thumb.font_size = font_size
                    thumb.update_tooltip(self.tooltip_templates, self.model)
                    self.scene.addItem(thumb)
                    self.item_to_thumb[item_data] = thumb
        self.rearrange_items()

    def _on_rows_removed(self, parent, first, last):
        all_items = getattr(self.model, "all_items", self.model.items)
        for row in range(first, last + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data in self.item_to_thumb:
                    thumb = self.item_to_thumb.pop(item_data)
                    if hasattr(self, "active_players") and thumb in self.active_players:
                        player = self.active_players.pop(thumb)
                        player.clear_video()
                        player.deleteLater()
                    self.scene.removeItem(thumb)

    def _on_data_changed(self, top_left, bottom_right, roles=None):
        all_items = getattr(self.model, "all_items", self.model.items)
        for row in range(top_left.row(), bottom_right.row() + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data in self.item_to_thumb:
                    thumb = self.item_to_thumb[item_data]
                    thumb.cached_label = ""
                    thumb.update_tooltip(self.tooltip_templates, self.model)
                    thumb.update()

    def rearrange_items(self, age_filter=None, search_text=None, ignore_text=None, force=False):
        if not self.item_to_thumb or not self.model: return
        
        for item in self.item_to_thumb.values():
            item.cached_label = ""
        
        if age_filter is not None:
            self._last_age_filter = age_filter
        if search_text is not None:
            self._last_search_text = search_text
        if ignore_text is not None:
            self._last_ignore_text = ignore_text
            
        age_enabled, age_val = self._last_age_filter
        search_term = self._last_search_text
        ignore_strings = self._last_ignore_text.lower().split() if getattr(self, "_last_ignore_text", "") else []

        v_stack_enabled = getattr(self.model, "v_stack_enabled", False)

        show_reviews = getattr(self, "show_reviews", True)
        if hasattr(self, "window") and callable(self.window):
            win = self.window()
            if win and hasattr(win, "show_reviews"):
                show_reviews = win.show_reviews
            elif win and hasattr(win, "config"):
                show_reviews = win.config.get("show_reviews", True)

        visible_items = []
        all_items = getattr(self.model, "all_items", self.model.items)
        for item_data in all_items:
            item = self.item_to_thumb.get(item_data)
            if not item: continue
            
            # Visibility logic
            is_tagged = item_data.is_tagged
            item_abs = os.path.normpath(os.path.abspath(item_data.file_path))
            filter_abs = os.path.normpath(os.path.abspath(self._path_filter))
            in_path = not self._path_filter or (item_abs == filter_abs or item_abs.startswith(filter_abs + os.sep))
            
            show_by_tag = True
            if self._tag_filter_state == "enabled": show_by_tag = is_tagged
            elif self._tag_filter_state == "disabled": show_by_tag = not is_tagged
            
            is_young_enough = not age_enabled or (item_data.age_minutes <= age_val)
            matches_search = (not search_term or 
                              search_term in item_data.label.lower() or 
                              search_term in item_data.filename.lower())
            
            is_ignored = False
            if ignore_strings:
                lbl_lower = item_data.label.lower()
                fn_lower = item_data.filename.lower()
                for ign in ignore_strings:
                    if ign in lbl_lower or ign in fn_lower:
                        is_ignored = True
                        break
            
            is_visible_ver = not v_stack_enabled or self.model.is_item_visible_by_v_stack(item_data, True)
            is_rev = getattr(item_data, "is_review_repre", False)
            
            if show_by_tag and in_path and is_young_enough and matches_search and not is_ignored and is_visible_ver and (show_reviews or not is_rev):
                item.show()
                visible_items.append(item)
            else:
                item.hide()

        if not visible_items:
            return
            
        # Use last arrangement values
        vals = self._last_arrange_vals.copy()
        
        # Calculate horizontal gap dynamically: 20% of default thumbnail size
        dynamic_gap_h = int(self.slider_thumb_size.value() * 0.20)
        vals["gap_h"] = dynamic_gap_h
        self._last_arrange_vals["gap_h"] = dynamic_gap_h
        
        # Calculate vertical gap dynamically: 40% of average thumbnail height (metadata-driven height)
        total_h = 0.0
        count = 0
        for item in visible_items:
            w = item.data.metadata.get("width", None)
            h = item.data.metadata.get("height", None)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
                
            item_size = getattr(item, "size", self.slider_thumb_size.value())
            total_h += item_size / aspect
            count += 1
            
        if count > 0:
            avg_height = total_h / count
            dynamic_gap_v = int(avg_height * 0.20)
            vals["gap_v"] = dynamic_gap_v
            self._last_arrange_vals["gap_v"] = dynamic_gap_v
            
        if force:
            self._apply_arrangement(visible_items, "grid", vals, anchor=(0, 0), ignore_manual=False)
        else:
            already_placed = []
            unplaced = []
            for thumb in visible_items:
                key = self._get_item_key(thumb.data)
                has_pos = (
                    getattr(thumb.data, "has_placed_position", False) or
                    getattr(thumb, "is_manually_moved", False) or
                    getattr(thumb.data, "is_manually_moved", False) or
                    (key in self.item_positions)
                )
                if has_pos:
                    if key in self.item_positions:
                        px, py = self.item_positions[key]
                    else:
                        px, py = thumb.data.position
                    thumb.setPos(px, py)
                    thumb.data.position = (px, py)
                    thumb.data.has_placed_position = True
                    if key: self.item_positions[key] = (px, py)
                    already_placed.append(thumb)
                else:
                    unplaced.append(thumb)

            if unplaced:
                if self._marked_placement_pos is not None:
                    start_x = self._marked_placement_pos.x()
                    start_y = self._marked_placement_pos.y()
                elif already_placed:
                    max_x = max(t.sceneBoundingRect().right() for t in already_placed)
                    min_y = min(t.sceneBoundingRect().top() for t in already_placed)
                    start_x = max_x + vals["gap_h"]
                    start_y = min_y
                else:
                    start_x = 0.0
                    start_y = 0.0

                gap_h = vals["gap_h"]
                gap_v = vals["gap_v"]

                # Get existing placed bounding rects (placed thumbnails, notes, backdrops, etc.)
                placed_rects = [
                    it.sceneBoundingRect() for it in self.scene.items()
                    if it.isVisible() and it not in unplaced
                ]

                curr_x = start_x
                for thumb in unplaced:
                    rect = thumb.boundingRect()
                    item_w = rect.width() if rect.width() > 0 else getattr(thumb, "size", 150) + gap_h
                    item_h = rect.height() if rect.height() > 0 else getattr(thumb, "size", 150) + 50 + gap_v

                    test_x = curr_x
                    test_y = start_y

                    # Shift test_y down by one item height + vertical gap if overlap detected
                    step_y = max(item_h + gap_v, 50.0)
                    while True:
                        test_rect = QRectF(test_x, test_y, item_w, item_h)
                        if any(test_rect.intersects(r) for r in placed_rects):
                            test_y += step_y
                        else:
                            break

                    thumb.setPos(test_x, test_y)
                    thumb.data.position = (test_x, test_y)
                    thumb.data.has_placed_position = True
                    key = self._get_item_key(thumb.data)
                    if key:
                        self.item_positions[key] = (test_x, test_y)

                    placed_rects.append(QRectF(test_x, test_y, item_w, item_h))
                    curr_x = test_x + item_w + gap_h

                self._marked_placement_pos = QPointF(curr_x, start_y)

        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    def set_path_filter(self, path):
        self._path_filter = path
        self.rearrange_items()

    def _cycle_tag_filter(self):
        states = ["all", "enabled", "disabled"]
        curr_idx = states.index(self._tag_filter_state)
        self._tag_filter_state = states[(curr_idx + 1) % len(states)]
        self.btn_tag_filter.setText(f"Filter: {self._tag_filter_state.capitalize()}")
        self.rearrange_items()

    def update_label_validator(self, regex_str):
        # Temporarily disabled per user request
        pass
        # regex = QRegularExpression(regex_str)
        # validator = QRegularExpressionValidator(regex, self.inline_editor)
        # self.inline_editor.setValidator(validator)

    def update_font_size(self):
        font_size = self.slider_text_size.value()
        for item in self.item_to_thumb.values():
            item.prepareGeometryChange()
            item.font_size = font_size
            item.cached_label = ""
            item.update()
        self.rearrange_items()
        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    def update_thumb_size(self):
        new_size = self.slider_thumb_size.value()
        for item in self.item_to_thumb.values():
            item.prepareGeometryChange()
            item.size = new_size
            item.data.size = new_size
            item.update()
        self.rearrange_items()
        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    def _update_paste_button_state(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        # QMimeData check is faster than converting to QImage
        has_image = clipboard.mimeData().hasImage()
        if has_image:
            self.btn_paste.setStyleSheet("color: white; font-weight: bold;")
            self.btn_paste.setEnabled(True)
        else:
            self.btn_paste.setStyleSheet("color: #666666;")
            self.btn_paste.setEnabled(False)

    

    def frame_all(self):
        rect = self.scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.view.fitInView(rect.adjusted(-50, -50, 50, 50), Qt.KeepAspectRatio)
            self.update_zoom_indicator()

    def frame_selection(self):
        items = self.scene.selectedItems()
        if not items: return
        
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
            
        if not rect.isEmpty():
            self.view.fitInView(rect.adjusted(-50, -50, 50, 50), Qt.KeepAspectRatio)
            self.update_zoom_indicator()

    def eventFilter(self, source, event):
        if self._draw_mode_active:
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove, QEvent.MouseButtonDblClick, QEvent.Wheel):
                if source in (self.view, self.view.viewport()):
                    return False
            if event.type() == QEvent.KeyPress:
                modifiers = event.modifiers()
                if not (modifiers & (Qt.ControlModifier | Qt.AltModifier)):
                    key = event.key()
                    if key == Qt.Key_Escape:
                        self.exit_draw_mode(save=True)
                        return True
                    elif key == Qt.Key_B:
                        self.draw_toolbar.btn_brush.click()
                        return True
                    elif key == Qt.Key_E:
                        self.draw_toolbar.btn_eraser.click()
                        return True
                    elif key == Qt.Key_A:
                        self.draw_toolbar.btn_arrow.click()
                        return True
                    elif key == Qt.Key_C:
                        self.draw_toolbar.btn_color.click()
                        return True
                    elif key in (Qt.Key_Delete, Qt.Key_Backspace):
                        if self._edit_draw_item:
                            self.delete_draw_item_safely(self._edit_draw_item)
                            self._edit_draw_item = None
                        self.clear_canvas_drawings()
                        self.exit_draw_mode(save=False)
                        return True
                    elif key == Qt.Key_BracketLeft:
                        idx = self.draw_toolbar.combo_thickness.currentIndex()
                        if idx > 0:
                            self.draw_toolbar.combo_thickness.setCurrentIndex(idx - 1)
                        return True
                    elif key == Qt.Key_BracketRight:
                        idx = self.draw_toolbar.combo_thickness.currentIndex()
                        if idx < self.draw_toolbar.combo_thickness.count() - 1:
                            self.draw_toolbar.combo_thickness.setCurrentIndex(idx + 1)
                        return True
                return True

        if event.type() == QEvent.Enter:
            self.view.setFocus()
            
        if event.type() == QEvent.Resize:
            if source in (self.view, self.view.viewport()):
                QTimer.singleShot(1, self.update_video_overlay_geometry)
            
        if event.type() == QEvent.Wheel:
            if source in (self.view, self.view.viewport()):
                self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                angle = event.angleDelta().y()
                factor = 1.15 if angle > 0 else 1 / 1.15
                self.view.scale(factor, factor)
                self.update_zoom_indicator()
                self.update_video_overlay_geometry()
                return True # Prevent default scrolling/panning
        
        if event.type() == QEvent.MouseMove:
            if source is self.view.viewport():
                # Handle tooltip
                self._tooltip_timer.stop()
                self._tooltip_timer.start(300) # 300ms delay
                self._last_tooltip_pos = event.globalPos()
                self._last_tooltip_local_pos = event.pos()
  
                if self._is_panning:
                    delta = event.pos() - self._last_pan_pos
                    self._last_pan_pos = event.pos()
                    
                    self.view.setTransformationAnchor(QGraphicsView.NoAnchor)
                    factor = self.view.transform().m11()
                    self.view.translate(delta.x() / factor, delta.y() / factor)
                    self.update_video_overlay_geometry()
                    return True

        if event.type() == QEvent.Leave:
            self._tooltip_timer.stop()
            QToolTip.hideText()

        if event.type() == QEvent.MouseButtonPress:
            self._tooltip_timer.stop()
            QToolTip.hideText()
            if source in (self.view, self.view.viewport()):
                self._last_click_scene_pos = self.view.mapToScene(event.pos())
                
                is_middle = event.button() == Qt.MiddleButton
                is_ctrl_left = event.button() == Qt.LeftButton and (event.modifiers() & Qt.ControlModifier)
                
                if is_middle or is_ctrl_left:
                    self._is_panning = True
                    self._last_pan_pos = event.pos()
                    self.view.viewport().setCursor(Qt.ClosedHandCursor)
                    return True
                    
                if event.button() == Qt.LeftButton:
                    if not self.view.itemAt(event.pos()):
                        self._marked_placement_pos = self.view.mapToScene(event.pos())
                        self._show_placement_marker(self._marked_placement_pos)

                if event.button() == Qt.RightButton:
                    # Select the item under the mouse if it's not already selected,
                    # but do not clear selection if right-clicking empty space or a selected item.
                    item = self.view.itemAt(event.pos())
                    selectable_item = None
                    temp = item
                    while temp:
                        if temp.flags() & QGraphicsItem.ItemIsSelectable:
                            selectable_item = temp
                            break
                        temp = temp.parentItem()
                        
                    if selectable_item:
                        if not selectable_item.isSelected():
                            self.scene.clearSelection()
                            selectable_item.setSelected(True)
                else:
                    if not self.view.itemAt(event.pos()):
                        # Exit edit mode on any active text note before clearing selection
                        self._exit_active_note_edit()
                        self.scene.clearSelection()

        if event.type() == QEvent.MouseButtonRelease:
            # Process deferred change after the mouse release is finished
            QTimer.singleShot(0, self._process_deferred_scene_items_changed)
            if self._is_panning:
                self._is_panning = False
                self.view.viewport().setCursor(Qt.ArrowCursor)
                self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                return True
        
        if event.type() == QEvent.MouseButtonDblClick:
            if source is self.view.viewport():
                item = self.view.itemAt(event.pos())
                if item:
                    # Ignore double-clicks on text notes and backdrops
                    temp = item
                    while temp:
                        if isinstance(temp, (TextNoteItem, BackdropItem)):
                            return False
                        temp = temp.parentItem()

                    # Find the ThumbnailItem
                    thumb_item = item
                    while thumb_item and not hasattr(thumb_item, 'get_label_top'):
                        thumb_item = thumb_item.parentItem()

                    if thumb_item:
                        # Clear current selection first
                        self.scene.clearSelection()
                        # Select only this thumbnail item
                        thumb_item.setSelected(True)
                        # Frame selection
                        self.frame_selection()
                        return True
                    else:
                        return True
                else:
                    self.frame_all()
                    return True
        elif event.type() == QEvent.KeyPress:
            if source is self.inline_editor:
                if event.key() == Qt.Key_Escape:
                    self.inline_editor.hide()
                    self._editing_item = None
                    self.view.setFocus()
                    return True
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    self._on_inline_editing_finished()
                    return True
                # For any other key in the editor, let it process natively, do NOT fall through
                return False
                
            # Disable global hotkeys if any text note is being edited
            focus_item = self.scene.focusItem()
            if focus_item and isinstance(focus_item, QGraphicsTextItem):
                return False

            if event.key() == Qt.Key_D and not self._draw_mode_active:
                if not self._editing_item:
                    self.enter_draw_mode()
                    return True

            # Version stack hotkeys
            modifiers = event.modifiers()
            is_alt = bool(modifiers & Qt.AltModifier)
            is_ctrl = bool(modifiers & Qt.ControlModifier)
            key_code = event.key()
            if key_code in (Qt.Key_Up, Qt.Key_Down) and is_alt:
                if self.model:
                    selected = self.scene.selectedItems()
                    selected_thumbs = [it for it in selected if isinstance(it, ThumbnailItem)]
                    if selected_thumbs:
                        processed_keys = set()
                        for thumb_item in selected_thumbs:
                            item = thumb_item.data
                            key = self.model.get_version_stack_key(item)
                            if key in processed_keys:
                                continue
                            processed_keys.add(key)
                            
                            stack = self.model.version_stacks.get(key)
                            if not stack or len(stack["items"]) <= 1:
                                continue
                                
                            sorted_versions = sorted([it.version for it in stack["items"]])
                            current_picked = stack["picked"]
                            
                            target_version = None
                            if is_ctrl and key_code == Qt.Key_Up:
                                # Max version
                                max_v = sorted_versions[-1]
                                if current_picked != max_v:
                                    target_version = max_v
                            elif is_ctrl and key_code == Qt.Key_Down:
                                # Min version
                                min_v = sorted_versions[0]
                                if current_picked != min_v:
                                    target_version = min_v
                            elif not is_ctrl and key_code == Qt.Key_Up:
                                # Next version
                                for v in sorted_versions:
                                    if v > current_picked:
                                        target_version = v
                                        break
                            elif not is_ctrl and key_code == Qt.Key_Down:
                                # Previous version
                                for v in reversed(sorted_versions):
                                    if v < current_picked:
                                        target_version = v
                                        break
                                        
                            if target_version is not None:
                                self.change_version_requested.emit(item, target_version)
                        return True

            # Global shortcuts (only when editor is NOT active)
            if event.key() == Qt.Key_A and (event.modifiers() & Qt.AltModifier):
                self._on_arrange("grid")
                return True
            elif event.key() == Qt.Key_Space:
                if self.view.underMouse():
                    self.maximize_toggle_requested.emit()
                    return True
            elif event.key() in [Qt.Key_Plus, Qt.Key_Equal]:
                if self.view.underMouse():
                    self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
                    self.view.scale(1.15, 1.15)
                    self.update_zoom_indicator()
                    return True
            elif event.key() == Qt.Key_Minus:
                if self.view.underMouse():
                    self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
                    self.view.scale(1/1.15, 1/1.15)
                    self.update_zoom_indicator()
                    return True
            elif event.key() == Qt.Key_Z:
                if self.view.underMouse():
                    self.frame_all()
                    return True
            elif event.key() == Qt.Key_F:
                if self.view.underMouse():
                    self.frame_selection()
                    return True
            elif event.key() == Qt.Key_O and (event.modifiers() & Qt.ControlModifier):
                if self.view.underMouse():
                    self._on_action_os_open()
                    return True
            elif event.key() == Qt.Key_N and (event.modifiers() & Qt.ControlModifier):
                if self.view.underMouse():
                    self.add_text_note()
                    return True
            elif event.key() == Qt.Key_N and (event.modifiers() & Qt.AltModifier):
                if self.view.underMouse():
                    self.add_backdrop()
                    return True
            elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                if self.view.underMouse() or self.view.hasFocus():
                    selected = self.scene.selectedItems()
                    notes = [it for it in selected if isinstance(it, (TextNoteItem, BackdropItem, DrawItem))]
                    
                    ayon_items_to_delete = []
                    for it in selected:
                        if hasattr(it, "data") and getattr(it.data, "is_ayon_item", False):
                            ayon_items_to_delete.append(it.data)
                            
                    handled = False
                    if notes:
                        non_notes_non_ayon = [it for it in selected if not isinstance(it, (TextNoteItem, BackdropItem, DrawItem)) and not getattr(getattr(it, "data", None), "is_ayon_item", False)]
                        if not non_notes_non_ayon:
                            self.delete_selected_notes()
                            self.scene_items_changed.emit()
                            handled = True

                    if ayon_items_to_delete:
                        if self.model:
                            self.model.remove_items(ayon_items_to_delete)
                        handled = True

                    if handled:
                        return True
        
        if event.type() == QEvent.Gesture:
            return self.gestureEvent(event)
            
        return super().eventFilter(source, event)

    def _show_placement_marker(self, pos):
        from PySide6.QtWidgets import QGraphicsEllipseItem
        from PySide6.QtGui import QPen, QColor, QBrush
        from PySide6.QtCore import QVariantAnimation
        
        if not hasattr(self, "_active_marker_anims"):
            self._active_marker_anims = []
            
        r = 60
        marker = QGraphicsEllipseItem(pos.x() - r, pos.y() - r, r * 2, r * 2)
        marker.setPen(QPen(QColor(0, 255, 255), 4))
        marker.setBrush(QBrush(QColor(0, 255, 255, 80)))
        marker.setZValue(9999)
        self.scene.addItem(marker)
        
        anim = QVariantAnimation()
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(400)
        
        self._active_marker_anims.append(anim)
        
        def update_opacity(val):
            marker.setOpacity(val)
            
        def remove_marker():
            if marker in self.scene.items():
                self.scene.removeItem(marker)
            if anim in self._active_marker_anims:
                self._active_marker_anims.remove(anim)
                
        anim.valueChanged.connect(update_opacity)
        anim.finished.connect(remove_marker)
        anim.start()

    def _start_inline_rename(self, item):
        # Ensure we have a ThumbnailItem (or a child of one)
        orig_item = item
        while item and not hasattr(item, 'get_label_top'):
            item = item.parentItem()
            
        if not item:
            # If it was a TextNoteItem child, we don't want to trigger rename
            return

        self._editing_item = item
        
        # Calculate scene position of the first line
        label_top_scene = item.get_label_top()
        # Map center of the first line to view
        scene_pt = item.mapToScene(QPointF(item.boundingRect().width() / 2, label_top_scene))
        view_pt = self.view.mapFromScene(scene_pt)
        
        self.inline_editor.setText(item.data.label)
        
        # Match font size (slightly bigger for clarity)
        font = self.inline_editor.font()
        target_size = item.font_size + 1
        font.setPointSize(target_size)
        self.inline_editor.setFont(font)
        
        # Calculate width to fit text
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(item.data.label) + 24
        editor_w = int(max(item.size, text_w) * 0.8)
        # Cap at viewport width
        editor_w = min(self.view.viewport().width() - 40, editor_w)
        self.inline_editor.setFixedWidth(editor_w)
        
        # Position: centered horizontally, top aligned with first line
        # Offset Y slightly for padding alignment
        self.inline_editor.move(view_pt.x() - editor_w // 2, view_pt.y() - 4)
        
        self.inline_editor.show()
        self.inline_editor.setFocus()
        self.inline_editor.selectAll()
        item.set_editing(True)

    def _on_inline_editing_finished(self):
        item = self._editing_item
        if not item: return
        self._editing_item = None # Clear early to prevent reentrancy
        
        new_label = self.inline_editor.text().strip()
        if new_label and new_label != item.data.label:
            # Update the source of truth (model)
            if self.model:
                all_items = getattr(self.model, "all_items", self.model.items)
                for i, m_item in enumerate(all_items):
                    if m_item == item.data:
                        idx = self.model.index(i, 2)
                        self.model.setData(idx, new_label, Qt.EditRole)
                        break
        
        item.set_editing(False)
        self.inline_editor.hide()
        self.view.setFocus()

    def update_zoom_indicator(self):
        lod = self.view.transform().m11()
        percent = int(lod * 100)
        self.lbl_zoom.setText(f"{percent}%")
        
        if lod > 0.6:
            self.lbl_zoom.setStyleSheet("color: #4CAF50; font-family: monospace; font-weight: bold; background: rgba(30,30,30,180); padding: 2px; border: 1px solid #4CAF50; border-radius: 3px;")
        else:
            self.lbl_zoom.setStyleSheet("color: #F44336; font-family: monospace; font-weight: bold; background: rgba(30,30,30,180); padding: 2px; border: 1px solid #F44336; border-radius: 3px;")
            
        v_width = self.view.width()
        self.lbl_zoom.move(v_width - self.lbl_zoom.width() - 25, 15)
        self.lbl_zoom.raise_()

    def gestureEvent(self, event):
        pinch = event.gesture(Qt.PinchGesture)
        if pinch:
            factor = pinch.scaleFactor()
            if factor != 1.0:
                self.view.scale(factor, factor)
                self.update_zoom_indicator()
            return True
        return False

    def _on_show_text_toggled(self, checked):
        self.scene.show_labels = checked
        self.scene.update()

    def resizeEvent(self, event):
        self.update_zoom_indicator()
        super().resizeEvent(event)

    def _reflow_only(self):
        if not self.item_to_thumb or not self.model: return
        view_width = self.view.viewport().width()
        cols = max(5, view_width // 240)
        
        self.slider_cols.blockSignals(True)
        self.slider_cols.setValue(cols)
        self.slider_cols.blockSignals(False)
        
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()
        line_height = font_size * 1.5
        thumb_h = int(thumb_size + 25 + (line_height * 3.5))
        thumb_h = max(100, thumb_h)
        
        spacing_x = thumb_size + 50
        
        current_row = 0
        current_col = 0
        all_items = getattr(self.model, "all_items", self.model.items)
        for item_data in all_items:
            item = self.item_to_thumb.get(item_data)
            if not item: continue
            
            if not item.is_manually_moved:
                new_x, new_y = current_col * spacing_x, current_row * thumb_h
                item.setPos(new_x, new_y)
                item_data.position = (new_x, new_y)
                
            current_col += 1
            if current_col >= cols:
                current_col = 0
                current_row += 1

    def contextMenuEvent(self, event):
        menu = QMenu(self.window())
        
        add_note_action = QAction("Add Text Note", self)
        add_note_action.triggered.connect(self.add_text_note)
        menu.addAction(add_note_action)
        
        add_backdrop_action = QAction("Add Backdrop", self)
        add_backdrop_action.triggered.connect(self.add_backdrop)
        menu.addAction(add_backdrop_action)

        # Check for backdrop under cursor for editing
        backdrop_under_cursor = None
        it = self.view.itemAt(self.view.mapFromGlobal(event.globalPos()))
        while it:
            if isinstance(it, BackdropItem):
                backdrop_under_cursor = it
                break
            it = it.parentItem()

        if backdrop_under_cursor:
            edit_backdrop_action = QAction("Edit Backdrop", self)
            edit_backdrop_action.triggered.connect(lambda: self.edit_backdrop(backdrop_under_cursor))
            menu.addAction(edit_backdrop_action)
            
            delete_backdrop_action = QAction("Delete Backdrop", self)
            delete_backdrop_action.triggered.connect(lambda: self.delete_backdrop(backdrop_under_cursor))
            menu.addAction(delete_backdrop_action)

        menu.addSeparator()
        
        # Draw precedence (only when thumbnails are selected)
        selected_thumbs = [it for it in self.scene.selectedItems() if isinstance(it, ThumbnailItem)]
        if selected_thumbs:
            front_action = QAction("Move to Front", self)
            front_action.triggered.connect(self.move_selected_to_front)
            menu.addAction(front_action)

            back_action = QAction("Move to Back", self)
            back_action.triggered.connect(self.move_selected_to_back)
            menu.addAction(back_action)

        menu.addSeparator()
        
        tag_action = QAction("Enable/Disable Selected", self)
        tag_action.triggered.connect(self.tag_toggle_requested.emit)
        menu.addAction(tag_action)
        
        menu.addSeparator()
        action_seq_rename = QAction("Sequence Rename...", self)
        action_seq_rename.triggered.connect(self._on_sequence_rename)
        # Enable only if something is selected
        action_seq_rename.setEnabled(bool(self.scene.selectedItems()))
        menu.addAction(action_seq_rename)
        
        # Add OS Open action
        action_os_open = QAction("OS Open", self)
        action_os_open.setShortcut("Ctrl+O")
        action_os_open.triggered.connect(self._on_action_os_open)
        # Filter for ThumbnailItems
        selected = self.scene.selectedItems()
        target_items = [it for it in selected if isinstance(it, ThumbnailItem)]
        action_os_open.setEnabled(bool(target_items))
        menu.addAction(action_os_open)
        
        menu.addSeparator()
        reset_action = QAction("Reset Label", self)
        reset_action.triggered.connect(lambda: self.label_action_requested.emit("reset", None))
        menu.addAction(reset_action)
        prefix_action = QAction("Add Prefix...", self)
        prefix_action.triggered.connect(lambda: self.label_action_requested.emit("prefix", None))
        menu.addAction(prefix_action)
        suffix_action = QAction("Add Suffix...", self)
        suffix_action.triggered.connect(lambda: self.label_action_requested.emit("suffix", None))
        menu.addAction(suffix_action)
        
        search_replace_action = QAction("Search and Replace...", self)
        search_replace_action.triggered.connect(lambda: self.label_action_requested.emit("search_replace", None))
        menu.addAction(search_replace_action)
        
        menu.addSeparator()
        trim_len_action = QAction("Trim to Length...", self)
        trim_len_action.triggered.connect(lambda: self.label_action_requested.emit("trim_length", None))
        menu.addAction(trim_len_action)
        
        trim_right_action = QAction("Trim Right...", self)
        trim_right_action.triggered.connect(lambda: self.label_action_requested.emit("trim_right", None))
        menu.addAction(trim_right_action)
        
        trim_left_action = QAction("Trim Left...", self)
        trim_left_action.triggered.connect(lambda: self.label_action_requested.emit("trim_left", None))
        menu.addAction(trim_left_action)
        
        menu.addSeparator()
        arrange_action = QAction("Arrange", self)
        arrange_action.setShortcut("Alt+A")
        arrange_action.triggered.connect(lambda: self._on_arrange("grid"))
        menu.addAction(arrange_action)
        
        # Add open review action if a review video exists
        video_path = None
        selected = self.scene.selectedItems()
        selected_thumb = None
        for it in selected:
            if isinstance(it, ThumbnailItem) and it.isVisible():
                selected_thumb = it
                break
        if selected_thumb and self.model:
            video_path = self.find_media_path(selected_thumb.data)
                    
        if video_path:
            menu.addSeparator()
            open_review_action = QAction("Open Review Video in System Player", self)
            def _open_video():
                try:
                    os.startfile(video_path)
                except Exception as e:
                    print(f"Error opening review video: {e}")
            open_review_action.triggered.connect(_open_video)
            menu.addAction(open_review_action)
            
        if len(selected_thumbs) == 1 and self.model:
            thumb_item = selected_thumbs[0]
            item = thumb_item.data
            key = self.model.get_version_stack_key(item)
            stack = self.model.version_stacks.get(key)
            if stack and len(stack["items"]) > 1:
                v_stack_enabled = getattr(self.model, "v_stack_enabled", False)
                if v_stack_enabled:
                    sub_menu = menu.addMenu("Version Stack")
                    sorted_items = sorted(stack["items"], key=lambda it: it.version, reverse=True)
                    for v_item in sorted_items:
                        v = v_item.version
                        is_picked = (v == stack["picked"])
                        if is_picked:
                            action = QAction(f"> {v}", self)
                            action.setIcon(self._get_green_arrow_icon())
                            font = action.font()
                            font.setBold(True)
                            action.setFont(font)
                        else:
                            action = QAction(str(v), self)
                        action.triggered.connect(lambda checked=False, item_obj=item, ver=v: self.change_version_requested.emit(item_obj, ver))
                        sub_menu.addAction(action)
                else:
                    select_action = QAction("Version Stack Select", self)
                    select_action.triggered.connect(lambda checked=False, it_obj=item: self._select_all_items_in_stack(it_obj))
                    menu.addAction(select_action)
                    menu.addSeparator()

        menu.exec(event.globalPos())

    def _select_all_items_in_stack(self, item):
        if not self.model: return
        key = self.model.get_version_stack_key(item)
        stack = self.model.version_stacks.get(key)
        if not stack: return
        
        self.scene.blockSignals(True)
        self.scene.clearSelection()
        for it in stack["items"]:
            thumb = self.item_to_thumb.get(it)
            if thumb:
                thumb.setSelected(True)
        self.scene.blockSignals(False)
        self.scene.selectionChanged.emit()

    def move_selected_to_front(self):
        """Raise selected ThumbnailItems above all other thumbnails."""
        all_thumbs = [it for it in self.scene.items() if isinstance(it, ThumbnailItem)]
        selected = [it for it in all_thumbs if it.isSelected()]
        others = [it for it in all_thumbs if not it.isSelected()]
        if not selected:
            return
        # Find the highest z among non-selected thumbnails
        base_z = max((it.zValue() for it in others), default=0)
        # Place each selected item above: cap at 4999 (below text notes at 5000)
        for i, it in enumerate(selected):
            it.setZValue(min(base_z + 1 + i, 4999))
        self.scene_items_changed.emit()

    def move_selected_to_back(self):
        """Lower selected ThumbnailItems below all other thumbnails."""
        all_thumbs = [it for it in self.scene.items() if isinstance(it, ThumbnailItem)]
        selected = [it for it in all_thumbs if it.isSelected()]
        others = [it for it in all_thumbs if not it.isSelected()]
        if not selected:
            return
        # Find the lowest z among non-selected thumbnails
        base_z = min((it.zValue() for it in others), default=0)
        # Place each selected item below: floor at -999 (above backdrops at -1000)
        for i, it in enumerate(reversed(selected)):
            it.setZValue(max(base_z - 1 - i, -999))
        self.scene_items_changed.emit()

    def _on_action_os_open(self):
        selected = self.scene.selectedItems()
        paths = []
        for it in selected:
            if isinstance(it, ThumbnailItem) and it.data and it.data.file_path:
                paths.append(it.data.file_path)
        for path in paths:
            if os.path.exists(path):
                os.startfile(path)

    def wheelEvent(self, event):
        # Base wheel events for the widget itself (if any)
        super().wheelEvent(event)

    def _on_arrange(self, mode):
        if hasattr(self, "_arrange_dialog") and self._arrange_dialog:
            self._arrange_dialog.close()
            
        # 1. Identify target items
        selected = self.scene.selectedItems()
        # Filter for ThumbnailItems only
        target_items = [it for it in selected if isinstance(it, ThumbnailItem)]
        
        if not target_items:
            # Arrange all visible ThumbnailItems
            target_items = []
            all_items = getattr(self.model, "all_items", getattr(self.model, "items", []))
            for item_data in all_items:
                item = self.item_to_thumb.get(item_data)
                if item and item.isVisible() and item not in target_items:
                    target_items.append(item)
            for item in self.scene.items():
                if isinstance(item, ThumbnailItem) and item.isVisible() and item not in target_items:
                    target_items.append(item)
                    
        if not target_items: return
        
        # Store initial positions and sizes for revert
        initial_pos = {item: item.pos() for item in target_items}
        initial_sizes = {item: (getattr(item, "size", self.slider_thumb_size.value()), getattr(item, "is_custom_size", False)) for item in target_items}
        
        if "thumb_size" not in self._last_arrange_vals:
            first_size = initial_sizes[target_items[0]][0] if target_items else self.slider_thumb_size.value()
            self._last_arrange_vals["thumb_size"] = int(first_size)

        # Calculate top-left anchor point once
        anchor_x = min(p.x() for p in initial_pos.values())
        anchor_y = min(p.y() for p in initial_pos.values())
        anchor = (anchor_x, anchor_y)
        
        # 2. Show dialog
        self._arrange_dialog = ArrangeDialog(mode, self._last_arrange_vals, self)
        
        # Connect live updates
        self._arrange_dialog.valuesChanged.connect(lambda vals: self._apply_arrangement(target_items, mode, vals, anchor, mark_manual=True))
        
        def finalize():
            vals = self._arrange_dialog.get_values()
            self._apply_arrangement(target_items, mode, vals, anchor, mark_manual=True)
            self._last_arrange_vals = vals # Save for next time
            if target_items:
                max_x = max(it.sceneBoundingRect().right() for it in target_items)
                min_y = min(it.sceneBoundingRect().top() for it in target_items)
                self._marked_placement_pos = QPointF(max_x + vals.get("gap_h", 20), min_y)
            self._arrange_dialog = None
            
        def revert():
            for item, pos in initial_pos.items():
                item.setPos(pos)
                item.data.position = (pos.x(), pos.y())
                key = self._get_item_key(item.data)
                if key:
                    self.item_positions[key] = (pos.x(), pos.y())
                if item in initial_sizes:
                    old_size, old_custom = initial_sizes[item]
                    item.prepareGeometryChange()
                    item.size = old_size
                    item.data.size = old_size
                    item.is_custom_size = old_custom
                    item.data.is_custom_size = old_custom
                    item.update()
            self.scene.update()
            self._arrange_dialog = None
            
        self._arrange_dialog.accepted.connect(finalize)
        self._arrange_dialog.rejected.connect(revert)
        
        # Initial preview
        self._apply_arrangement(target_items, mode, self._arrange_dialog.get_values(), anchor, mark_manual=True)
        
        self._arrange_dialog.show()
        self._arrange_dialog.raise_()
        self._arrange_dialog.activateWindow()

    def _apply_arrangement(self, items, mode, vals, anchor=None, ignore_manual=False, mark_manual=False):
        if not items: return
        
        if ignore_manual:
            items = [item for item in items if not item.is_manually_moved]
            if not items: return
        
        arr_thumb_size = vals.get("thumb_size")
        if arr_thumb_size is not None:
            for item in items:
                if getattr(item, "size", None) != arr_thumb_size:
                    item.prepareGeometryChange()
                    item.size = arr_thumb_size
                    item.data.size = arr_thumb_size
                    item.is_custom_size = True
                    item.data.is_custom_size = True
                    item.update()

        sort_by = vals.get("sort_by", "File Name")
        reverse = vals.get("reverse", False)
        
        # Sort items based on criteria
        def sort_key(thumb):
            d = thumb.data
            if sort_by == "File Name": return d.filename.lower()
            if sort_by == "Label": return d.label.lower()
            if sort_by == "Version": return d.version
            if sort_by == "File Size": 
                try: return int(d.metadata.get("filesize", 0))
                except: return 0
            if sort_by == "Width": 
                try: return int(d.metadata.get("width", 0))
                except: return 0
            if sort_by == "Height": 
                try: return int(d.metadata.get("height", 0))
                except: return 0
            if sort_by == "Age": return d.modification_time
            if sort_by == "File Type":
                _, ext = os.path.splitext(d.file_path.lower())
                return ext
            return 0

        items = sorted(items, key=sort_key, reverse=reverse)
        
        if anchor:
            start_x, start_y = anchor
        else:
            start_x = items[0].scenePos().x()
            start_y = items[0].scenePos().y()
        
        gap_h = vals["gap_h"]
        gap_v = vals["gap_v"]
        cols = vals["cols"]
        
        show_text = self.btn_show_text.isChecked()
        font_size = self.slider_text_size.value()
        line_height = font_size * 1.5
        label_area = (line_height * 3.5) + 10 if show_text else 0

        def get_item_w(thumb):
            t_size = getattr(thumb, "size", self.slider_thumb_size.value())
            return t_size + 20

        def get_item_h(thumb):
            w = thumb.data.metadata.get("width", 1)
            h = thumb.data.metadata.get("height", 1)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
            t_size = getattr(thumb, "size", self.slider_thumb_size.value())
            return (t_size / aspect) + 20 + label_area

        # For grid, we need to track row heights to keep them aligned
        row_heights = []
        if mode == "grid":
            current_max_h = 0
            for i, item in enumerate(items):
                h = get_item_h(item)
                current_max_h = max(current_max_h, h)
                if (i + 1) % cols == 0 or (i + 1) == len(items):
                    row_heights.append(current_max_h)
                    current_max_h = 0

        group_cols = vals.get("group_cols", False)
        if mode == "grid" and group_cols:
            groups = {}
            for item in items:
                gk = getattr(item.data, "group_key", "")
                if gk not in groups:
                    groups[gk] = []
                groups[gk].append(item)
                
            group_keys = list(groups.keys())
            
            col_widths = []
            for gk in group_keys:
                max_w = 0
                for item in groups[gk]:
                    max_w = max(max_w, get_item_w(item))
                col_widths.append(max_w)
                
            for c_idx, gk in enumerate(group_keys):
                g_items = groups[gk]
                current_y_offset = 0
                x_pos = sum(col_widths[:c_idx]) + (c_idx * gap_h)
                
                for item in g_items:
                    h = get_item_h(item)
                    new_x = start_x + x_pos
                    new_y = start_y + current_y_offset
                    
                    item.setPos(new_x, new_y)
                    item.data.position = (new_x, new_y)
                    item.data.has_placed_position = True
                    key = self._get_item_key(item.data)
                    if key: self.item_positions[key] = (new_x, new_y)
                    if mark_manual:
                        item.is_manually_moved = True
                        item.data.is_manually_moved = True
                    current_y_offset += h + gap_v
            
            self.scene.update()
            return
            
        current_y_offset = 0
        for i, item in enumerate(items):
            h = get_item_h(item)
            w = get_item_w(item)
            
            if mode == "horizontal":
                new_x = start_x + i * (w + gap_h)
                new_y = start_y
            elif mode == "vertical":
                new_x = start_x
                new_y = start_y + current_y_offset
                current_y_offset += h + gap_v
            else: # grid
                row = i // cols
                col = i % cols
                new_x = start_x + col * (w + gap_h)
                y_pos = sum(row_heights[:row]) + (row * gap_v)
                new_y = start_y + y_pos
            
            item.setPos(new_x, new_y)
            item.data.position = (new_x, new_y)
            item.data.has_placed_position = True
            key = self._get_item_key(item.data)
            if key: self.item_positions[key] = (new_x, new_y)
            if mark_manual:
                item.is_manually_moved = True
                item.data.is_manually_moved = True
            
        self.scene.update()

    def load_high_res(self, graph_item):
        item_data = graph_item.data
        if item_data.is_high_res_loading or item_data.high_res_thumbnail:
            return
        item_data.is_high_res_loading = True
        h_size = getattr(self, "high_res_size", 512)
        worker = ThumbnailWorker(item_data, size=h_size)
        worker.signals.finished.connect(self._on_high_res_loaded)
        self.thread_pool.start(worker)

    def _on_high_res_loaded(self, item_data, image):
        if image:
            item_data.high_res_thumbnail = QPixmap.fromImage(image)
            item_data.high_res_failed = False
        else:
            item_data.high_res_thumbnail = None
            item_data.high_res_failed = True
        item_data.is_high_res_loading = False
        if item_data in self.item_to_thumb:
            self.item_to_thumb[item_data].on_high_res_ready()

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
        
        target_size = 72  # 3x the original 24pt default
        
        note = TextNoteItem(scene_pos)
        # Apply initial font size
        font = note.text_item.font()
        font.setPointSize(target_size)
        note.text_item.setFont(font)
        
        # Calculate reasonable initial size based on font
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance("New Note") + 100
        text_h = fm.height() + 100
        note.width = text_w
        note.height = text_h
        note.text_item.setTextWidth(text_w - 40)
        
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

    def get_main_window(self):
        curr = self
        while curr:
            if hasattr(curr, "config") and hasattr(curr, "save_config"):
                return curr
            parent = None
            if hasattr(curr, "parentWidget") and curr.parentWidget():
                parent = curr.parentWidget()
            elif hasattr(curr, "parent") and callable(curr.parent) and curr.parent():
                parent = curr.parent()
            curr = parent
        return None

    def get_config(self):
        win = self.get_main_window()
        if win:
            return win.config
        return {}

    def save_config_if_possible(self):
        win = self.get_main_window()
        if win:
            win.save_config()

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

    def _get_green_arrow_icon(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#4caf50"), 3))
        painter.drawLine(4, 3, 11, 8)
        painter.drawLine(11, 8, 4, 13)
        painter.end()
        return QIcon(pixmap)
