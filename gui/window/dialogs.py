"""Small dialogs and the help overlay used by the main window."""
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


class RenameDialog(QDialog):
    def __init__(self, initial_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename Label")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        
        self.edit = QLineEdit(initial_text)
        self.edit.selectAll()
        layout.addWidget(QLabel("New label name:"))
        layout.addWidget(self.edit)
        
        # Style hint
        self.edit.setMinimumHeight(30)
        self.edit.setStyleSheet("font-size: 14px; padding: 5px;")
        
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Rename")
        self.btn_ok.setObjectName("IngestButton")
        self.btn_ok.setMinimumHeight(35)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(35)
        self.btn_cancel.clicked.connect(self.reject)
        
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)
        
    def get_text(self):
        return self.edit.text().strip()


class HelpContentWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(710)
        self.setFixedHeight(1400) # Extra room for generous spacing
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        painter.setBrush(QColor(25, 25, 25, 255))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())
        
        def draw_shortcut(p, rect, key, desc, y_off):
            f = p.font()
            f.setBold(True)
            f.setPointSize(9)
            p.setFont(f)
            p.setPen(QColor(180, 180, 255))
            p.drawText(rect.adjusted(0, y_off, 0, 0), Qt.AlignLeft, key)
            
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor(180, 180, 180))
            p.drawText(rect.adjusted(160, y_off, 0, 0), Qt.AlignLeft, desc)
            return y_off + 35 # More vertical spacing (was 25)

        col1_rect = QRect(40, 20, 310, 1300)
        col2_rect = QRect(370, 20, 310, 1300)
        
        font = painter.font()
        
        # Col 1
        y = 20
        painter.setPen(QColor(100, 100, 100))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(col1_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "GENERAL")
        y += 30
        y = draw_shortcut(painter, col1_rect, "Ctrl + A", "Select All (contextual)", y)
        y = draw_shortcut(painter, col1_rect, "Ctrl + D", "Toggle Enable/Disable selected", y)
        y = draw_shortcut(painter, col1_rect, "F2", "Rename selected item", y)
        y = draw_shortcut(painter, col1_rect, "Space", "Toggle Maximize view", y)
        y = draw_shortcut(painter, col1_rect, "Esc", "Close this guide", y)
        
        y += 25
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(col1_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "THUMBNAILS")
        y += 30
        y = draw_shortcut(painter, col1_rect, "+ / =", "Zoom In", y)
        y = draw_shortcut(painter, col1_rect, "-", "Zoom Out", y)
        y = draw_shortcut(painter, col1_rect, "Z", "Reset Zoom", y)
        y = draw_shortcut(painter, col1_rect, "F", "Focus Selection", y)
        y = draw_shortcut(painter, col1_rect, "Alt + A", "Arrange items", y)
        y = draw_shortcut(painter, col1_rect, "Ctrl+Wheel", "Zoom at cursor", y)

        # Col 2
        y = 20
        painter.setPen(QColor(100, 100, 100))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(col2_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "SPREADSHEET")
        y += 30
        y = draw_shortcut(painter, col2_rect, "Dbl Click", "Edit cell", y)
        y = draw_shortcut(painter, col2_rect, "Enter", "Submit changes", y)
        y = draw_shortcut(painter, col2_rect, "Esc", "Cancel edit", y)
        
        y += 25
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(col2_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "PIPELINE")
        y += 30
        y = draw_shortcut(painter, col2_rect, "Right Click", "Assignment menu", y)
        y = draw_shortcut(painter, col2_rect, "Header Click", "Sort column", y)
        
        y += 25
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(col2_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "NAVIGATION")
        y += 30
        y = draw_shortcut(painter, col2_rect, "Click Folder", "Filter by folder", y)

        # Preset Keywords (Full Width)
        y_keys = 520 # Lowered due to column spacing
        full_rect = QRect(40, y_keys, 630, 900)
        y = 0
        painter.setPen(QColor(100, 100, 100))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(full_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "PRESET VARIANT KEYWORDS")
        y += 40
        
        y = draw_shortcut(painter, full_rect, "{product_type}", "Product Type from the matched preset", y)
        y = draw_shortcut(painter, full_rect, "{task_name}", "Task name from assigned AYON path", y)
        y = draw_shortcut(painter, full_rect, "{ayon_folder_path}", "AYON path excluding the task", y)
        y = draw_shortcut(painter, full_rect, "{label}", "Current label (including edits)", y)
        y = draw_shortcut(painter, full_rect, "{variant_parsed}", "Variant string parsed via AutoAssign regex", y)
        y = draw_shortcut(painter, full_rect, "{variant}", "Effective variant (preset template evaluated)", y)
        y = draw_shortcut(painter, full_rect, "{filename}", "Full path (hashes for sequences)", y)
        y = draw_shortcut(painter, full_rect, "{file_name}", "Base name without extension", y)
        y = draw_shortcut(painter, full_rect, "{extension}", "File extension without dot", y)
        y = draw_shortcut(painter, full_rect, "{repre}", "Representation from preset", y)
        y = draw_shortcut(painter, full_rect, "{head} / {tail}", "Handle Start / End from preset", y)
        y = draw_shortcut(painter, full_rect, "{slate_exists}", "True/False based on preset", y)
        y = draw_shortcut(painter, full_rect, "{fps}", "FPS from preset / metadata", y)
        y = draw_shortcut(painter, full_rect, "{fps_int}", "FPS rounded to nearest integer", y)
        y = draw_shortcut(painter, full_rect, "{version}", "Current version from spreadsheet", y)
        y = draw_shortcut(painter, full_rect, "{ocio}", "OCIO config absolute path from preferences", y)
        y = draw_shortcut(painter, full_rect, "{metadata.width}", "Source image width (integer)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.height}", "Source image height (integer)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.timecode}", "Technical timecode (from file)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.start_from_tc}", "Calculated integer start frame from TC", y)
        y = draw_shortcut(painter, full_rect, "{metadata.nb_frames}", "Total frame count (Duration * FPS)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.duration}", "Total duration in seconds (float)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.framerate}", "Extracted technical framerate (float)", y)
        y = draw_shortcut(painter, full_rect, "{metadata.seq_thumbnail_path}", "Path to the frame used for sequence thumbnail", y)


class HelpOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()
        
        # Main layout for the overlay
        self.overlay_layout = QVBoxLayout(self)
        self.overlay_layout.setContentsMargins(0, 0, 0, 0)
        
        # Semi-transparent background
        self.bg_widget = QWidget()
        self.bg_widget.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.overlay_layout.addWidget(self.bg_widget)
        
        # Center container for the help box
        self.center_layout = QVBoxLayout(self.bg_widget)
        self.center_layout.setContentsMargins(100, 60, 100, 60)
        
        self.box = QWidget()
        self.box.setFixedWidth(750)
        self.box.setStyleSheet("background-color: #191919; border: 1px solid #505050; border-radius: 4px;")
        self.center_layout.addWidget(self.box, 0, Qt.AlignCenter)
        
        self.box_layout = QVBoxLayout(self.box)
        self.box_layout.setContentsMargins(0, 0, 0, 0)
        self.box_layout.setSpacing(0)
        
        # Header
        self.header = QLabel(" INGESTDESKTOP USER GUIDE")
        self.header.setFixedHeight(60)
        self.header.setStyleSheet("""
            background-color: #282828; 
            color: white; 
            font-weight: bold; 
            font-size: 14px; 
            padding-left: 25px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        """)
        self.box_layout.addWidget(self.header)
        
        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        
        self.content = HelpContentWidget()
        self.scroll.setWidget(self.content)
        self.box_layout.addWidget(self.scroll)
        
        # Footer
        self.footer = QLabel("Click anywhere or press ESC to exit")
        self.footer.setFixedHeight(35)
        self.footer.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.footer.setStyleSheet("color: #777777; font-size: 9px; padding-right: 20px; border-top: 1px solid #333333;")
        self.box_layout.addWidget(self.footer)

    def show_help(self):
        # Set height to 80% of main window
        if self.parent():
            parent_h = self.parent().height()
            self.box.setFixedHeight(int(parent_h * 0.8))
            
        self.show()
        self.raise_()
        self.setFocus()

    def hide_help(self):
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_help()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Only hide if clicked on the darkened background, not the box
        if self.box.geometry().contains(event.pos()):
            return
        self.hide_help()


class SearchReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search and Replace Labels")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)
        
        self.search_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        
        layout.addRow("Search for:", self.search_edit)
        layout.addRow("Replace with:", self.replace_edit)
        
        # Style hints
        self.search_edit.setMinimumHeight(30)
        self.replace_edit.setMinimumHeight(30)
        
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Replace All")
        self.btn_ok.setObjectName("IngestButton")
        self.btn_ok.setMinimumHeight(35)
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(35)
        self.btn_cancel.clicked.connect(self.reject)
        
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addRow(btns)
        
    def get_values(self):
        return self.search_edit.text(), self.replace_edit.text()
