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
                         QHelpEvent, QTextCharFormat, QTextCursor, QPainterPath)
from PySide6.QtWidgets import QToolTip

class TextNoteItem(QGraphicsObject):
    moving_started = Signal()
    moving_finished = Signal()
    
    def __init__(self, pos, text="New Note"):
        super().__init__()
        self.setPos(pos)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(1000)
        self.uuid = str(uuid.uuid4())
        self.setCacheMode(QGraphicsItem.NoCache) # Prevent clipping artifacts
        
        self.text_item = QGraphicsTextItem(self)
        self.text_item.setDefaultTextColor(QColor("#e0e0e0"))
        # Standard default font
        font = QFont("Arial", 24)
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
            self.prepareGeometryChange()
            
            if self._resize_mode in ["bottom_right", "right"]:
                self.width = max(100, self._resize_start_size[0] + delta.x())
            if self._resize_mode in ["bottom_right", "bottom"]:
                self.height = max(50, self._resize_start_size[1] + delta.y())
                
            self.text_item.setTextWidth(self.width - 20)
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_mode = None
        if event.button() == Qt.LeftButton:
            self.moving_finished.emit()
        super().mouseReleaseEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        self.text_item.setAcceptedMouseButtons(Qt.LeftButton)
        self.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.text_item.setFocus()
        # Select all text on double click
        cursor = self.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.text_item.setTextCursor(cursor)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)
        # Clear selection when losing focus
        cursor = self.text_item.textCursor()
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        super().focusOutEvent(event)

        self.text_item.setTextCursor(cursor)
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
from utils import generate_thumbnail_image

class ThumbnailItem(QGraphicsObject):
    def __init__(self, item_data):
        super().__init__()
        self.data = item_data
        self.size = 150
        self.font_size = 10
        self.is_manually_moved = False
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
        if not templates or not model:
            return
            
        cat = self.data.category.lower()
        key = "other"
        if "sequence" in cat: key = "sequences"
        elif "still" in cat: key = "stills"
        elif "video" in cat: key = "videos"
        
        template = templates.get(f"item_info_{key}", "")
        if template:
            expanded = model.expand_tokens(template, self.data)
            self.setToolTip(expanded)
        else:
            self.setToolTip("")


    def boundingRect(self):
        # 1. Calculate aspect ratio
        w = self.data.metadata.get("width", 1)
        h = self.data.metadata.get("height", 1)
        try:
            fw = float(w) if w is not None else 1.0
            fh = float(h) if h is not None else 1.0
            aspect = fw / fh if fh > 0 else 1.0
        except (ValueError, TypeError):
            aspect = 1.0
            
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
            w = self.data.metadata.get("width", 1)
            h = self.data.metadata.get("height", 1)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
            
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
            painter.fillRect(thumb_rect, QColor("#333333")) # Lighter gray for visibility
        else:
            painter.drawPixmap(thumb_rect, pixmap, QRectF(pixmap.rect()))

        # 3. Draw Borders (always)
        base_w = 2
        if lod < 0.3:
            base_w = 6
        elif lod < 0.6:
            base_w = 4
            
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
                self.cached_label = f"{self.data.label} (v{self.data.version})"
            
            t_opt = QTextOption(Qt.AlignLeft | Qt.AlignTop)
            t_opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            painter.drawText(label_rect, self.cached_label, t_opt)
        
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
            # If moved by user (interaction)
            if self.scene().mouseGrabberItem() == self:
                # Only hide editor if this is a real drag, not a tiny wiggle during dblclick
                new_pos = value.toPointF() if hasattr(value, 'toPointF') else value
                if (new_pos - self.pos()).manhattanLength() > 2:
                    for view in self.scene().views():
                        area = view.parent()
                        if hasattr(area, 'inline_editor') and area.inline_editor.isVisible():
                            # Use the proper finish method if possible
                            if hasattr(area, '_on_inline_editing_finished'):
                                area._on_inline_editing_finished()
                            else:
                                area.inline_editor.hide()

                self.is_manually_moved = True
                self.data.position = (new_pos.x(), new_pos.y())

        return super().itemChange(change, value)

