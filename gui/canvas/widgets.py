"""Toolbars and dialogs of the canvas (notes, drawing, backdrops, arrange, sequence rename)."""
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
        from gui.canvas.scene_items import NOTE_DEFAULT_FONT_PT
        self.spin_size.setValue(NOTE_DEFAULT_FONT_PT)
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
            fmt = QTextCharFormat()
            fmt.setFontPointSize(size)
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
                item.text_item.setTextCursor(cursor)
            else:
                # No selection: resize the whole note without leaving it all selected
                whole = QTextCursor(item.text_item.document())
                whole.select(QTextCursor.SelectionType.Document)
                whole.mergeCharFormat(fmt)
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