class BackdropItem(QGraphicsObject):
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
        self.update()

    def boundingRect(self):
        # Margin to avoid clipping borders
        return QRectF(-2, -2, self.width + 4, self.height + 4)

    def shape(self):
        path = QPainterPath()
        # Top bar is interactive
        path.addRect(0, 0, self.width, self.top_bar_height)
        # Corners are interactive for resizing
        cs = self.corner_size
        path.addRect(0, 0, cs, cs) # TL
        path.addRect(self.width - cs, 0, cs, cs) # TR
        path.addRect(0, self.height - cs, cs, cs) # BL
        path.addRect(self.width - cs, self.height - cs, cs, cs) # BR
        # Border is interactive? 
        # Actually, let's keep it simple: Top bar + Corners.
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
        
        # 3. Top Bar (Name area)
        top_bar_rect = QRectF(0, 0, self.width, self.top_bar_height)
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
        
        cs = self.corner_size
        # Top-left
        painter.drawPolygon([QPointF(0,0), QPointF(cs, 0), QPointF(0, cs)])
        # Top-right
        painter.drawPolygon([QPointF(self.width,0), QPointF(self.width - cs, 0), QPointF(self.width, cs)])
        # Bottom-left
        painter.drawPolygon([QPointF(0, self.height), QPointF(cs, self.height), QPointF(0, self.height - cs)])
        # Bottom-right
        painter.drawPolygon([QPointF(self.width, self.height), QPointF(self.width - cs, self.height), QPointF(self.width, self.height - cs)])
        
        painter.restore()

    def mousePressEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        cs = self.corner_size
        
        # Check corners first
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
            
        # Check top bar
        if y < self.top_bar_height:
            self._is_dragging_top_bar = True
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            # Find all items inside the backdrop to move with it
            self._content_offsets = {}
            if not (event.modifiers() & Qt.ControlModifier):
                backdrop_rect = self.sceneBoundingRect()
                for item in self.scene().items(backdrop_rect):
                    if item == self or item.parentItem() or item.isSelected(): continue
                    # Only move top-level items that are truly "inside" (center point)
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
        self._content_offsets = {}
        self.setFlag(QGraphicsItem.ItemIsMovable, True) # Restore for selection/other uses
        super().mouseReleaseEvent(event)

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
        image = generate_thumbnail_image(self.item_data.file_path, self.size)
        self.signals.finished.emit(self.item_data, image)

class SequenceRenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Rename")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.prefix = QLineEdit("img")
        self.counter_start = QSpinBox()
        self.counter_start.setRange(0, 999999)
        self.counter_start.setValue(1)
        
        self.counter_zeroes = QSpinBox()
        self.counter_zeroes.setRange(1, 10)
        self.counter_zeroes.setValue(3)
        
        self.suffix = QLineEdit("")
        
        form.addRow("Prefix:", self.prefix)
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

    def get_values(self):
        return {
            "prefix": self.prefix.text().strip(),
            "start": self.counter_start.value(),
            "zeroes": self.counter_zeroes.value(),
            "suffix": self.suffix.text().strip()
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
        init_sort = initial_values.get("sort_by", "File Name") if initial_values else "File Name"
        init_reverse = initial_values.get("reverse", False) if initial_values else False

        # Sort Row
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort By:"))
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["File Name", "Label", "Version", "File Size", "Width", "Height", "Age"])
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
            layout.addLayout(col_layout)
            
        # Gap (Horizontal) - only for horizontal or grid
        self.slider_gap_h = None
        if mode in ["horizontal", "grid"]:
            gap_h_layout = QHBoxLayout()
            gap_h_label = "Gap:" if mode != "grid" else "Horizontal Gap:"
            gap_h_layout.addWidget(QLabel(gap_h_label))
            self.slider_gap_h = QSlider(Qt.Horizontal)
            self.slider_gap_h.setRange(0, 1000)
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
            "gap_h": self.slider_gap_h.value() if self.slider_gap_h else 0,
            "gap_v": self.slider_gap_v.value() if self.slider_gap_v else 0,
            "cols": self.slider_cols.value() if self.slider_cols else 1,
            "sort_by": self.combo_sort.currentText(),
            "reverse": self.chk_reverse.isChecked()
        }
        return vals

class ThumbnailArea(QWidget):
    tag_toggle_requested = Signal()
    label_action_requested = Signal(str, object)
    maximize_toggle_requested = Signal()
    paste_requested = Signal()
    queue_requested = Signal()
    scene_items_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State Initialization
        self.item_to_thumb = {}
        self._last_arrange_vals = {
            "cols": 10, "gap_h": 50, "gap_v": 50,
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
        self.tooltip_templates = {}
        
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
        
        self.slider_cols = QSpinBox()
        self.slider_cols.setRange(5, 100)
        self.slider_cols.setValue(self._last_arrange_vals["cols"])
        self.slider_cols.valueChanged.connect(self._on_spinner_changed)

        self.slider_text_size = QSlider(Qt.Horizontal)
        self.slider_text_size.setRange(4, 64)
        self.slider_text_size.setValue(10)
        self.slider_text_size.setFixedWidth(100)
        self.slider_text_size.valueChanged.connect(self.update_font_size)
        self.slider_thumb_size = QSlider(Qt.Horizontal)
        self.slider_thumb_size.setRange(20, 2048)
        self.slider_thumb_size.setValue(150)
        self.slider_thumb_size.setFixedWidth(100)
        self.slider_thumb_size.valueChanged.connect(self.update_thumb_size)

        self.btn_tag_filter = QPushButton("Filter: All")
        self.btn_tag_filter.clicked.connect(self._cycle_tag_filter)
        self._tag_filter_state = "all" # all, tagged, untagged

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
        self.controls_layout.addWidget(QLabel("Cols:"))
        self.controls_layout.addWidget(self.slider_cols)
        self.controls_layout.addWidget(self.btn_show_text)
        add_v_line(self.controls_layout)
        self.controls_layout.addWidget(QLabel("Text:"))
        self.controls_layout.addWidget(self.slider_text_size)
        self.controls_layout.addWidget(QLabel("Thumb:"))
        self.controls_layout.addWidget(self.slider_thumb_size)
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

        # Graphics View
        self.view = QGraphicsView()
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        
        # Use OpenGL for performance
        self.gl_widget = QOpenGLWidget()
        self.view.setViewport(self.gl_widget)
        
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.BspTreeIndex)
        self.scene.setSceneRect(-50000, -50000, 100000, 100000)
        self.view.setScene(self.scene)
        self.scene.show_labels = True
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.view.setBackgroundBrush(QColor("#1e1e1e"))
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
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
            
            for i, thumb in enumerate(sorted_thumbs):
                counter = start + i
                new_label = f"{prefix}{counter:0{zeroes}d}{suffix}"
                
                try:
                    row = self.model.items.index(thumb.data)
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

    def _on_scene_selection_changed(self):
        self._has_selection = bool(self.scene.selectedItems())
        self.scene.update()
        self._update_note_toolbar()

    def _update_note_toolbar(self):
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

    def add_items(self, items=None):
        """Initial populate or full reset."""
        self.scene.clear()
        self.item_to_thumb.clear()
        
        if items is None and self.model:
            items = self.model.items
            
        if not items: return

        # Cache current sizes to apply to new items
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()

        for item_data in items:
            thumb = ThumbnailItem(item_data)
            thumb.size = thumb_size
            thumb.font_size = font_size
            thumb.update_tooltip(self.tooltip_templates, self.model)
            self.scene.addItem(thumb)
            self.item_to_thumb[item_data] = thumb
            
        self.rearrange_items()
        self.frame_all()

    def _on_rows_inserted(self, parent, first, last):
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()
        
        for row in range(first, last + 1):
            item_data = self.model.items[row]
            if item_data not in self.item_to_thumb:
                thumb = ThumbnailItem(item_data)
                thumb.size = thumb_size
                thumb.font_size = font_size
                thumb.update_tooltip(self.tooltip_templates, self.model)
                self.scene.addItem(thumb)
                self.item_to_thumb[item_data] = thumb
        self.rearrange_items()

    def _on_rows_removed(self, parent, first, last):
        # Items are still in the model at this point (aboutToBeRemoved)
        for row in range(first, last + 1):
            item_data = self.model.items[row]
            if item_data in self.item_to_thumb:
                thumb = self.item_to_thumb.pop(item_data)
                self.scene.removeItem(thumb)
        self.rearrange_items()

    def _on_data_changed(self, top_left, bottom_right, roles=None):
        # Refresh the labels of affected items using the mapping
        for row in range(top_left.row(), bottom_right.row() + 1):
            if row < len(self.model.items):
                item_data = self.model.items[row]
                if item_data in self.item_to_thumb:
                    thumb = self.item_to_thumb[item_data]
                    thumb.cached_label = ""
                    thumb.update_tooltip(self.tooltip_templates, self.model)
                    thumb.update()

    def rearrange_items(self, age_filter=None, search_text=None):
        if not self.item_to_thumb or not self.model: return
        
        if age_filter is not None:
            self._last_age_filter = age_filter
        if search_text is not None:
            self._last_search_text = search_text
            
        cols = self.slider_cols.value()
        
        age_enabled, age_val = self._last_age_filter
        search_term = self._last_search_text

        visible_items = []
        for item_data in self.model.items:
            item = self.item_to_thumb.get(item_data)
            if not item: continue
            
            # Visibility logic
            is_tagged = item_data.is_tagged
            item_abs = os.path.normpath(os.path.abspath(item_data.file_path))
            filter_abs = os.path.normpath(os.path.abspath(self._path_filter))
            in_path = not self._path_filter or (item_abs == filter_abs or item_abs.startswith(filter_abs + os.sep))
            
            show_by_tag = True
            if self._tag_filter_state == "tagged": show_by_tag = is_tagged
            elif self._tag_filter_state == "untagged": show_by_tag = not is_tagged
            
            is_young_enough = not age_enabled or (item_data.age_minutes <= age_val)
            matches_search = not search_term or search_term in item_data.label.lower()
            
            if show_by_tag and in_path and is_young_enough and matches_search:
                item.show()
                visible_items.append(item)
            else:
                item.hide()

        if not visible_items:
            return
            
        # Use last arrangement values but current column count
        vals = self._last_arrange_vals.copy()
        vals["cols"] = self.slider_cols.value()
        
        # Use (0,0) as anchor for the main layout
        self._apply_arrangement(visible_items, "grid", vals, anchor=(0, 0))

    def set_path_filter(self, path):
        self._path_filter = path
        self.rearrange_items()

    def _cycle_tag_filter(self):
        states = ["all", "tagged", "untagged"]
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

    def update_thumb_size(self):
        new_size = self.slider_thumb_size.value()
        for item in self.item_to_thumb.values():
            item.prepareGeometryChange()
            item.size = new_size
            item.update()

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

    def _on_spinner_changed(self, value):
        self.rearrange_items()

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
        if event.type() == QEvent.Enter:
            self.view.setFocus()
            
        if event.type() == QEvent.Wheel:
            if source in (self.view, self.view.viewport()):
                self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                angle = event.angleDelta().y()
                factor = 1.15 if angle > 0 else 1 / 1.15
                self.view.scale(factor, factor)
                self.update_zoom_indicator()
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
                    return True

        if event.type() == QEvent.Leave:
            self._tooltip_timer.stop()
            QToolTip.hideText()

        if event.type() == QEvent.MouseButtonPress:
            self._tooltip_timer.stop()
            QToolTip.hideText()
            if source is self.view.viewport():
                self._last_click_scene_pos = self.view.mapToScene(event.pos())
                
                is_middle = event.button() == Qt.MiddleButton
                is_ctrl_left = event.button() == Qt.LeftButton and (event.modifiers() & Qt.ControlModifier)
                
                if is_middle or is_ctrl_left:
                    self._is_panning = True
                    self._last_pan_pos = event.pos()
                    self.view.viewport().setCursor(Qt.ClosedHandCursor)
                    return True
                    
                if not self.view.itemAt(event.pos()):
                    self.scene.clearSelection()

        if event.type() == QEvent.MouseButtonRelease:
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

                    # Slightly longer delay to ensure the dblclick sequence is fully processed
                    QTimer.singleShot(50, lambda: self._start_inline_rename(item))
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

            # Global shortcuts (only when editor is NOT active)
            if event.key() == Qt.Key_Space:
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
            elif event.key() == Qt.Key_N and (event.modifiers() & Qt.ControlModifier):
                if self.view.underMouse():
                    self.add_text_note()
                    return True
            elif event.key() == Qt.Key_N and (event.modifiers() & Qt.AltModifier):
                if self.view.underMouse():
                    self.add_backdrop()
                    return True
                if self.view.underMouse():
                    self.delete_selected_notes()
                    self.scene_items_changed.emit()
                    return True
        
        if event.type() == QEvent.Gesture:
            return self.gestureEvent(event)
            
        return super().eventFilter(source, event)

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
                for i, m_item in enumerate(self.model.items):
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
        for item_data in self.model.items:
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
        menu = QMenu(self)
        
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

        menu.addSeparator()
        
        tag_action = QAction("Tag/Untag Selected", self)
        tag_action.triggered.connect(self.tag_toggle_requested.emit)
        menu.addAction(tag_action)
        
        menu.addSeparator()
        action_seq_rename = QAction("Sequence Rename...", self)
        action_seq_rename.triggered.connect(self._on_sequence_rename)
        # Enable only if something is selected
        action_seq_rename.setEnabled(bool(self.scene.selectedItems()))
        menu.addAction(action_seq_rename)
        
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
        arrange_action.triggered.connect(lambda: self._on_arrange("grid"))
        menu.addAction(arrange_action)
        
        menu.exec(event.globalPos())

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
            for item_data in self.model.items:
                item = self.item_to_thumb.get(item_data)
                if item and item.isVisible():
                    target_items.append(item)
                    
        if not target_items: return
        
        # Store initial positions for revert
        initial_pos = {item: item.pos() for item in target_items}
        # Calculate top-left anchor point once
        anchor_x = min(p.x() for p in initial_pos.values())
        anchor_y = min(p.y() for p in initial_pos.values())
        anchor = (anchor_x, anchor_y)
        
        # 2. Show dialog
        self._arrange_dialog = ArrangeDialog(mode, self._last_arrange_vals, self)
        
        # Connect live updates
        self._arrange_dialog.valuesChanged.connect(lambda vals: self._apply_arrangement(target_items, mode, vals, anchor))
        
        def finalize():
            vals = self._arrange_dialog.get_values()
            self._apply_arrangement(target_items, mode, vals, anchor)
            self._last_arrange_vals = vals # Save for next time
            self._arrange_dialog = None
            
        def revert():
            for item, pos in initial_pos.items():
                item.setPos(pos)
                item.data.position = (pos.x(), pos.y())
            self.scene.update()
            self._arrange_dialog = None
            
        self._arrange_dialog.accepted.connect(finalize)
        self._arrange_dialog.rejected.connect(revert)
        
        # Initial preview
        self._apply_arrangement(target_items, mode, self._arrange_dialog.get_values(), anchor)
        
        self._arrange_dialog.show()
        self._arrange_dialog.raise_()
        self._arrange_dialog.activateWindow()

    def _apply_arrangement(self, items, mode, vals, anchor=None):
        if not items: return
        
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
        
        thumb_size = self.slider_thumb_size.value()
        show_text = self.btn_show_text.isChecked()
        font_size = self.slider_text_size.value()
        line_height = font_size * 1.5
        label_area = (line_height * 3.5) + 10 if show_text else 0

        # Width is always thumb_size + 20 (from boundingRect)
        item_w = thumb_size + 20

        def get_item_h(thumb):
            w = thumb.data.metadata.get("width", 1)
            h = thumb.data.metadata.get("height", 1)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
            # Height matches boundingRect: thumb_h + 20 + label_area
            return (thumb_size / aspect) + 20 + label_area

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

        current_y_offset = 0
        for i, item in enumerate(items):
            h = get_item_h(item)
            
            if mode == "horizontal":
                new_x = start_x + i * (item_w + gap_h)
                new_y = start_y
            elif mode == "vertical":
                new_x = start_x
                new_y = start_y + current_y_offset
                current_y_offset += h + gap_v
            else: # grid
                row = i // cols
                col = i % cols
                new_x = start_x + col * (item_w + gap_h)
                y_pos = sum(row_heights[:row]) + (row * gap_v)
                new_y = start_y + y_pos
            
            item.setPos(new_x, new_y)
            item.is_manually_moved = True
            item.data.position = (new_x, new_y)
            
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

    def get_scene_item_summaries(self):
        res = []
        for item in self.scene.items():
            if isinstance(item, TextNoteItem):
                text = item.text_item.toPlainText()
                res.append({"type": "note", "name": text[:20], "label": "Note", "id": item.uuid, "full_text": text})
            elif isinstance(item, BackdropItem):
                res.append({"type": "backdrop", "name": item.name or item.label, "label": "Backdrop", "id": item.uuid})
        return res

    def add_text_note(self, pos=None):
        # Create at last click position or center of view
        if hasattr(self, "_last_click_scene_pos"):
            scene_pos = self._last_click_scene_pos
        else:
            v_rect = self.view.viewport().rect()
            center_view = v_rect.center()
            scene_pos = self.view.mapToScene(center_view)
        
        target_size = 200
        
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
        
    def delete_selected_notes(self):
        selected = self.scene.selectedItems()
        to_remove = [it for it in selected if isinstance(it, (TextNoteItem, BackdropItem))]
        if not to_remove: return
        
        for it in to_remove:
            self.scene.removeItem(it)
        self.scene_items_changed.emit()
        self._update_note_toolbar()

    def add_backdrop(self):
        # 1. Calculate geometry
        selected = self.scene.selectedItems()
        # Filter for top-level visible items (ThumbnailItem, TextNoteItem)
        groupable = [it for it in selected if not it.parentItem()]
        
        margin = 250
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
            else:
                temp_item.set_data(vals)
        
        dialog.applyRequested.connect(apply_to_temp)
        
        if dialog.exec():
            data = dialog.get_values()
            if not temp_item:
                backdrop = BackdropItem(rect, data)
                self.scene.addItem(backdrop)
                self.scene_items_changed.emit()
            else:
                backdrop = temp_item
                backdrop.set_data(data)
            
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
            self.scene.removeItem(it)
