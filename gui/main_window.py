import os
import re
import json
import csv
import tempfile
import subprocess
import logging
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, 
                             QPushButton, QMessageBox, QInputDialog, QApplication,
                             QDialog, QLineEdit, QLabel, QHBoxLayout, QPlainTextEdit, QFormLayout, QScrollArea)
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel, QItemSelection, QThread, Signal, QRect
from PySide6.QtGui import QKeySequence, QCursor, QShortcut, QPainter, QColor, QImage, QAction

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
from ayon_client import AyonClient
from utils import evaluate_preset


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
        y = draw_shortcut(painter, full_rect, "{variant}", "Expanded variant string", y)
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

class MainWindow(QMainWindow):
    log_signal = Signal(str, str) # (message, level)

    def __init__(self):
        self._is_initializing = True
        self.current_project_path = None
        super().__init__()
        self.setWindowTitle("IngestDesktop - AYON Pipeline Tool")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        # Load Config and Secrets
        self.secrets = self.load_secrets()
        self.config = self.load_config()

        # Migration: Move API key to secrets if found in config but not in secrets
        if "ayon_api_key" in self.config:
            if "ayon_api_key" not in self.secrets or not self.secrets["ayon_api_key"]:
                self.secrets["ayon_api_key"] = self.config["ayon_api_key"]
                self.save_secrets()
            # We'll remove it from config upon the next save_config call

        # Logic
        self.model = ImageTableModel()
        self.model.product_name_template = self.config.get("product_name", "{label}")
        self.model.product_name_camel = self.config.get("product_name_camel", True)
        self.model.stills_thumb_same = self.config.get("stills_thumb_same", True)
        
        self.csv_preview_model = CSVPreviewModel(self.model, self.config)
        
        # Clean credentials - prioritize secrets
        server_url = self.secrets.get("ayon_server_url", "").strip()
        api_key = self.secrets.get("ayon_api_key", "").strip()
        if not api_key: # Fallback to config during transition
            api_key = self.config.get("ayon_api_key", "").strip()
        
        # Instantiate parameterless to prevent synchronous startup connection blocking the GUI thread.
        # The background ConnectionThread will handle the actual connection asynchronously.
        self.ayon = AyonClient()
        self.ayon_thumb_cache = {}
        self.ayon_thumb_downloading = set()
        self.ayon_thumb_states = {}
        self.load_ayon_thumb_states()
        self._thumb_threads = []
        
        # Configure logging to console
        self.log_signal.connect(self.log_message)
        
        class ConsoleLogHandler(logging.Handler):
            def __init__(self, signal):
                super().__init__()
                self.signal = signal
            def emit(self, record):
                msg = self.format(record)
                level = "info"
                if record.levelno >= logging.ERROR: level = "error"
                elif record.levelno >= logging.WARNING: level = "warning"
                self.signal.emit(msg, level)

        self.console_handler = ConsoleLogHandler(self.log_signal)
        self.console_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        logging.getLogger().addHandler(self.console_handler)
        logging.getLogger().setLevel(logging.INFO)

        self._is_maximized = False
        self._last_h_state = None
        self._last_v_state = None
        
        # Filter State
        self._age_filter_enabled = False
        self._age_filter_value = 0
        self._age_filter_units = "minutes"
        self._search_filter_text = ""
        self._selection_lock = False
        
        # Queue Workers
        self._conv_worker = None
        self._review_worker = None
        self._queue_dialog = None

        # UI Components
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        self.top_bar = TopBar(self)
        self.top_bar.setObjectName("TopBar")
        self.top_bar.folder_selected.connect(self.start_scan)
        self.top_bar.prefs_requested.connect(self.show_preferences)
        self.top_bar.rescan_requested.connect(self.rescan_current)
        self.top_bar.load_preset_requested.connect(self._on_preset_changed)
        self.main_layout.addWidget(self.top_bar, 0)
        self.main_layout.addSpacing(5)

        # Main Splitter (Left, Center, Right)
        self.h_splitter = QSplitter(Qt.Horizontal)
        
        # 2. Left Panel (AYON)
        self.ayon_panel = AyonPanel(self)
        self.ayon_panel.project_changed.connect(self._on_project_changed)
        self.ayon_panel.task_selected.connect(self._on_ayon_task_selected)
        self.ayon_panel.product_double_clicked.connect(self._on_ayon_product_selected)
        self.ayon_panel.unassign_requested.connect(self._on_ayon_unassign)
        self.ayon_panel.select_assigned_requested.connect(self._on_ayon_select_assigned)
        self.ayon_panel.clear_all_requested.connect(self._on_ayon_clear_all)
        self.ayon_panel.auto_assign_requested.connect(self.perform_auto_assign)
        self.ayon_panel.btn_refresh.clicked.connect(self.refresh_ayon)
        self.ayon_panel.info_requested.connect(self._on_ayon_info_requested)
        self.ayon_panel.representations_requested.connect(self._on_ayon_representations_requested)
        self.ayon_panel.show_thumbs_toggled.connect(self._on_show_thumbs_toggled)
        self.h_splitter.addWidget(self.ayon_panel)

        # 3. Center Area (Thumbnails + Spreadsheet)
        self.v_splitter = QSplitter(Qt.Vertical)
        
        self.thumb_area = ThumbnailArea(self)
        self.thumb_area.setModel(self.model)
        self.thumb_area.tag_toggle_requested.connect(self._on_tag_selection)
        self.thumb_area.label_action_requested.connect(self._on_label_action)
        self.thumb_area.maximize_toggle_requested.connect(lambda: self.toggle_maximize("thumbs"))
        self.thumb_area.paste_requested.connect(self.perform_paste_image)
        self.thumb_area.queue_requested.connect(self.show_queue_dialog)
        self.thumb_area.scene_items_changed.connect(self._sync_scene_items_to_filter)
        self.thumb_area.change_version_requested.connect(self.change_version_stack_picked_version)
        self.v_splitter.addWidget(self.thumb_area)
        
        self.spreadsheet = SpreadsheetPanel(self)
        self.spreadsheet.set_model(self.model)
        self.spreadsheet.set_csv_model(self.csv_preview_model)
        self.spreadsheet.btn_tag_sel.clicked.connect(self._on_tag_selection)
        self.spreadsheet.maximize_toggle_requested.connect(lambda: self.toggle_maximize("spreadsheet"))
        self.spreadsheet.version_collision_check_clicked.connect(self.perform_version_collision_check)
        self.spreadsheet.label_action_requested.connect(self._on_label_action)
        self.spreadsheet.add_comment_requested.connect(self._on_add_comment)
        self.spreadsheet.check_duplicates_clicked.connect(self.perform_duplicate_check)
        self.v_splitter.addWidget(self.spreadsheet)
        
        # Connect selection after model is set
        self.spreadsheet.selectionChanged.connect(self._sync_selection_to_thumbs)
        self.thumb_area.scene.selectionChanged.connect(self._sync_selection_to_table)
        
        # Sync visuals
        self.model.dataChanged.connect(self._update_ayon_visuals)
        
        self.h_splitter.addWidget(self.v_splitter)

        # 4. Right Panel (Filtering)
        self.filter_panel = FilterPanel(self.model, self)
        self.filter_panel.age_changed.connect(self._on_age_filter_changed)
        self.filter_panel.search_changed.connect(self._on_filter_search_changed)
        self.filter_panel.sequences_toggled.connect(self._on_filter_sequences_toggled)
        self.filter_panel.toggles_changed.connect(self._save_filter_toggles)
        
        # Load initial toggle states
        toggles = self.config.get("filter_toggles", {})
        self.filter_panel.set_toggle_states(toggles)
        self.model.v_stack_enabled = self.filter_panel.btn_v_stack.isChecked()
        
        self._connect_filter_selection_signal()
        self.filter_panel.rename_to_label_requested.connect(self._on_rename_to_label_requested)
        self.filter_panel.delete_scene_items_requested.connect(self._on_filter_delete_scene_items)
        self.filter_panel.edit_scene_item_requested.connect(self._on_filter_edit_scene_item)
        self.filter_panel.move_front_back_requested.connect(self._on_filter_move_front_back)
        self.filter_panel.change_version_requested.connect(self.change_version_stack_picked_version)
        self.h_splitter.addWidget(self.filter_panel)

        self.main_layout.addWidget(self.h_splitter, 1)
        self.main_layout.addSpacing(5)

        # 5. Big Ingest Button row
        ingest_row_layout = QHBoxLayout()
        ingest_row_layout.setSpacing(2)
        
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setObjectName("IngestButton")
        self.btn_export_csv.setMinimumHeight(50)
        self.btn_export_csv.clicked.connect(self.perform_export_csv)
        ingest_row_layout.addWidget(self.btn_export_csv, 1)

        self.btn_publish_local = QPushButton("Publish Ayon Local")
        self.btn_publish_local.setObjectName("IngestButton")
        self.btn_publish_local.setMinimumHeight(50)
        self.btn_publish_local.clicked.connect(self.perform_publish_local)
        ingest_row_layout.addWidget(self.btn_publish_local, 1)

        self.btn_publish_deadline = QPushButton("Process Reviews on Deadline")
        self.btn_publish_deadline.setObjectName("IngestButton")
        self.btn_publish_deadline.setMinimumHeight(50)
        self.btn_publish_deadline.clicked.connect(self.perform_publish_deadline)
        ingest_row_layout.addWidget(self.btn_publish_deadline, 1)
        
        self.btn_toggle_log = QPushButton("Log")
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setFixedSize(50, 50)
        self.btn_toggle_log.setStyleSheet("font-size: 10px; color: #888888;")
        self.btn_toggle_log.clicked.connect(self._toggle_log)
        ingest_row_layout.addWidget(self.btn_toggle_log)
        
        self.main_layout.addLayout(ingest_row_layout)
        
        # 6. Log Console (expandable)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(300)
        self.log_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c; 
                color: #cccccc; 
                font-family: Consolas, monospace; 
                font-size: 27px;
                border: none;
                padding: 0px;
            }
        """)
        self.log_console.hide() # Hide by default for extra compactness
        self.main_layout.addWidget(self.log_console, 0)
        self.main_layout.setContentsMargins(5, 5, 5, 0)
        self.main_layout.setSpacing(0)
        
        # 7. Help Overlay
        self.help_overlay = HelpOverlay(self)
        
        # 8. Menu Bar
        self._init_menu_bar()
        
        # Initial config apply
        self._apply_preferences(self.config, self.secrets, 
                               self.config.get("detect_sequences", True), 
                               self.config.get("seq_thumb_frame", "Middle"),
                               self.config.get("version_regex", ""),
                               json.dumps(self.config.get("extensions", {}), sort_keys=True),
                               show_message=False,
                               save=False)

        # 6. Select All Shortcut
        self.shortcut_all = QShortcut(QKeySequence("Ctrl+A"), self)
        self.shortcut_all.activated.connect(self._on_select_all)
        
        self.shortcut_toggle_enable = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_toggle_enable.setContext(Qt.ApplicationShortcut)
        self.shortcut_toggle_enable.activated.connect(self._on_tag_selection)
        
        self.shortcut_f2 = QShortcut(QKeySequence("F2"), self)
        self.shortcut_f2.setContext(Qt.ApplicationShortcut)
        self.shortcut_f2.activated.connect(self._on_f2_pressed)

        # Final setup
        self.h_splitter.setStretchFactor(1, 2) # Center area gets more space
        self.v_splitter.setStretchFactor(0, 2) # Thumbnails get more space
        
        self.load_initial_data()
        
        # 6. Periodic Age Update
        self.age_timer = QTimer(self)
        self.age_timer.timeout.connect(self._update_ages)
        self.age_timer.start(60000) # 60 seconds

    def _init_menu_bar(self):
        menubar = self.menuBar()
        
        # --- File Menu ---
        file_menu = menubar.addMenu("&File")
        
        act_load_preset = QAction("Load Preset...", self)
        act_load_preset.triggered.connect(self.show_preferences) # Preferences handles presets
        file_menu.addAction(act_load_preset)
        
        act_save_preset = QAction("Save Preset As...", self)
        act_save_preset.triggered.connect(self.save_preset_as)
        file_menu.addAction(act_save_preset)
        
        file_menu.addSeparator()
        
        act_new_project = QAction("&New Project", self)
        act_new_project.triggered.connect(self.perform_new_project)
        file_menu.addAction(act_new_project)
        
        file_menu.addSeparator()
        
        act_open_project = QAction("&Open Project...", self)
        act_open_project.triggered.connect(self.perform_open_project)
        file_menu.addAction(act_open_project)
        
        self.recent_menu = file_menu.addMenu("Open Recent")
        self._update_recent_menu()
        
        file_menu.addSeparator()
        
        act_save_project = QAction("&Save Project...", self)
        act_save_project.setShortcut("Ctrl+S")
        act_save_project.triggered.connect(self.perform_save_project)
        file_menu.addAction(act_save_project)
        
        act_save_project_as = QAction("Save Project As...", self)
        act_save_project_as.triggered.connect(self.perform_save_project_as)
        file_menu.addAction(act_save_project_as)
        
        file_menu.addSeparator()
        
        act_prefs = QAction("&Preferences", self)
        act_prefs.setShortcut("Ctrl+,")
        act_prefs.triggered.connect(self.show_preferences)
        file_menu.addAction(act_prefs)
        
        file_menu.addSeparator()
        
        act_exit = QAction("Exit", self)
        act_exit.setShortcut("Alt+F4")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)
        
        # --- Convert Menu ---
        conv_menu = menubar.addMenu("&Convert")
        
        act_queue = QAction("&Queue...", self)
        act_queue.setShortcut("Ctrl+Q")
        act_queue.triggered.connect(self.show_queue_dialog)
        conv_menu.addAction(act_queue)
        
        conv_menu.addSeparator()
        
        act_conv_thumbs = QAction("Convert Thumbnails", self)
        act_conv_thumbs.triggered.connect(lambda: self.start_conversions(self.model.items))
        conv_menu.addAction(act_conv_thumbs)
        
        act_force_thumbs = QAction("Force Convert Thumbnails", self)
        act_force_thumbs.triggered.connect(lambda: self.start_conversions(self.model.items, force=True))
        conv_menu.addAction(act_force_thumbs)
        
        conv_menu.addSeparator()
        
        act_conv_reviews = QAction("Convert Reviews", self)
        act_conv_reviews.triggered.connect(lambda: self.start_review_conversions(force=True))
        conv_menu.addAction(act_conv_reviews)
        
        act_force_reviews = QAction("Force Convert Reviews", self)
        act_force_reviews.triggered.connect(lambda: self.start_review_conversions(force=True, reset=True))
        conv_menu.addAction(act_force_reviews)
        
        # --- Help Menu ---
        help_menu = menubar.addMenu("&Help")
        
        act_hotkeys = QAction("Hotkeys", self)
        act_hotkeys.setShortcut("F1")
        act_hotkeys.triggered.connect(self.show_help)
        help_menu.addAction(act_hotkeys)
        
        act_keys = QAction("Key List", self)
        act_keys.triggered.connect(self.show_help)
        help_menu.addAction(act_keys)
        
        help_menu.addSeparator()
        
        act_guide = QAction("User Guide", self)
        act_guide.triggered.connect(self.open_help_guide)
        help_menu.addAction(act_guide)
        
        act_reference = QAction("System Reference", self)
        act_reference.triggered.connect(self.open_help_reference)
        help_menu.addAction(act_reference)

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
            "backdrops": []
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
                "comment": item.comment,
                "category": item.category,
                "variant": item.variant,
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
        from gui.thumbnail_area import TextNoteItem, BackdropItem
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

    def load_config(self):
        import time
        print("[Timer] Starting to read preferences...")
        start_time = time.perf_counter()
        config = {}
        
        username = os.environ.get("USERNAME", "default_user")
        
        path = os.path.join("presets", "users", f"{username}.json")
        user_config_loaded = False
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    config = json.load(f)
                print(f"[Prefs] Loaded user-centric preferences for '{username}' from {path}")
                user_config_loaded = True
            except Exception as e:
                print(f"[Prefs] Error loading user preset from {path}: {e}")
                    
        if not user_config_loaded:
            try:
                if os.path.exists("config.json"):
                    with open("config.json", "r") as f:
                        config = json.load(f)
                    print("[Prefs] Loaded default config.json from app root.")
            except Exception as e:
                print(f"Error loading config.json: {e}")
                
        # Inject standard defaults for still & video thumbnail commands if missing
        default_stills_cmd = '{ffmpeg} -i "{filename}" -vf "scale=if(gte(iw\\,ih)\\,min({prefs_highres_thumb_size}\\,iw)\\,-4):if(lt(iw\\,ih)\\,min({prefs_highres_thumb_size}\\,ih)\\,-4)" -y "{prefs_thumb_path}"'
        default_videos_cmd = '{ffmpeg} -ss {metadata.thumbnail_time} -i "{filename}" -vframes 1 -vf "scale=if(gte(iw\\,ih)\\,min({prefs_highres_thumb_size}\\,iw)\\,-4):if(lt(iw\\,ih)\\,min({prefs_highres_thumb_size}\\,ih)\\,-4)" -y "{prefs_thumb_path}"'
        
        if "cmd_stills" not in config:
            config["cmd_stills"] = default_stills_cmd
        if "cmd_videos" not in config:
            config["cmd_videos"] = default_videos_cmd

        self._migrate_keys_to_secrets(config)
        self.load_prefs_elapsed = time.perf_counter() - start_time
        print(f"[Timer] Reading preferences took {self.load_prefs_elapsed:.4f} seconds.")
        return config

    def _migrate_keys_to_secrets(self, config_dict):
        """Move shifted keys from the given config dict to self.secrets and remove them from the dict."""
        shifted_keys = [
            "presets_folder",
            "ayon_server_url",
            "traypublisher_path",
            "ffmpeg_path",
            "ffprobe_path",
            "oiiotool_path",
            "vfxtranscode",
            "ocio_config",
            "ayon_api_key",
            "ingest_log_folder",
            "per_project_logging"
        ]
        migrated = False
        for key in shifted_keys:
            if key in config_dict:
                val = config_dict[key]
                if key not in self.secrets or not self.secrets[key]:
                    self.secrets[key] = val
                    migrated = True
                del config_dict[key]
                migrated = True
        if migrated:
            self.save_secrets()

    def load_secrets(self):
        try:
            if os.path.exists("install.json"):
                with open("install.json", "r") as f:
                    return json.load(f)
            elif os.path.exists("secrets.json"):
                with open("secrets.json", "r") as f:
                    data = json.load(f)
                # Save to install.json
                with open("install.json", "w") as f:
                    json.dump(data, f, indent=4)
                # Remove secrets.json
                try:
                    os.remove("secrets.json")
                except Exception as e:
                    print(f"Error removing secrets.json: {e}")
                return data
        except Exception as e:
            print(f"Error loading install config: {e}")
        return {}

    def load_initial_data(self):
        # Apply label regex
        label_regex = self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$")
        # Upgrade old strict regex if found
        if label_regex == "^[a-zA-Z_-]*$":
            label_regex = "^[a-zA-Z0-9_\\-\\.\\s]*$"
            self.config["label_allowed_chars"] = label_regex
            
        self.model.label_allowed_regex = label_regex
        self.thumb_area.update_label_validator(label_regex)
        
        # Initial UI states
        self._restore_gui_state()
        self.thumb_area.high_res_size = self.config.get("thumb_size", 512)
        
        self.thumb_area.slider_text_size.valueChanged.connect(self._on_text_size_changed)
        self.thumb_area.slider_thumb_size.valueChanged.connect(self._on_thumb_size_changed)

        # Update model presets mapping
        self._update_model_presets()
        
        # Populate and sync quick-preset selection dropdown
        self.update_preset_dropdown()

        # Async AYON Load
        self.refresh_ayon_async()
        
        self._is_initializing = False

        from utils import expand_env_vars
        last_folder = self.config.get("last_source_folder")
        if last_folder:
            last_folder = expand_env_vars(last_folder)
        if not last_folder or not os.path.exists(last_folder):
            last_folder = expand_env_vars(self.config.get("default_scan_folder", ""))
            
        if last_folder and os.path.exists(last_folder):
            self.start_scan(last_folder)
        
        # Initial AYON refresh (handled by refresh_ayon_async above)
        
        # Restore Geometry and Splitter States
        if "geometry" in self.config:
            self.restoreGeometry(bytes.fromhex(self.config["geometry"]))
        if "h_splitter" in self.config:
            self.h_splitter.restoreState(bytes.fromhex(self.config["h_splitter"]))
        if "v_splitter" in self.config:
            self.v_splitter.restoreState(bytes.fromhex(self.config["v_splitter"]))
            
        if hasattr(self, "load_prefs_elapsed"):
            self.log_message(f"Reading preferences took {self.load_prefs_elapsed:.4f} seconds.", "info")

    def start_scan(self, directory):
        self.log_message(f"Starting scan of directory: {directory}")
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()

        self.thumb_area.clear_canvas()
        self.model.clear()
        self.model.source_folder = directory
        self.filter_panel.set_root_folder(directory)
        self.top_bar.set_path(directory)
        
        from utils import expand_env_vars
        self.scanner = ImageScanner(
            directory, 
            recursive=self.top_bar.chk_recursive.isChecked(),
            version_regex=self.config.get("version_regex", r"([._]v|v)(\d+)"),
            thumbnail_size=self.config.get("thumbnail_size", 150),
            age_source=self.config.get("age_source", "Modification Date"),
            detect_sequences=self.config.get("detect_sequences", True),
            seq_thumb_frame=self.config.get("seq_thumb_frame", "Middle"),
            extensions=self.config.get("extensions", {}),
            presets=self.config.get("presets", {}),
            stills_start_frame=self.config.get("stills_start_frame", 1001),
            stills_end_frame=self.config.get("stills_end_frame", 1001),
            video_start_from_tc=self.config.get("video_start_from_tc", False),
            video_start_frame=self.config.get("video_start_frame", 1001),
            ffmpeg_path=expand_env_vars(self.secrets.get("ffmpeg_path", "ffmpeg.exe")),
            ffprobe_path=expand_env_vars(self.secrets.get("ffprobe_path", "ffprobe.exe")),
            oiiotool_path=expand_env_vars(self.secrets.get("oiiotool_path", "oiiotool.exe")),
            ocio_config=expand_env_vars(self.secrets.get("ocio_config", "")),
            stills_thumb_same=self.config.get("stills_thumb_same", True),
            thumb_suffix=self.config.get("thumb_suffix", "_thumbnail"),
            thumb_format=self.config.get("thumb_format", ".jpg"),
            thumb_location=self.config.get("thumb_location", "Relative to Source Folder"),
            thumb_location_path=self.config.get("thumb_location_path", "_thumbs"),
            timeout=self.config.get("timeout_seconds", 6),
            default_fps=self.config.get("default_fps", 25.0),
            use_fps_from_metadata=self.config.get("use_fps_from_metadata", True)
        )
        self.scanner.finished.connect(lambda items: self.log_message(f"Scan complete. Found {len(items)} items. Fetching metadata in background...", "success"))
        self.scanner.finished.connect(self._on_scan_finished)
        self.scanner.item_updated.connect(self.model.update_item)
        self.scanner.status_text.connect(lambda txt: self.statusBar().showMessage(txt))
        self.scanner.log.connect(self.log_message)
        self.scanner.start()
        self._add_to_recent(directory)
        
        # Update config
        self.config["last_source_folder"] = directory
        self.save_config()
        
        # Apply current age filter after scan starts/completes
        # (Though items are added asynchronously, we want the state set)
        self._update_ages()
        self.spreadsheet.update_filtering(age_filter=(self._age_filter_enabled, self._age_filter_value))
        self.thumb_area.rearrange_items(age_filter=(self._age_filter_enabled, self._age_filter_value))

    def _on_scan_finished(self, new_items):
        """Parse tags for all new items before adding them to the model."""
        for item in new_items:
            self._parse_item_tags(item)
        self.model.add_items(new_items)
        self.thumb_area.frame_all()
        
        # Start background conversions
        if self.config.get("run_thumb_after_scan", False):
            self.start_conversions(new_items)
        elif self.config.get("run_review_after_scan", False):
            self.start_review_conversions()
        else:
            self.trigger_ayon_thumbnail_downloads()

    def start_conversions(self, items, force=False, force_review=False):
        """Start background conversion of thumbnails based on preferences."""
        if self._conv_worker and self._conv_worker.isRunning():
            self._conv_worker.cancel()
            # Wait at most 2 seconds for the previous worker to finish its current command cleanup
            if not self._conv_worker.wait(2000):
                self.log_message("Previous conversion worker did not stop in time, starting new one anyway.", "warning")
            
        self._conv_worker = ThumbnailConversionWorker(items, self.model, self.config, force=force, timeout=self.config.get("timeout_seconds", 6))
        self._conv_worker.item_updated.connect(self._on_conversion_item_updated)
        self._conv_worker.log.connect(lambda msg: self.log_message(msg))
        self._conv_worker.status_text.connect(lambda txt: self.statusBar().showMessage(txt))
        self._conv_worker.finished.connect(lambda: self.start_review_conversions(force=force_review))
        self._conv_worker.start()

    def start_review_conversions(self, force=False, reset=False, force_overwrite=False):
        """Triggered after thumbnail conversions are done or scan finished."""
        if not force and not self.config.get("run_review_after_scan", False):
            self.trigger_ayon_thumbnail_downloads()
            return
            
        if self._review_worker and self._review_worker.isRunning():
            return
            
        if reset:
            for it in self.model.items:
                if it.review_status != "do not convert":
                    it.review_status = "waiting"
            self.model.layoutChanged.emit()

        items_to_convert = [it for it in self.model.items if it.review_status == "waiting"]
        if not items_to_convert:
            self.thumb_area.btn_queue.setText("Conversion Queue: done")
            return
            
        self._review_worker = ReviewConversionWorker(self.model.items, self.model, self.config, force_overwrite=force_overwrite)
        self._review_worker.item_updated.connect(self.model.update_item)
        self._review_worker.item_updated.connect(lambda it: self._refresh_tables())
        self._review_worker.progress.connect(self._on_review_progress)
        self._review_worker.status_text.connect(lambda txt: self.statusBar().showMessage(txt))
        self._review_worker.log.connect(lambda msg: self.log_message(msg))
        self._review_worker.finished.connect(self._on_review_finished)
        
        self.thumb_area.btn_queue.setText("Conversion Queue: processing")
        self._review_worker.start()

    def _refresh_tables(self):
        if self._queue_dialog and self._queue_dialog.isVisible():
            self._queue_dialog.table.viewport().update()
            self._queue_dialog.table.update()
        self.spreadsheet.table.viewport().update()
        self.spreadsheet.table.update()

    def _on_review_progress(self, current, total):
        if self._queue_dialog:
            self._queue_dialog.set_queue_status(f"Processing {current}/{total}")
        self._refresh_tables()
            
    def _on_review_finished(self):
        self.thumb_area.btn_queue.setText("Conversion Queue: done")
        if self._queue_dialog:
            self._queue_dialog.set_queue_status("Done")
        self._refresh_tables()
        self.trigger_ayon_thumbnail_downloads()

    def show_queue_dialog(self):
        if not self._queue_dialog:
            self._queue_dialog = ConversionQueueDialog(self.model, self)
            self._queue_dialog.btn_pause.clicked.connect(self._on_queue_pause)
            self._queue_dialog.btn_cancel.clicked.connect(self._on_queue_cancel)
            self._queue_dialog.btn_restart.clicked.connect(self._on_queue_restart)
            self._queue_dialog.convertReviewsRequested.connect(lambda: self.start_review_conversions(force=True, reset=False, force_overwrite=False))
            self._queue_dialog.forceConvertReviewsRequested.connect(lambda: self.start_review_conversions(force=True, reset=True, force_overwrite=True))
            self._queue_dialog.convertThumbsRequested.connect(lambda: self.start_conversions(self.model.items, force=False))
            self._queue_dialog.forceConvertThumbsRequested.connect(lambda: self.start_conversions(self.model.items, force=True))
            
        self._queue_dialog.show()
        self._queue_dialog.raise_()

    def _on_queue_pause(self):
        if self._review_worker:
            is_paused = self._review_worker.toggle_pause()
            self._queue_dialog.set_pause_text(is_paused)
            if is_paused:
                self.thumb_area.btn_queue.setText("Conversion Queue: paused")
            else:
                self.thumb_area.btn_queue.setText("Conversion Queue: processing")

    def _on_queue_cancel(self):
        if self._review_worker:
            self._review_worker.cancel()
            self.thumb_area.btn_queue.setText("Conversion Queue: canceled")
            if self._queue_dialog:
                self._queue_dialog.set_queue_status("Canceled")

    def _on_queue_restart(self):
        # Reset statuses
        for it in self.model.items:
            if it.review_status in ["done", "failed", "processing"]:
                it.review_status = "waiting"
        self.model.layoutChanged.emit()
        self.start_review_conversions()

    def _on_conversion_item_updated(self, item):
        """Reload thumbnail from converted file and update UI."""
        if hasattr(item, "temp_qimage") and item.temp_qimage:
            from PySide6.QtGui import QPixmap
            item.thumbnail = QPixmap.fromImage(item.temp_qimage)
            try:
                delattr(item, "temp_qimage")
            except AttributeError:
                pass
        elif item.conversion_thumb_path:
            # Fallback if somehow temp_qimage is missing
            from utils import generate_thumbnail
            new_thumb = generate_thumbnail(item.conversion_thumb_path, self.config.get("default_thumb_size", 150))
            if new_thumb:
                item.thumbnail = new_thumb
        
        self.model.update_item(item)
        self._refresh_tables()


    def rescan_current(self):
        """Scan for new files in the current directory without clearing existing data."""
        directory = self.top_bar.path_display.text()
        if not directory or not os.path.exists(directory):
            self.log_message("No valid directory to rescan.", "warning")
            return
            
        self.log_message(f"Rescanning directory: {directory}")
        self.model.source_folder = directory
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()
            
        from utils import expand_env_vars
        self.scanner = ImageScanner(
            directory, 
            recursive=self.top_bar.chk_recursive.isChecked(),
            version_regex=self.config.get("version_regex", r"([._]v|v)(\d+)"),
            thumbnail_size=self.config.get("thumbnail_size", 150),
            age_source=self.config.get("age_source", "Modification Date"),
            detect_sequences=self.config.get("detect_sequences", True),
            seq_thumb_frame=self.config.get("seq_thumb_frame", "Middle"),
            extensions=self.config.get("extensions", {}),
            presets=self.config.get("presets", {}),
            stills_start_frame=self.config.get("stills_start_frame", 1001),
            stills_end_frame=self.config.get("stills_end_frame", 1001),
            video_start_from_tc=self.config.get("video_start_from_tc", False),
            video_start_frame=self.config.get("video_start_frame", 1001),
            ffmpeg_path=expand_env_vars(self.secrets.get("ffmpeg_path", "ffmpeg.exe")),
            ffprobe_path=expand_env_vars(self.secrets.get("ffprobe_path", "ffprobe.exe")),
            oiiotool_path=expand_env_vars(self.secrets.get("oiiotool_path", "oiiotool.exe")),
            ocio_config=expand_env_vars(self.secrets.get("ocio_config", "")),
            stills_thumb_same=self.config.get("stills_thumb_same", True),
            thumb_suffix=self.config.get("thumb_suffix", "_thumbnail"),
            thumb_format=self.config.get("thumb_format", ".jpg"),
            thumb_location=self.config.get("thumb_location", "Relative to Source Folder"),
            thumb_location_path=self.config.get("thumb_location_path", "_thumbs"),
            timeout=self.config.get("timeout_seconds", 6),
            default_fps=self.config.get("default_fps", 25.0),
            use_fps_from_metadata=self.config.get("use_fps_from_metadata", True)
        )
        self.scanner.finished.connect(self._on_rescan_finished)
        self.scanner.item_updated.connect(self.model.update_item)
        self.scanner.log.connect(self.log_message)
        self.scanner.start()

    def _on_rescan_finished(self, items):
        """Filter for new items and add them to the model."""
        existing_paths = {item.file_path for item in self.model.items}
        new_items = [it for it in items if it.file_path not in existing_paths]
        
        if new_items:
            for item in new_items:
                self._parse_item_tags(item)
            self.model.add_items(new_items)
            self.thumb_area.frame_all()
            
            if self.config.get("run_thumb_after_scan", False):
                self.start_conversions(new_items)
            elif self.config.get("run_review_after_scan", False):
                self.start_review_conversions()
            else:
                self.trigger_ayon_thumbnail_downloads()
                
            self.log_message(f"Rescan complete. Added {len(new_items)} new items.", "success")
        else:
            self.log_message("Rescan complete. No new items found.")
            self.trigger_ayon_thumbnail_downloads()

    def _on_project_changed(self, project_name):
        """Called when user selects a different project in the top bar."""
        if not project_name or not self.ayon.is_connected:
            return
            
        # Clear "not available" states
        self.ayon_thumb_states = {k: v for k, v in self.ayon_thumb_states.items() if v != "not available"}
        self.save_ayon_thumb_states()
        
        # Save last project to config
        self.config["last_ayon_project"] = project_name
        self.save_config()
        
        self.refresh_hierarchy_async(project_name)

    def _update_model_presets(self):
        """Update the model's category-to-preset-name mapping and re-evaluate items."""
        active_map = {}
        presets = self.config.get("presets", {})
        for p_type, p_list in presets.items():
            active_name = "-"
            for p in p_list:
                if p.get("Active"):
                    active_name = p.get("Name", "-")
                    break
            else:
                if p_list:
                    active_name = p_list[0].get("Name", "-")
            
            # Map back to model categories
            if p_type == "stills": active_map["Still"] = active_name
            elif p_type == "sequences": active_map["Sequence"] = active_name
            elif p_type == "videos": active_map["Video"] = active_name
            elif p_type == "other": active_map["Other"] = active_name
            
        self.model.set_presets(active_map)
        self.model.stills_thumb_same = self.config.get("stills_thumb_same", True)
        
        # Default frame settings from config
        stills_start = self.config.get("stills_start_frame", 1001)
        stills_end = self.config.get("stills_end_frame", 1001)
        video_start = self.config.get("video_start_frame", 1001)
        video_tc = self.config.get("video_start_from_tc", False)

        # Re-evaluate every item in the model
        for item in self.model.items:
            cat = item.category
            p_type = "other"
            if "sequence" in cat.lower(): p_type = "sequences"
            elif cat == "Still": p_type = "stills"
            elif cat == "Video": p_type = "videos"
            
            matched_p = evaluate_preset(item.file_path, presets, p_type, label=item.label)
            if matched_p:
                item.preset_name = matched_p.get("Name")
                item.variant = matched_p.get("Variant")
                item.product_type = matched_p.get("Product Type")
                item.camel_case = matched_p.get("CamelCase", True)
                item.representation = matched_p.get("Representation", "{extension}")
                item.colorspace = matched_p.get("Colorspace", "sRGB")
                item.rep_tags = matched_p.get("Tags", "passing")
                item.preset_data = matched_p
                
                # Update review status
                if matched_p.get("Convert Review", True):
                    # Only reset to waiting if it wasn't already done/processing? 
                    # Actually, if the preset changed, we might want to re-convert.
                    # But if it's already "done", we probably shouldn't reset it unless the user explicitly asks.
                    # For now, let's only set to waiting if it was "do not convert" or "failed".
                    if item.review_status in ["do not convert", "failed"]:
                        item.review_status = "waiting"
                else:
                    item.review_status = "do not convert"
            else:
                item.preset_name = None
                item.variant = None
                item.product_type = None
                item.camel_case = True
                item.representation = "{extension}"
                item.colorspace = "sRGB"
                item.rep_tags = "passing"
                item.preset_data = {}
                item.review_status = "do not convert"

            # Refresh frames for non-sequences
            if cat == "Still":
                item.frame_start = stills_start
                item.frame_end = stills_end
            elif cat == "Video":
                # Start from TC if enabled and available in metadata
                if video_tc and item.metadata.get("start_from_tc") is not None:
                    item.frame_start = item.metadata["start_from_tc"]
                    item.frame_end = item.metadata["start_from_tc"]
                else:
                    item.frame_start = video_start
                    item.frame_end = video_start
            
        self.model.layoutChanged.emit()

    def refresh_ayon(self):
        self.refresh_ayon_async(reconnect=False)

    def refresh_ayon_async(self, reconnect=False):
        """Asynchronously connect and refresh AYON projects list."""
        if hasattr(self, "_conn_thread") and self._conn_thread.isRunning():
            return
            
        # Clear "not available" states so we can retry them
        self.ayon_thumb_states = {k: v for k, v in self.ayon_thumb_states.items() if v != "not available"}
        self.save_ayon_thumb_states()
            
        # Force a reconnect if we aren't connected yet
        if not self.ayon.is_connected:
            reconnect = True
            
        self.ayon_panel.set_connection_status(self.ayon.is_connected, self.ayon.server_url)
        
        class ConnectionThread(QThread):
            finished = Signal(bool, list)
            def __init__(self, ayon, url, key, do_connect):
                super().__init__()
                self.ayon = ayon
                self.url = url
                self.key = key
                self.do_connect = do_connect
            def run(self):
                import time
                start_t = time.perf_counter()
                print("[Timer] Starting to pull projects list from AYON...")
                if self.do_connect:
                    print(f"[Timer] Connecting to AYON server at {self.url}...")
                    self.ayon.connect(self.url, self.key)
                projects = self.ayon.get_projects()
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling projects list from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(self.ayon.is_connected, projects)

        server_url = self.secrets.get("ayon_server_url", "").strip()
        api_key = self.secrets.get("ayon_api_key", "").strip()
        if not api_key: # Fallback
            api_key = self.config.get("ayon_api_key", "").strip()
        
        self._conn_thread = ConnectionThread(self.ayon, server_url, api_key, reconnect)
        self._conn_thread.finished.connect(self._on_ayon_refreshed)
        self._conn_thread.start()

    def _on_ayon_refreshed(self, is_connected, projects):
        """Called when project list refresh is done."""
        self.ayon_panel.set_connection_status(is_connected, self.ayon.server_url)
        
        # Block signals to avoid feedback loop when setting project list
        self.ayon_panel.combo_project.blockSignals(True)
        current = self.ayon_panel.combo_project.currentText()
        if not current:
            current = self.config.get("ayon_project") or self.config.get("last_ayon_project")
            
        self.ayon_panel.set_projects(projects)
        if current in projects:
            self.ayon_panel.combo_project.setCurrentText(current)
        self.ayon_panel.combo_project.blockSignals(False)
        
        if is_connected:
            project = self.ayon_panel.combo_project.currentText()
            if project:
                self.refresh_hierarchy_async(project)
 
    def refresh_hierarchy_async(self, project_name):
        """Asynchronously fetch folder hierarchy for a specific project."""
        if hasattr(self, "_last_fetched_project") and self._last_fetched_project == project_name:
            if hasattr(self, "_hier_thread") and self._hier_thread.isRunning():
                return
        self._last_fetched_project = project_name
        
        if hasattr(self, "_hier_thread") and self._hier_thread.isRunning():
            try:
                self._hier_thread.finished.disconnect()
            except Exception:
                pass
            self._hier_thread.terminate()
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._hier_thread)
            
        class HierarchyThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project):
                super().__init__()
                self.ayon = ayon
                self.project = project
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull folder hierarchy for project '{self.project}' from AYON...")
                hierarchy = self.ayon.get_project_hierarchy(self.project)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling folder hierarchy for project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(hierarchy)
 
        self._hier_thread = HierarchyThread(self.ayon, project_name)
        self._hier_thread.finished.connect(self.ayon_panel.set_hierarchy)
        self._hier_thread.finished.connect(self._update_ayon_visuals)
        self._hier_thread.finished.connect(self._restore_ayon_selection)
        self._hier_thread.finished.connect(self._refresh_ayon_panel_icons)
        self._hier_thread.finished.connect(self.trigger_ayon_thumbnail_downloads)
        self._hier_thread.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'help_overlay'):
            self.help_overlay.setGeometry(self.rect())

    def show_help(self):
        self.help_overlay.show_help()

    def open_help_guide(self):
        import os
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        doc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "help_guide.md")
        if os.path.exists(doc_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(doc_path))
        else:
            self.log_message(f"Help Guide file not found at: {doc_path}", "error")

    def open_help_reference(self):
        import os
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        doc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "help_reference.md")
        if os.path.exists(doc_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(doc_path))
        else:
            self.log_message(f"Help Reference file not found at: {doc_path}", "error")

    def show_preferences(self):
        # Store old values to check if re-scan is needed
        old_detect = self.config.get("detect_sequences", True)
        old_thumb = self.config.get("seq_thumb_frame", "Middle")
        old_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)

        dialog = PreferencesDialog(self.config, self.secrets, self)
        
        # Set size to 80% of main window
        new_w = int(self.width() * 0.8)
        new_h = int(self.height() * 0.8)
        dialog.resize(new_w, new_h)
        
        # Connect Apply button signal
        dialog.applied.connect(lambda data: self._apply_preferences(data[0], data[1], old_detect, old_thumb, old_regex, old_exts, show_message=False))
        
        if dialog.exec():
            new_config, new_secrets = dialog.get_settings()
            self._apply_preferences(new_config, new_secrets, old_detect, old_thumb, old_regex, old_exts, show_message=True)

    def _apply_preferences(self, new_config, new_secrets, old_detect, old_thumb, old_regex, old_exts, show_message=True, save=True):
        self.config.update(new_config)
        self.secrets.update(new_secrets)
        
        default_cols = self.config.get("default_columns", 12)
        default_text_size = self.config.get("default_text_size", 10)
        default_thumb_size = self.config.get("default_thumb_size", 150)
        
        gap_h = int(default_thumb_size * 0.20)
        gap_v = int(default_thumb_size * 0.20)
        
        self.thumb_area._last_arrange_vals["cols"] = default_cols
        self.thumb_area._last_arrange_vals["gap_h"] = gap_h
        self.thumb_area._last_arrange_vals["gap_v"] = gap_v
        
        # Update sliders first so items are sized correctly before rearrange
        self.thumb_area.slider_text_size.setValue(default_text_size)
        self.thumb_area.slider_thumb_size.setValue(default_thumb_size)
        self.thumb_area.rearrange_items(force=True)
        self.thumb_area.high_res_size = self.config.get("thumb_size", 512)
        
        # Apply label regex update
        label_regex = self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$")
        self.model.label_allowed_regex = label_regex
        self.thumb_area.update_label_validator(label_regex)
        
        # Update Tooltip templates
        tt_keys = ["item_info_stills", "item_info_sequences", "item_info_videos", "item_info_other"]
        tt_templates = {k: self.config.get(k, "") for k in tt_keys}
        self.thumb_area.set_tooltip_templates(tt_templates)
        
        # Update Filter Panel sequence display
        version_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        self.model.version_regex = version_regex
        self.model.rebuild_version_stacks()
        
        self.filter_panel.set_sequence_detection(
            self.config.get("detect_sequences", True),
            version_regex
        )
        
        if save:
            self.save_config()
            self.save_secrets()
        self._update_model_presets()
        self.update_preset_dropdown()
        
        # Update model properties that affect string expansion
        self.model.product_name_template = self.config.get("product_name", "{label}")
        self.model.product_name_camel = self.config.get("product_name_camel", True)
        self.model.stills_thumb_same = self.config.get("stills_thumb_same", True)
        self.model.high_res_size = self.config.get("thumb_size", 512)
        self.model.default_fps = self.config.get("default_fps", 25.0)
        self.model.use_fps_from_metadata = self.config.get("use_fps_from_metadata", True)
        
        self.model.thumb_location = self.config.get("thumb_location", "Relative to Source Folder")
        self.model.thumb_location_path = self.config.get("thumb_location_path", "_thumbs")
        self.model.thumb_suffix = self.config.get("thumb_suffix", "_thumbnail")
        self.model.thumb_format = self.config.get("thumb_format", ".jpg")
        
        from utils import expand_env_vars
        self.model.ffmpeg_path = expand_env_vars(self.secrets.get("ffmpeg_path", "ffmpeg.exe"))
        self.model.ffprobe_path = expand_env_vars(self.secrets.get("ffprobe_path", "ffprobe.exe"))
        self.model.oiiotool_path = expand_env_vars(self.secrets.get("oiiotool_path", "oiiotool.exe"))
        vfxtrans_path = expand_env_vars(self.secrets.get("vfxtranscode", ""))
        self.model.vfxtranscode = os.path.abspath(vfxtrans_path).replace("\\", "/") if vfxtrans_path else ""
        ocio_config_path = expand_env_vars(self.secrets.get("ocio_config", ""))
        self.model.ocio_config = os.path.abspath(ocio_config_path).replace("\\", "/") if ocio_config_path else ""
        
        self.csv_preview_model.refresh_config(self.config)
        
        # Check if scan-related settings changed
        new_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)
        scan_affected = (
            old_detect != self.config.get("detect_sequences") or
            old_thumb != self.config.get("seq_thumb_frame") or
            old_regex != self.config.get("version_regex") or
            old_exts != new_exts
        )
        
        if scan_affected and self.config.get("last_source_folder"):
            self.start_scan(self.config["last_source_folder"])

        # Refresh AYON asynchronously
        self.refresh_ayon_async(reconnect=True)
        
        if show_message:
            QMessageBox.information(self, "Preferences", "Settings saved. View has been refreshed to reflect scanner changes.")

    def _on_cols_changed(self, value):
        self.config["default_columns"] = value
        self.save_config()

    def _on_text_size_changed(self, value):
        self.config["default_text_size"] = value
        self.save_config()

    def _on_thumb_size_changed(self, value):
        self.config["default_thumb_size"] = value
        # Sync with scanner size so new items match current UI
        self.config["thumbnail_size"] = value
        self.save_config()

    def _on_age_filter_changed(self, value, units, enabled):
        self._age_filter_enabled = enabled
        self._age_filter_units = units
        
        # Convert to minutes for internal comparison
        # We add 1 to the value to include the full period (e.g. 0 days = < 1 day)
        minutes = (value + 1)
        if units == "hours": minutes *= 60
        elif units == "days": minutes *= 1440
        self._age_filter_value = minutes
        
        self.model.set_age_unit(units)
        
        # Re-calculate ages and refresh filtering
        self._update_ages()
        self.spreadsheet.update_filtering(age_filter=(self._age_filter_enabled, self._age_filter_value))
        self.thumb_area.rearrange_items(age_filter=(self._age_filter_enabled, self._age_filter_value))
        
        # Save changed states immediately
        self.config["filter_age_enabled"] = enabled
        self.config["filter_age_value"] = value
        self.config["filter_age_units"] = units
        self.save_config()

    def _update_ages(self):
        import time
        current_time = time.time()
        source = self.config.get("age_source", "Modification Date")
        
        for item in self.model.items:
            source_time = item.modification_time if source == "Modification Date" else item.creation_time
            item.age_minutes = int((current_time - source_time) / 60)
        
        # Notify the model that the age column (index 9) has changed
        if self.model.items:
            self.model.dataChanged.emit(
                self.model.index(0, 9), 
                self.model.index(len(self.model.items)-1, 9)
            )

    def _gather_gui_state(self):
        # 1. AYON Panel
        if hasattr(self, "ayon_panel") and self.ayon_panel:
            self.config["ayon_project"] = self.ayon_panel.combo_project.currentText()
            self.config["ayon_search_text"] = self.ayon_panel.search_edit.text()
            self.config["ayon_search_column"] = self.ayon_panel.search_combo.currentIndex()
            self.config["ayon_show_thumbs"] = self.ayon_panel.btn_show_thumbs.isChecked()
            
            # Selected folder & task in AYON tree
            ayon_folder = ""
            ayon_task = ""
            try:
                indexes = self.ayon_panel.tree.selectionModel().selectedIndexes()
                if indexes:
                    source_idx = self.ayon_panel.proxy.mapToSource(indexes[0])
                    first_col_index = self.ayon_panel.model.index(source_idx.row(), 0, source_idx.parent())
                    item = self.ayon_panel.model.itemFromIndex(first_col_index)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data:
                            if 'folderId' in data and 'folder_path' in data: # Task
                                ayon_folder = data.get("folder_path", "")
                                ayon_task = data.get("name", "")
                            elif 'path' in data: # Folder
                                ayon_folder = data.get("path", "")
                                ayon_task = ""
            except Exception as e:
                print(f"Error gathering AYON selection state: {e}")
            self.config["ayon_selected_folder"] = ayon_folder
            self.config["ayon_selected_task"] = ayon_task

        # 2. Top Panel
        if hasattr(self, "top_bar") and self.top_bar:
            self.config["last_source_folder"] = self.top_bar.path_display.text()
            self.config["active_preset"] = self.top_bar.combo_preset.currentText()

        # 3. Thumbnails Panel
        if hasattr(self, "thumb_area") and self.thumb_area:
            self.config["default_columns"] = self.thumb_area._last_arrange_vals["cols"]
            self.config["thumbnails_show_text"] = self.thumb_area.btn_show_text.isChecked()
            self.config["default_text_size"] = self.thumb_area.slider_text_size.value()
            self.config["default_thumb_size"] = self.thumb_area.slider_thumb_size.value()

        # 4. Filter Panel
        if hasattr(self, "filter_panel") and self.filter_panel:
            self.config["filter_search_enabled"] = self.filter_panel.chk_search.isChecked()
            self.config["filter_search_text"] = self.filter_panel.search_bar.text()
            self.config["filter_age_enabled"] = self.filter_panel.chk_age.isChecked()
            self.config["filter_age_value"] = self.filter_panel.spin_age.value()
            self.config["filter_age_units"] = self.filter_panel.combo_units.currentText()
            self.config["filter_files_only"] = self.filter_panel.btn_files_only.isChecked()
            self.config["filter_flat"] = self.filter_panel.btn_flat.isChecked()
            self.config["filter_v_stack"] = self.filter_panel.btn_v_stack.isChecked()
            self.config["filter_sequences"] = self.filter_panel.btn_sequences.isChecked()

    def _restore_gui_state(self):
        # 1. AYON Panel
        if hasattr(self, "ayon_panel") and self.ayon_panel:
            self.ayon_panel.search_edit.setText(self.config.get("ayon_search_text", ""))
            self.ayon_panel.search_combo.setCurrentIndex(self.config.get("ayon_search_column", 0))
            self.ayon_panel.btn_show_thumbs.setChecked(self.config.get("ayon_show_thumbs", True))

        # 2. Thumbnails Panel
        if hasattr(self, "thumb_area") and self.thumb_area:
            default_cols = self.config.get("default_columns", 12)
            default_text_size = self.config.get("default_text_size", 10)
            default_thumb_size = self.config.get("default_thumb_size", 150)
            
            gap_h = int(default_thumb_size * 0.20)
            gap_v = int(default_thumb_size * 0.20)
            
            self.thumb_area._last_arrange_vals["cols"] = default_cols
            self.thumb_area._last_arrange_vals["gap_h"] = gap_h
            self.thumb_area._last_arrange_vals["gap_v"] = gap_v
            
            # Update sliders first so items are sized correctly before rearrange
            self.thumb_area.slider_text_size.setValue(default_text_size)
            self.thumb_area.slider_thumb_size.setValue(default_thumb_size)
            self.thumb_area.rearrange_items(force=True)
            
            show_text = self.config.get("thumbnails_show_text", True)
            self.thumb_area.btn_show_text.setChecked(show_text)
            self.thumb_area._on_show_text_toggled(show_text)

        # 3. Filter Panel
        if hasattr(self, "filter_panel") and self.filter_panel:
            self.filter_panel.chk_search.setChecked(self.config.get("filter_search_enabled", True))
            self.filter_panel.search_bar.setText(self.config.get("filter_search_text", ""))
            self.filter_panel.chk_age.setChecked(self.config.get("filter_age_enabled", False))
            self.filter_panel.spin_age.setValue(self.config.get("filter_age_value", 0))
            self.filter_panel.combo_units.setCurrentText(self.config.get("filter_age_units", "minutes"))
            
            # Toggles
            toggles = {
                "files_only": self.config.get("filter_files_only", self.config.get("filter_toggles", {}).get("files_only", True)),
                "flat": self.config.get("filter_flat", self.config.get("filter_toggles", {}).get("flat", False)),
                "v_stack": self.config.get("filter_v_stack", self.config.get("filter_toggles", {}).get("v_stack", False)),
                "sequences": self.config.get("filter_sequences", self.config.get("filter_toggles", {}).get("sequences", True)),
            }
            self.filter_panel.set_toggle_states(toggles)

    def _restore_ayon_selection(self):
        folder = self.config.get("ayon_selected_folder")
        task = self.config.get("ayon_selected_task")
        if folder:
            self.ayon_panel.select_path(folder, task)

    def save_config(self):
        if hasattr(self, "_is_initializing") and self._is_initializing:
            return
        self._gather_gui_state()
        # Sensitive data should not be in config.json
        clean_config = self.config.copy()
        
        shifted_keys = [
            "presets_folder",
            "ayon_server_url",
            "traypublisher_path",
            "ffmpeg_path",
            "ffprobe_path",
            "oiiotool_path",
            "vfxtranscode",
            "ocio_config",
            "ayon_api_key",
            "ingest_log_folder",
            "per_project_logging"
        ]
        for key in shifted_keys:
            if key in clean_config:
                del clean_config[key]
            
        # Remove redundant keys
        if "thumbnails_per_row" in clean_config:
            del clean_config["thumbnails_per_row"]
            
        try:
            with open("config.json", "w") as f:
                json.dump(clean_config, f, indent=4)
        except Exception as e:
            print(f"Error saving config.json: {e}")
            
        presets_folder = self.secrets.get("presets_folder") or "presets"
        import os
        username = os.environ.get("USERNAME", "default_user")
        
        users_dir = os.path.join(presets_folder, "users")
        if not os.path.exists(users_dir):
            try:
                os.makedirs(users_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating user presets directory {users_dir}: {e}")
        
        if os.path.exists(users_dir):
            user_pref_path = os.path.join(users_dir, f"{username}.json")
            try:
                with open(user_pref_path, "w") as f:
                    json.dump(clean_config, f, indent=4)
                print(f"Saved user preferences for '{username}' to {user_pref_path}")
            except Exception as e:
                print(f"Error saving user preferences to {user_pref_path}: {e}")

    def save_secrets(self):
        with open("install.json", "w") as f:
            json.dump(self.secrets, f, indent=4)

    def perform_export_csv(self):
        tagged_items = self._get_tagged_for_ingest()
        if not tagged_items: return
        
        source_folder = self.config.get("last_source_folder")
        if not source_folder or not os.path.exists(source_folder):
            QMessageBox.warning(self, "Export CSV", "No valid source folder scanned.")
            return

        # 1. Validate items
        self.log_message("Export CSV: Running validation checks...")
        valid_items, skipped_duplicates, skipped_collisions = self._validate_tagged_items(tagged_items)
            
        if not valid_items:
            msg = "All selected items were skipped due to errors:\n"
            if skipped_duplicates: msg += f"- {skipped_duplicates} duplicates\n"
            if skipped_collisions: msg += f"- {skipped_collisions} version collisions\n"
            QMessageBox.warning(self, "Export CSV", msg)
            return

        # 2. Export logic
        folder_name = os.path.basename(os.path.abspath(source_folder))
        if not folder_name: folder_name = "export"
        csv_path = os.path.join(source_folder, f"{folder_name}.csv")
        
        try:
            self._write_csv_from_preview(valid_items, csv_path)
            self.log_message(f"Exported {len(valid_items)} items to CSV: {csv_path}", "success")
            
            # Summary message
            summary = f"CSV exported successfully to:\n{csv_path}\n\n"
            summary += f"Total exported: {len(valid_items)}\n"
            if skipped_duplicates or skipped_collisions:
                summary += f"Total skipped: {skipped_duplicates + skipped_collisions}\n"
                if skipped_duplicates: summary += f"  - Duplicates: {skipped_duplicates}\n"
                if skipped_collisions: summary += f"  - Version collisions: {skipped_collisions}\n"
            
            QMessageBox.information(self, "Export CSV", summary)
            
        except Exception as e:
            self.log_message(f"Failed to export CSV: {e}", "error")
            QMessageBox.critical(self, "Export CSV", f"Failed to export CSV: {e}")

    def _validate_tagged_items(self, tagged_items):
        """Run duplicity and version collision checks and return (valid_items, skip_dup_count, skip_coll_count)."""
        # 1. Run Duplicity Test
        duplicate_items = self._check_duplicates_in_list(tagged_items)
        duplicate_set = set(duplicate_items)
        
        # 2. Run Version Collision Test (Synchronous)
        project = self.ayon_panel.combo_project.currentText()
        v_map = {}
        if project:
            v_map = self._check_versions_sync(tagged_items)
        
        collision_items = []
        for item in tagged_items:
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            path_map = self.ayon_panel.get_path_to_id_map()
            f_id = path_map.get(folder_path)
            if f_id:
                prod_name = self.model._expand_string(self.model.product_name_template, item, use_global_camel=True)
                key = f"{f_id}|{prod_name}|{item.product_type}"
                last_v = v_map.get(key)
                if last_v is not None and last_v >= item.version:
                    collision_items.append(item)
        
        collision_set = set(collision_items)
        
        valid_items = []
        skipped_duplicates = 0
        skipped_collisions = 0
        
        for item in tagged_items:
            if item in duplicate_set:
                skipped_duplicates += 1
                continue
            if item in collision_set:
                skipped_collisions += 1
                continue
            valid_items.append(item)
            
        return valid_items, skipped_duplicates, skipped_collisions

    def _check_duplicates_in_list(self, items):
        """Returns a list of items that are considered duplicates within the provided list."""
        identity_map = {}
        for item in items:
            prod_name = self.model._expand_string(self.model.product_name_template, item, use_global_camel=True)
            identity = f"{item.ayon_path}{prod_name}{item.version}"
            if identity not in identity_map:
                identity_map[identity] = []
            identity_map[identity].append(item)
            
        duplicates = []
        for group in identity_map.values():
            if len(group) > 1:
                duplicates.extend(group)
        return duplicates

    def _check_versions_sync(self, items):
        """Synchronously fetch versions from AYON for the provided items."""
        import time
        start_t = time.perf_counter()
        project = self.ayon_panel.combo_project.currentText()
        if not project: return {}
        
        path_map = self.ayon_panel.get_path_to_id_map()
        folder_ids = set()
        for item in items:
            if not item.ayon_path: continue
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            if f_id: folder_ids.add(f_id)
            
        if not folder_ids: return {}
        
        try:
            print(f"[Timer] Starting synchronous pull of last versions for {len(folder_ids)} folders in project '{project}' from AYON...")
            res = self.ayon.get_last_versions(project, list(folder_ids))
            elapsed = time.perf_counter() - start_t
            print(f"[Timer] Synchronous pull of last versions from AYON took {elapsed:.4f} seconds.")
            return res
        except Exception as e:
            self.log_message(f"Version check failed during export: {e}", "error")
            return {}

    def perform_publish_local(self):
        tagged_items = self._get_tagged_for_ingest()
        if not tagged_items: return
        
        # 1. Validate items
        self.log_message("Publish Local: Running validation checks...")
        valid_items, skipped_duplicates, skipped_collisions = self._validate_tagged_items(tagged_items)
        
        if not valid_items:
            msg = "All selected items were skipped due to errors:\n"
            if skipped_duplicates: msg += f"- {skipped_duplicates} duplicates\n"
            if skipped_collisions: msg += f"- {skipped_collisions} version collisions\n"
            QMessageBox.warning(self, "Publish Ayon Local", msg)
            return
            
        if skipped_duplicates or skipped_collisions:
            msg = f"Found {skipped_duplicates + skipped_collisions} invalid items which will be skipped.\n"
            if skipped_duplicates: msg += f"- {skipped_duplicates} duplicates\n"
            if skipped_collisions: msg += f"- {skipped_collisions} version collisions\n"
            msg += "\nDo you want to proceed with the remaining items?"
            res = QMessageBox.question(self, "Publish Ayon Local", msg, QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.No:
                return

        # 2. Proceed with publish
        project = self.ayon_panel.combo_project.currentText()
        
        # Determine target CSV log path
        log_folder = self.secrets.get("ingest_log_folder", "").strip()
        if log_folder:
            per_project = self.secrets.get("per_project_logging", True)
            if per_project and project:
                log_dir = os.path.join(log_folder, project)
            else:
                log_dir = log_folder
            try:
                os.makedirs(log_dir, exist_ok=True)
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = os.path.normpath(os.path.join(log_dir, f"ayon_ingest_{timestamp}.csv"))
            except Exception as e:
                self.log_message(f"Failed to create Ingest Log Folder structure: {e}. Falling back to temp directory.", "warning")
                import tempfile
                csv_path = os.path.normpath(os.path.join(tempfile.gettempdir(), "ayon_ingest.csv"))
        else:
            import tempfile
            csv_path = os.path.normpath(os.path.join(tempfile.gettempdir(), "ayon_ingest.csv"))
        
        try:
            self._write_csv_from_preview(valid_items, csv_path)
        except Exception as e:
            self.log_message(f"Failed to write temporary CSV: {e}", "error")
            QMessageBox.critical(self, "CSV Error", f"Failed to write temporary CSV: {e}")
            return
        
        from utils import expand_env_vars
        tray_path = expand_env_vars(self.secrets.get("traypublisher_path", "ayon_console.exe"))
        ingest_folder = self.config.get("ayon_csv_ingest_folder", "/edit/csvingest")
        ingest_task = self.config.get("ayon_csv_ingest_task", "csvingest")
        ingest_preset = self.config.get("ayon_csv_preset", "Default")
        ignore_validators = self.config.get("ayon_ignore_validators", True)

        cmd = [
            tray_path, "addon", "traypublisher", "ingestcsv",
            "--filepath", csv_path,
            "--project", project,
            "--folder-path", ingest_folder,
            "--task", ingest_task,
            "--preset", ingest_preset
        ]
        if ignore_validators:
            cmd.append("--ignore-validators")
        print(cmd)
        try:
            # Prepare environment with Ftrack secrets
            env = os.environ.copy()
            ftrack_server = self.secrets.get("ftrack_server", "")
            ftrack_user = self.secrets.get("ftrack_api_user", "")
            ftrack_key = self.secrets.get("ftrack_api_key", "")
            
            if ftrack_server: env["FTRACK_SERVER"] = ftrack_server
            if ftrack_user: env["FTRACK_API_USER"] = ftrack_user
            if ftrack_key: env["FTRACK_API_KEY"] = ftrack_key
            
            # Show log console and inform user
            self.log_console.show()
            self.btn_toggle_log.setChecked(True)
            self.log_message("Starting Ayon Publish process...", "info")

            class PublishWorker(QThread):
                line_received = Signal(str)
                
                def __init__(self, cmd, env):
                    super().__init__()
                    self.cmd = cmd
                    self.env = env
                    
                def run(self):
                    # CREATE_NO_WINDOW = 0x08000000
                    process = subprocess.Popen(
                        self.cmd, 
                        env=self.env, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.STDOUT, 
                        text=True,
                        bufsize=1,
                        creationflags=0x08000000
                    )
                    for line in process.stdout:
                        self.line_received.emit(line.strip())
                    process.wait()

            self._publish_worker = PublishWorker(cmd, env)
            self._publish_worker.line_received.connect(lambda line: self.log_message(f"[TrayPublisher] {line}"))
            self._publish_worker.finished.connect(lambda: self._on_publish_finished(csv_path, valid_items))
            self._publish_worker.start()

        except Exception as e:
            self.log_message(f"Failed to start TrayPublisher: {e}", "error")

    def _on_publish_finished(self, csv_path, valid_items):
        self.log_message("Publish process finished.", "success")
        self.refresh_ayon()
        
        # Check if Ingest Check is enabled
        if not self.config.get("ayon_ingest_check", True):
            return
            
        self.log_message("Starting Ingest Check verification...", "info")
        
        import csv
        import shutil
        import datetime
        import ayon_api
        
        if not self.ayon.is_connected:
            self.log_message("AYON is not connected. Ingest Check cannot run.", "error")
            return
            
        project = self.ayon_panel.combo_project.currentText()
        if not project:
            self.log_message("No project selected for Ingest Check.", "error")
            return
            
        if not csv_path or not os.path.exists(csv_path):
            self.log_message(f"Ingest Log file not found at: {csv_path}", "error")
            return
            
        delimiter = self.config.get("csv_delimiter", ",")
        quotechar = self.config.get("csv_quotechar", '"')
        
        rows = []
        headers = []
        try:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
                headers = next(reader, [])
                for r in reader:
                    if r:
                        rows.append(r)
        except Exception as e:
            self.log_message(f"Error reading Ingest Log file: {e}", "error")
            return
            
        # Find critical columns by checking headers case-insensitively
        file_path_col = -1
        ayon_path_col = -1
        product_name_col = -1
        version_col = -1
        repre_col = -1
        task_col = -1
        
        for idx, h in enumerate(headers):
            h_lower = h.lower().strip()
            if h_lower in ["file path", "filepath"]:
                file_path_col = idx
            elif h_lower in ["ayon path", "folder path", "folder_path"]:
                ayon_path_col = idx
            elif h_lower in ["product name", "product", "subset"]:
                product_name_col = idx
            elif h_lower in ["version", "v"]:
                version_col = idx
            elif h_lower in ["representation", "repre"]:
                repre_col = idx
            elif h_lower in ["task", "task name", "task_name"]:
                task_col = idx
                
        def normalize_version(v_str):
            if not v_str: return None
            try:
                return int(v_str)
            except ValueError:
                pass
            import re
            m = re.search(r'\d+', str(v_str))
            if m:
                return int(m.group())
            return None
            
        checked_rows = []
        check_results = []
        
        # Map item path (normalized, absolute) -> item to update ingest_status
        item_map = {}
        for item in valid_items:
            norm_main = os.path.normpath(os.path.abspath(item.file_path)).lower()
            item_map[norm_main] = item
            review_path = self.model.expand_tokens("{prefs_review_path}", item)
            if review_path:
                norm_review = os.path.normpath(os.path.abspath(review_path)).lower()
                item_map[norm_review] = item
                
        item_statuses = {}
        
        for row in rows:
            while len(row) < len(headers):
                row.append("")
                
            file_path_val = row[file_path_col] if file_path_col >= 0 else ""
            ayon_path_val = row[ayon_path_col] if ayon_path_col >= 0 else ""
            version_val = row[version_col] if version_col >= 0 else ""
            
            matched_item = None
            if file_path_val:
                norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                matched_item = item_map.get(norm_f)
                
            product_name_val = ""
            if matched_item:
                product_name_val = self.model._expand_string(self.model.product_name_template, matched_item, use_global_camel=True)
            if not product_name_val and product_name_col >= 0 and product_name_col < len(row):
                product_name_val = row[product_name_col]
                
            if not product_name_val:
                p_type_val = ""
                variant_val = ""
                for idx, h in enumerate(headers):
                    h_lower = h.lower().strip()
                    if "product type" in h_lower or "product_type" in h_lower:
                        p_type_val = row[idx] if idx < len(row) else ""
                    elif "variant" in h_lower:
                        variant_val = row[idx] if idx < len(row) else ""
                if p_type_val or variant_val:
                    camel = self.config.get("product_name_camel", True)
                    if camel:
                        if p_type_val: p_type_val = p_type_val[0].upper() + p_type_val[1:]
                        if variant_val: variant_val = variant_val[0].upper() + variant_val[1:]
                    product_name_val = f"{p_type_val}{variant_val}"
            
            repre_name = ""
            if repre_col >= 0 and repre_col < len(row):
                repre_name = row[repre_col]
            if not repre_name and file_path_val:
                repre_name = os.path.splitext(file_path_val)[1].replace(".", "").lower()
                
            status_str = "OK"
            try:
                folder = ayon_api.get_folder_by_path(project, ayon_path_val)
                if not folder:
                    status_str = f"Failed: AYON Folder {ayon_path_val} not found"
                else:
                    products = list(ayon_api.get_products(project, folder_ids=[folder["id"]]))
                    product = next((p for p in products if p["name"].lower() == product_name_val.lower()), None)
                    if not product:
                        status_str = f"Failed: Product name \"{product_name_val}\" not found"
                    else:
                        versions = list(ayon_api.get_versions(project, product_ids=[product["id"]]))
                        target_v_num = normalize_version(version_val)
                        version_obj = next((v for v in versions if normalize_version(v.get("version")) == target_v_num), None)
                        if not version_obj:
                            status_str = f"Failed: version {version_val} of product \"{product['name']}\" not found"
                        else:
                            repres = list(ayon_api.get_representations(project, version_ids=[version_obj["id"]]))
                            repre_obj = next((r for r in repres if (
                                r["name"].lower() == repre_name.lower() or
                                repre_name.lower() in r["name"].lower() or
                                r["name"].lower() in repre_name.lower()
                            )), None)
                            if not repre_obj:
                                status_str = f"Failed: version {version_val} of repre \"{repre_name}\" of product \"{product['name']}\" not found"
                            else:
                                if self.config.get("set_version_status_after_check", True):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        ayon_api.update_version(project, version_id=version_obj["id"], status=target_status)
                                        self.log_message(f"Updated AYON version {version_val} (ID: {version_obj['id']}) status to: {target_status}", "success")
                                    except Exception as e:
                                        self.log_message(f"Failed to update AYON version status for version {version_val}: {e}", "warning")

                                if self.config.get("set_product_status_after_check", True):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        ayon_api.update_product(project, product_id=product["id"], status=target_status)
                                        self.log_message(f"Updated AYON product {product['name']} status to: {target_status}", "success")
                                    except Exception as e:
                                        self.log_message(f"Failed to update AYON product status for {product['name']}: {e}", "warning")

                                if self.config.get("set_task_status_after_check", True) or self.config.get("set_neighbour_status_after_check", False):
                                    target_status = self.config.get("ayon_version_status", "Pending Review")
                                    try:
                                        tasks = list(ayon_api.get_tasks(project, folder_ids=[folder["id"]]))
                                        
                                        if self.config.get("set_task_status_after_check", True):
                                            current_task_name = row[task_col] if (task_col >= 0 and len(row) > task_col and row[task_col]) else self.config.get("ayon_csv_ingest_task", "csvingest")
                                            if current_task_name:
                                                current_task = next((t for t in tasks if t["name"].lower() == current_task_name.lower()), None)
                                                if current_task:
                                                    ayon_api.update_task(project, task_id=current_task["id"], status=target_status)
                                                    self.log_message(f"Updated AYON task {current_task['name']} status to: {target_status}", "success")
                                                else:
                                                    self.log_message(f"Task '{current_task_name}' not found under folder {ayon_path_val}", "warning")

                                        if self.config.get("set_neighbour_status_after_check", False):
                                            neighbour_name = self.config.get("neighbour_task_name", "comp")
                                            neighbour_status = self.config.get("neighbour_task_status", "Ready to start")
                                            if neighbour_name:
                                                neighbour_task = next((t for t in tasks if t["name"].lower() == neighbour_name.lower()), None)
                                                if neighbour_task:
                                                    ayon_api.update_task(project, task_id=neighbour_task["id"], status=neighbour_status)
                                                    self.log_message(f"Updated AYON neighbour task {neighbour_task['name']} status to: {neighbour_status}", "success")
                                                else:
                                                    self.log_message(f"Neighbour task '{neighbour_name}' not found under folder {ayon_path_val}", "warning")
                                    except Exception as e:
                                        self.log_message(f"Failed to update task/neighbour task status: {e}", "warning")
            except Exception as e:
                self.log_message(f"Error checking AYON database for product '{product_name_val}': {e}", "warning")
                status_str = f"Failed: Error checking AYON database: {e}"
                
            check_results.append(status_str)
            
            if file_path_val:
                norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                if norm_f not in item_statuses:
                    item_statuses[norm_f] = []
                item_statuses[norm_f].append(status_str)
            
            checked_row = list(row)
            checked_row.append(status_str)
            checked_rows.append(checked_row)
            
        # Update matching items with their final resolved status for this run
        for norm_f, statuses in item_statuses.items():
            matched_item = item_map.get(norm_f)
            if matched_item:
                if any(s != "OK" for s in statuses):
                    matched_item.ingest_status = "Failed"
                else:
                    matched_item.ingest_status = "OK"
                self.model.update_item(matched_item)
            
        checked_headers = list(headers)
        checked_headers.append("Check")
        
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
                writer.writerow(checked_headers)
                writer.writerows(checked_rows)
        except Exception as e:
            self.log_message(f"Failed to overwrite checked CSV file: {e}", "error")
            return
            
        if all(res == "OK" for res in check_results):
            suffix = "_checkedOK"
        elif all(res.startswith("Failed") for res in check_results):
            suffix = "_checkedFailed"
        else:
            suffix = "_checkedMixed"
            
        base_no_ext, ext = os.path.splitext(csv_path)
        new_csv_path = f"{base_no_ext}{suffix}{ext}"
        try:
            shutil.move(csv_path, new_csv_path)
            self.log_message(f"Ingest Check completed! Result suffix: {suffix}. File renamed to: {os.path.basename(new_csv_path)}", "success")
        except Exception as e:
            self.log_message(f"Failed to rename Ingest Log CSV: {e}", "error")

        # Generate PDF Ingest Report if configured
        if self.config.get("create_ingest_report", True):
            pdf_path = f"{base_no_ext}{suffix}.pdf"
            self.generate_ingest_pdf_report(pdf_path, checked_rows, checked_headers, file_path_col, ayon_path_col, version_col, item_map)
            
        # Clearly communicate to the user that the item was ingested (OK/FAIL)
        ok_count = check_results.count("OK")
        fail_count = len(check_results) - ok_count
        
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("AYON Ingest Check Summary")
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
            }
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #555555;
                padding: 5px 15px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        
        summary_text = "<h3>AYON Ingest Verification Complete</h3>"
        summary_text += f"<p><b>Total checked:</b> {len(check_results)}<br/>"
        summary_text += f"<span style='color: #4caf50;'><b>Successfully Ingested (OK):</b> {ok_count}</span><br/>"
        if fail_count > 0:
            summary_text += f"<span style='color: #f44336;'><b>Failed Ingest Check:</b> {fail_count}</span></p>"
        else:
            summary_text += f"<span style='color: #4caf50;'><b>All items ingested perfectly!</b></span></p>"
            
        if fail_count > 0:
            summary_text += "<p><b>Ingest failure details:</b><ul style='color: #f44336;'>"
            for r in check_results:
                if r != "OK":
                    summary_text += f"<li>{r}</li>"
            summary_text += "</ul></p>"
            
        msg.setText(summary_text)
        if fail_count > 0:
            msg.setIcon(QMessageBox.Warning)
        else:
            msg.setIcon(QMessageBox.Information)

        if self.config.get("ayon_play_sound_on_finish", True):
            try:
                import winsound
                if fail_count > 0:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                else:
                    winsound.MessageBeep(winsound.MB_OK)
            except Exception as e:
                self.log_message(f"Failed to play finish notification sound: {e}", "warning")

        msg.exec()

        # Hide the LOG window when pressing OK / closing the summary popup
        self.log_console.hide()
        self.btn_toggle_log.setChecked(False)

        self.model.layoutChanged.emit()

    def generate_ingest_pdf_report(self, pdf_path, checked_rows, headers, file_path_col, ayon_path_col, version_col, item_map):
        self.log_message(f"Generating Ingest PDF report: {os.path.basename(pdf_path)}...", "info")
        
        try:
            import datetime
            from datetime import timezone, timedelta
            
            # 1. Parse timezone offsets
            def parse_offset_to_hours(offset_str):
                import re
                if not offset_str:
                    return 0.0
                offset_str = str(offset_str).strip()
                match = re.match(r'^([+-]?)(\d+)(?::(\d+))?$', offset_str)
                if match:
                    sign = -1 if match.group(1) == '-' else 1
                    hours = int(match.group(2))
                    minutes = int(match.group(3)) if match.group(3) else 0
                    return sign * (hours + minutes / 60.0)
                try:
                    return float(offset_str)
                except ValueError:
                    return 0.0

            tz_a = self.config.get("timezone_offset_a", "+00:00")
            tz_b = self.config.get("timezone_offset_b", "+00:00")
            
            # Local time A: do not subtract the offset A, just display the local system time of the app
            local_now = datetime.datetime.now()
            date_time_a = local_now.strftime("%Y-%m-%d %H:%M") + f" {tz_a}"
            
            # Client time B: convert to UTC, then apply client offset B
            utc_now = datetime.datetime.now(timezone.utc)
            hours_b = parse_offset_to_hours(tz_b)
            time_b = utc_now + timedelta(hours=hours_b)
            date_time_b = time_b.strftime("%Y-%m-%d %H:%M") + f" {tz_b}"

            # 2. Filter for only successfully ingested rows (Check == "OK")
            ingested_rows = [r for r in checked_rows if r and r[-1] == "OK"]
            
            if not ingested_rows:
                self.log_message("No successfully ingested rows to include in PDF report.", "warning")
                return

            # Find Variant column in headers case-insensitively
            variant_col = -1
            for idx, h in enumerate(headers):
                if h.lower().strip() == "variant":
                    variant_col = idx
                    break

            # 3. Build HTML
            html_rows = []
            for row in ingested_rows:
                file_path_val = row[file_path_col] if file_path_col >= 0 else ""
                ayon_path_val = row[ayon_path_col] if ayon_path_col >= 0 else ""
                version_val = row[version_col] if version_col >= 0 else ""
                
                filename = os.path.basename(file_path_val) if file_path_val else ""
                
                # Fetch matched item properties
                matched_item = None
                if file_path_val:
                    norm_f = os.path.normpath(os.path.abspath(file_path_val)).lower()
                    matched_item = item_map.get(norm_f)
                
                variant_val = ""
                if matched_item and matched_item.variant:
                    variant_val = matched_item.variant
                elif variant_col >= 0 and variant_col < len(row):
                    variant_val = row[variant_col]
                
                # Substitute {label} template with matched_item's actual label if present
                if matched_item and matched_item.label:
                    variant_val = variant_val.replace("{label}", matched_item.label)

                length = "1"
                frame_start = "-"
                frame_end = "-"
                b64_image = ""
                
                if matched_item:
                    # Get frame ranges
                    if matched_item.is_sequence:
                        if matched_item.frame_start is not None and matched_item.frame_end is not None:
                            frame_start = str(matched_item.frame_start)
                            frame_end = str(matched_item.frame_end)
                            length = str(matched_item.frame_end - matched_item.frame_start + 1)
                    else:
                        length = "1"
                        frame_start = "-"
                        frame_end = "-"
                    
                    # Convert thumbnail to base64 preserving aspect ratio
                    if matched_item.thumbnail and not matched_item.thumbnail.isNull():
                        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
                        scaled_thumb = matched_item.thumbnail.scaled(75, 75, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        byte_array = QByteArray()
                        buffer = QBuffer(byte_array)
                        buffer.open(QIODevice.WriteOnly)
                        scaled_thumb.save(buffer, "PNG")
                        b64_image = byte_array.toBase64().data().decode("utf-8")
                
                # Render Thumbnail cell
                if b64_image:
                    thumb_html = f'<img src="data:image/png;base64,{b64_image}" style="border: 1px solid #cccccc; border-radius: 4px;" />'
                else:
                    thumb_html = '<div style="width: 75px; height: 75px; background-color: #eaeaea; border: 1px solid #cccccc; border-radius: 4px; text-align: center; line-height: 75px; color: #888888; font-size: 10px;">No Image</div>'
                
                html_rows.append(f"""
                <tr>
                    <td style="padding: 8px; text-align: center; border-bottom: 1px solid #eeeeee;">{thumb_html}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; word-break: break-all;">{filename}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee;">{variant_val}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee;">{ayon_path_val}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">v{version_val}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{length}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{frame_start}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eeeeee; text-align: center;">{frame_end}</td>
                </tr>
                """)
            
            rows_html = "\n".join(html_rows)
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        color: #333333;
                        margin: 0;
                        padding: 0;
                    }}
                    h1 {{
                        font-size: 24pt;
                        color: #111111;
                        margin: 0 0 8px 0;
                    }}
                    .subtitle {{
                        font-size: 11pt;
                        color: #666666;
                        margin: 0 0 20px 0;
                        line-height: 1.4;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                    }}
                    th {{
                        background-color: #f7f7f7;
                        border-bottom: 2px solid #dddddd;
                        color: #222222;
                        font-weight: bold;
                        font-size: 11pt;
                        padding: 8px;
                        text-align: left;
                    }}
                    td {{
                        font-size: 10pt;
                        padding: 8px;
                        border-bottom: 1px solid #eeeeee;
                        vertical-align: middle;
                    }}
                </style>
            </head>
            <body>
                <h1>Ingest Report</h1>
                <div class="subtitle">
                    <strong>Local:</strong> {date_time_a}<br/>
                    <strong>Client:</strong> {date_time_b}
                </div>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 85px; text-align: center;">Thumbnail</th>
                            <th>File Name</th>
                            <th>Variant</th>
                            <th>Ayon Folder</th>
                            <th style="width: 55px; text-align: center;">Version</th>
                            <th style="width: 70px; text-align: center;">Length (frames)</th>
                            <th style="width: 65px; text-align: center;">Frame Start</th>
                            <th style="width: 65px; text-align: center;">Frame End</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </body>
            </html>
            """
            
            # 4. Write to PDF using QPdfWriter
            from PySide6.QtGui import QPdfWriter, QTextDocument, QPageLayout, QPageSize
            from PySide6.QtCore import QMarginsF
            
            writer = QPdfWriter(pdf_path)
            writer.setPageSize(QPageSize(QPageSize.A4))
            
            # Landscape orientation with half-sized margins (7.5mm)
            layout = QPageLayout(
                QPageSize(QPageSize.A4),
                QPageLayout.Landscape,
                QMarginsF(7.5, 7.5, 7.5, 7.5),
                QPageLayout.Millimeter
            )
            writer.setPageLayout(layout)
            
            doc = QTextDocument()
            doc.setHtml(html_content)
            doc.print_(writer)
            
            self.log_message(f"Ingest PDF report generated successfully: {os.path.basename(pdf_path)}", "success")
        except Exception as e:
            self.log_message(f"Failed to generate Ingest PDF report: {e}", "error")

    def perform_paste_image(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            self.log_message("No image found in clipboard.", "warning")
            return

        # 1. Resolve path from Preferences
        import datetime
        now = datetime.datetime.now()
        yy = now.strftime("%y")
        mm = now.strftime("%m")
        dd = now.strftime("%d")
        
        default_root = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Downloads")
        from utils import expand_env_vars
        root = expand_env_vars(self.config.get("clip_temp_root", default_root))
        folder_tpl = self.config.get("clip_folder_template", "IngestDesktop_{yy}{mm}{dd}")
        folder_name = folder_tpl.replace("{yy}", yy).replace("{mm}", mm).replace("{dd}", dd)
        
        target_dir = os.path.normpath(os.path.join(root, folder_name))
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
        except Exception as e:
            self.log_message(f"Failed to create temp directory: {e}", "error")
            return
            
        # 2. Resolve filename
        prefix = self.config.get("clip_file_prefix", "clipboard")
        padding = self.config.get("clip_file_counter", 3)
        
        # Find next counter
        try:
            existing = [f for f in os.listdir(target_dir) if f.startswith(prefix) and f.endswith(".png")]
        except:
            existing = []
            
        next_num = 1
        if existing:
            import re
            nums = []
            safe_prefix = re.escape(prefix)
            # Match prefix, then underscore, then digits, then .png
            pattern = rf"^{safe_prefix}_(\d+)\.png$"
            for f in existing:
                match = re.search(pattern, f)
                if match:
                    nums.append(int(match.group(1)))
            if nums:
                next_num = max(nums) + 1
        
        file_name = f"{prefix}_{str(next_num).zfill(padding)}.png"
        file_path = os.path.join(target_dir, file_name)
        
        # 3. Save as 24-bit PNG
        try:
            # Convert to RGB888 for 24bit
            image_24 = image.convertToFormat(QImage.Format_RGB888)
            if image_24.save(file_path, "PNG"):
                self.log_message(f"Clipboard image saved: {file_path}", "success")
            else:
                self.log_message(f"Failed to save image to {file_path}", "error")
                return
        except Exception as e:
            self.log_message(f"Error saving clipboard image: {e}", "error")
            return
        
        # 4. Set source folder and rescan
        self.top_bar.set_path(target_dir)
        self.start_scan(target_dir)

    def perform_publish_deadline(self):
        # Stop all playback before sending items to deadline
        if hasattr(self, "thumb_area") and hasattr(self.thumb_area, "video_player"):
            try:
                self.thumb_area.video_player.clear_video()
            except Exception:
                pass

        # 1. Detect deadlinecommand
        import os
        import shutil
        import subprocess
        
        deadline_path = os.environ.get("DEADLINE_PATH", "")
        deadline_bin = None
        if deadline_path:
            exe_name = "deadlinecommand.exe" if os.name == 'nt' else "deadlinecommand"
            candidate = os.path.join(deadline_path, exe_name)
            if os.path.exists(candidate):
                deadline_bin = candidate
                
        if not deadline_bin:
            deadline_bin = shutil.which("deadlinecommand")
            
        if not deadline_bin:
            self.log_message("Error: deadlinecommand executable not found. Make sure DEADLINE_PATH environment variable is set.", "error")
            QMessageBox.critical(self, "Deadline Error", "deadlinecommand.exe not found! Please check your DEADLINE_PATH environment variable.")
            return

        # 2. Gather selected items
        selected_items = []
        selected_thumbs = self.thumb_area.scene.selectedItems()
        if selected_thumbs:
            selected_items = [thumb.data for thumb in selected_thumbs]
        else:
            selection_model = self.spreadsheet.table.selectionModel()
            selected_indexes = selection_model.selectedRows()
            if selected_indexes:
                for idx in selected_indexes:
                    row = idx.row()
                    if row < len(self.model.items):
                        selected_items.append(self.model.items[row])

        def requires_review(item):
            p_data = item.preset_data or {}
            return item.review_status == "waiting" or p_data.get("Convert Review", True)

        # 3. Filter review items based on selection
        if selected_items:
            review_items = [item for item in selected_items if requires_review(item)]
            if not review_items:
                QMessageBox.information(self, "Deadline", "None of the selected items require review conversion.")
                return
        else:
            review_items = [item for item in self.model.items if requires_review(item)]
            if not review_items:
                QMessageBox.information(self, "Deadline", "No items in the project require review conversion.")
                return

        # 4. Confirm with the user before submitting
        reply = QMessageBox.question(
            self,
            "Submit to Deadline",
            f"Are you sure you want to submit {len(review_items)} review conversion(s) to Deadline?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.No:
            return

        success_count = 0
        fail_count = 0
        
        self.log_message(f"Starting Deadline submission for {len(review_items)} jobs...", "info")
        
        for item in review_items:
            p_data = item.preset_data or {}
            cmd_template = p_data.get("Convert Review Command", "")
            if not cmd_template:
                self.log_message(f"Skipping {item.label}: No Convert Review Command preset defined.", "warning")
                item.review_status = "failed"
                self.model.layoutChanged.emit()
                fail_count += 1
                continue
                
            # Temporarily replace executable paths with backslashes for Deadline
            orig_ffmpeg = self.model.ffmpeg_path
            orig_ffprobe = self.model.ffprobe_path
            orig_oiiotool = self.model.oiiotool_path
            orig_vfxtranscode = self.model.vfxtranscode
            
            self.model.ffmpeg_path = (self.model.ffmpeg_path or "").replace("/", "\\")
            self.model.ffprobe_path = (self.model.ffprobe_path or "").replace("/", "\\")
            self.model.oiiotool_path = (self.model.oiiotool_path or "").replace("/", "\\")
            self.model.vfxtranscode = (self.model.vfxtranscode or "").replace("/", "\\")
            
            # Expand tokens
            cmd = self.model.expand_tokens(cmd_template, item)
            target_path = self.model.expand_tokens("{prefs_review_path}", item)
            
            # Restore original paths
            self.model.ffmpeg_path = orig_ffmpeg
            self.model.ffprobe_path = orig_ffprobe
            self.model.oiiotool_path = orig_oiiotool
            self.model.vfxtranscode = orig_vfxtranscode
            
            if not cmd or not target_path:
                self.log_message(f"Skipping {item.label}: Failed to evaluate tokens in command or review path.", "warning")
                item.review_status = "failed"
                self.model.layoutChanged.emit()
                fail_count += 1
                continue

            # Ensure all paths in cmd and target_path use backslashes
            cmd = cmd.replace("/", "\\")
            target_path = target_path.replace("/", "\\")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # Split executable and arguments
            import shlex
            try:
                tokens = shlex.split(cmd, posix=False)
            except Exception:
                tokens = cmd.split()
                
            executable = tokens[0] if tokens else ""
            if executable.startswith('"') and executable.endswith('"'):
                executable = executable[1:-1]
            elif executable.startswith("'") and executable.endswith("'"):
                executable = executable[1:-1]
                
            arguments = cmd[len(tokens[0]):].strip() if tokens else ""

            # Substitute Job Name Template
            name_template = self.secrets.get("deadline_job_name", "Encoding {label} Review for {ayon_path}/{ayon_task_name}")
            job_name = name_template.replace("{label}", item.label or "")
            job_name = job_name.replace("{ayon_path}", item.ayon_path or "")
            job_name = job_name.replace("{ayon_task_name}", item.ayon_task_name or "")

            # Build Job Info File
            job_info_content = [
                "Plugin=CommandLine",
                f"Name={job_name}",
                "Comment=Submitted via IngestDesktop",
                f"Department={self.secrets.get('deadline_department', 'io')}",
                f"Pool={self.secrets.get('deadline_pool', 'all')}",
                f"SecondaryPool={self.secrets.get('deadline_secondary_pool', 'all')}",
                f"Group={self.secrets.get('deadline_group', '2d_studio')}",
                f"Priority={int(self.secrets.get('deadline_priority', 50))}",
                f"MachineLimit={int(self.secrets.get('deadline_machine_limit', 1))}",
                f"ConcurrentTasks={int(self.secrets.get('deadline_concurrent_tasks', 1))}",
                "Frames=0",
                "ChunkSize=1"
            ]

            # Build Plugin Info File
            plugin_info_content = [
                "Shell=default",
                "ShellExecute=False",
                f"Executable={executable}",
                f"Arguments={arguments}",
                "StartupDirectory="
            ]

            import tempfile
            
            try:
                # Write files
                job_file = tempfile.NamedTemporaryFile(mode="w", suffix="_job.txt", delete=False, encoding="utf-8")
                job_file.write("\n".join(job_info_content))
                job_file.close()
                
                plugin_file = tempfile.NamedTemporaryFile(mode="w", suffix="_plugin.txt", delete=False, encoding="utf-8")
                plugin_file.write("\n".join(plugin_info_content))
                plugin_file.close()

                creationflags = 0
                if os.name == 'nt':
                    creationflags = 0x08000000 # CREATE_NO_WINDOW
                
                self.log_message(f"Submitting Deadline job for {item.label}...", "info")
                process = subprocess.Popen([deadline_bin, job_file.name, plugin_file.name],
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           text=True,
                                           creationflags=creationflags)
                stdout, stderr = process.communicate()
                
                # Cleanup temp files
                try:
                    os.remove(job_file.name)
                    os.remove(plugin_file.name)
                except Exception:
                    pass
                
                if process.returncode == 0:
                    self.log_message(f"Successfully submitted Deadline job for {item.label}: {stdout.strip()}", "success")
                    item.review_status = "submitted"
                    success_count += 1
                else:
                    err_msg = stderr or stdout or "Unknown error"
                    self.log_message(f"Failed to submit Deadline job for {item.label}: {err_msg.strip()}", "error")
                    item.review_status = "failed"
                    fail_count += 1
            except Exception as e:
                self.log_message(f"Exception while submitting Deadline job for {item.label}: {e}", "error")
                item.review_status = "failed"
                fail_count += 1
            
            self.model.layoutChanged.emit()

        summary_msg = f"Deadline Submission Finished. Success: {success_count}, Failed: {fail_count}."
        self.log_message(summary_msg, "success" if fail_count == 0 else "warning")
        QMessageBox.information(self, "Deadline Submission Summary", summary_msg)

    def _get_tagged_for_ingest(self):
        v_stack_enabled = getattr(self.model, "v_stack_enabled", False)
        tagged_items = [
            item for item in self.model.items 
            if item.is_tagged and (not v_stack_enabled or self.model.is_item_visible_by_v_stack(item, True))
        ]
        if not tagged_items:
            QMessageBox.warning(self, "Ingest", "No images tagged for ingest.")
            return None

        # 1. Check for duplicates (same label and AYON path)
        seen = set()
        duplicates = []
        for item in tagged_items:
            key = (item.label, item.ayon_path)
            if key in seen:
                duplicates.append(item)
            seen.add(key)
        
        if duplicates:
            QMessageBox.critical(self, "Ingest", f"Found {len(duplicates)} duplicate entries. Ingest stopped.")
            return None
        return tagged_items

    def _write_csv_from_preview(self, items, csv_path):
        """Write items to CSV using the column definitions from CSVPreviewModel."""
        column_defs = self.csv_preview_model.column_defs
        delimiter = self.config.get("csv_delimiter", ",")
        quotechar = self.config.get("csv_quotechar", '"')
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
            writer.writerow([h for h, t in column_defs])
            for item in items:
                # 1. Write the main item row
                row_data = []
                for h, template in column_defs:
                    val = self.model._expand_string(template, item, use_global_camel=True)
                    row_data.append(val)
                writer.writerow(row_data)
                
                # 2. Write the review row if the item has review
                review_path = self.model.expand_tokens("{prefs_review_path}", item)
                has_review = (item.review_status == "done") or (review_path and os.path.exists(review_path))
                if has_review:
                    row_data = []
                    for h, template in column_defs:
                        h_lower = h.lower()
                        if h_lower == "file path":
                            val = os.path.abspath(review_path).replace("\\", "/")
                        elif h_lower == "representation":
                            p_data = item.preset_data or {}
                            val = p_data.get("Review Representation", "h264")
                        elif h_lower == "representation colorspace":
                            p_data = item.preset_data or {}
                            val = p_data.get("Review Colorspace", "Output - sRGB")
                        elif h_lower == "representation tags":
                            p_data = item.preset_data or {}
                            val = p_data.get("Review Tags", "passing;ftracreview;webreview")
                        else:
                            val = self.model._expand_string(template, item, use_global_camel=True)
                        row_data.append(val)
                    writer.writerow(row_data)

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
        try:
            self.filter_panel.tree.selectionModel().selectionChanged.disconnect(self._sync_selection_from_filter)
        except (RuntimeError, TypeError):
            pass
        self.filter_panel.tree.selectionModel().selectionChanged.connect(self._sync_selection_from_filter)

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
        self.filter_panel.set_scene_items(summaries)

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

    def _sync_selection_from_filter(self, selected=None, deselected=None):
        """Sync selection from FilterPanel tree to Thumbs and Table."""
        if self._selection_lock: return
        
        # Get selected paths from tree
        selected_indexes = self.filter_panel.tree.selectionModel().selectedIndexes()
        paths = set()
        is_csv = self.spreadsheet._is_csv_mode
        for idx in selected_indexes:
            if idx.column() == 0:
                source_idx = self.filter_panel.proxy.mapToSource(idx)
                
                # Get the actual source model
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
                        for it in items_list:
                            if os.path.normpath(os.path.abspath(it.file_path)).lower() == norm_p:
                                is_known_item_path = True
                                break
                    
                    if isinstance(path, str) and (is_path_model or os.path.isabs(path) or os.path.exists(path) or is_known_item_path):
                        paths.add(os.path.normpath(os.path.abspath(path)))
                    elif not isinstance(path, dict):
                        # Use only hashable IDs (ints/strings)
                        paths.add(path)
                    elif isinstance(path, dict) and "id" in path:
                        # Fallback for old model data if any
                        paths.add(path["id"])
        
        if not paths: return
        
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
            
            for i, item in enumerate(items_list):
                item_abs = os.path.normpath(os.path.abspath(item.file_path))
                item_abs_lower = item_abs.lower()
                is_selected = False
                for p in paths:
                    # Only compare strings as paths
                    if isinstance(p, str):
                        p_lower = p.lower()
                        if item_abs_lower == p_lower or item_abs_lower.startswith(p_lower + os.sep):
                            is_selected = True
                            break
                
                if is_selected:
                    # Select in table
                    idx = target_model.index(i, 0)
                    tl = target_model.index(i, 0)
                    br = target_model.index(i, target_model.columnCount() - 1)
                    selection.select(tl, br)
                    if first_idx is None: first_idx = idx
                    
                    # Select in thumbs
                    if item in self.thumb_area.item_to_thumb:
                        self.thumb_area.item_to_thumb[item].setSelected(True)
            
            # 3. Sync Scene Items (Backdrops/Notes)
            for p in paths:
                if not isinstance(p, str) or not (os.path.isabs(p) or os.path.exists(p)):
                    # Check for scene items by UUID
                    try:
                        for scene_item in self.thumb_area.scene.items():
                            if hasattr(scene_item, "uuid") and scene_item.uuid == p:
                                scene_item.setSelected(True)
                                break
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

    def _on_add_comment(self, comment):
        if not comment: return
        
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedRows()
        
        if not selected_indexes:
            self.log_message("No items selected to add comment to.", "warning")
            return
            
        is_csv = self.spreadsheet._is_csv_mode
        count = 0
        for idx in selected_indexes:
            row = idx.row()
            if is_csv:
                if row < len(self.csv_preview_model.tagged_items):
                    item = self.csv_preview_model.tagged_items[row]
                    item.comment = comment
                    count += 1
            else:
                if row < len(self.model.items):
                    item = self.model.items[row]
                    item.comment = comment
                    count += 1
            
        # Refresh views
        self.csv_preview_model.layoutChanged.emit()
        self.log_message(f"Added comment to {count} items.", "success")

    def _on_filter_search_changed(self, text):
        if self._selection_lock: return
        self._search_filter_text = text.lower()
        
        # Trigger re-filtering in both views
        self.spreadsheet.update_filtering(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=self._search_filter_text
        )
        self.thumb_area.rearrange_items(
            age_filter=(self._age_filter_enabled, self._age_filter_value),
            search_text=self._search_filter_text
        )
        
        # Save search state immediately
        self.config["filter_search_text"] = text
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

    def closeEvent(self, event):
        """Save state before closing."""
        self.config["geometry"] = self.saveGeometry().toHex().data().decode()
        self.config["h_splitter"] = self.h_splitter.saveState().toHex().data().decode()
        self.config["v_splitter"] = self.v_splitter.saveState().toHex().data().decode()
        if hasattr(self, 'center_top_splitter'):
            self.config["center_top_splitter"] = self.center_top_splitter.saveState().toHex().data().decode()
        
        self.save_config()
        super().closeEvent(event)

    def toggle_maximize(self, source="thumbs"):
        """Toggle maximize state of the middle panel or spreadsheet."""
        from PySide6.QtCore import QPoint
        
        # Save a reference scene point and its screen position to keep items stable on screen
        scene_point = None
        global_pos = None
        if source == "thumbs" and self.thumb_area.isVisible():
            scene_point = self.thumb_area.view.mapToScene(0, 0)
            global_pos = self.thumb_area.view.viewport().mapToGlobal(QPoint(0, 0))

        if not self._is_maximized:
            # Maximize
            self._last_h_state = self.h_splitter.saveState()
            self._last_v_state = self.v_splitter.saveState()
            
            self.ayon_panel.hide()
            self.filter_panel.hide()
            self.top_bar.hide()
            self.btn_export_csv.hide()
            self.btn_publish_local.hide()
            self.btn_publish_deadline.hide()
            
            if source == "thumbs":
                self.spreadsheet.hide()
                self.thumb_area.btn_maximize.setText("Restore")
                self.thumb_area.btn_maximize.setChecked(True)
            else:
                self.thumb_area.hide()
            
            self._is_maximized = True
        else:
            # Restore
            self.ayon_panel.show()
            self.filter_panel.show()
            self.spreadsheet.show()
            self.thumb_area.show()
            self.top_bar.show()
            self.btn_export_csv.show()
            self.btn_publish_local.show()
            self.btn_publish_deadline.show()
            
            self.thumb_area.btn_maximize.setText("Maximize")
            self.thumb_area.btn_maximize.setChecked(False)
            
            if self._last_h_state:
                self.h_splitter.restoreState(self._last_h_state)
            if self._last_v_state:
                self.v_splitter.restoreState(self._last_v_state)
            
            self._is_maximized = False
        
        # Keep view zoom and pan untouched during maximize/restore; compensate for top/left panels so thumbnails do not move on screen
        if scene_point and global_pos:
            def restore_pan():
                if not self.thumb_area.isVisible():
                    return
                viewport = self.thumb_area.view.viewport()
                new_global_pos = viewport.mapToGlobal(QPoint(0, 0))
                target_viewport_pixel = global_pos - new_global_pos
                
                W = viewport.width()
                H = viewport.height()
                C_v = QPoint(W // 2, H // 2)
                
                scene_center = self.thumb_area.view.mapToScene(C_v)
                scene_target = self.thumb_area.view.mapToScene(target_viewport_pixel)
                
                new_scene_center = scene_point + (scene_center - scene_target)
                self.thumb_area.view.centerOn(new_scene_center)
                self.thumb_area.update_zoom_indicator()
            
            QTimer.singleShot(0, restore_pan)

    def _on_ayon_task_selected(self, folder_path, task_name, task_type, assignee=""):
        """Assign AYON path to selected items."""
        # Get selected rows robustly
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        if not selected_rows:
            # Check thumbnails fallback
            selected_thumbs = self.thumb_area.scene.selectedItems()
            if selected_thumbs:
                for thumb in selected_thumbs:
                    try:
                        row = self.model.items.index(thumb.data)
                        selected_rows.append(row)
                    except ValueError: continue
                selected_rows = sorted(list(set(selected_rows)))

        if not selected_rows:
            self.log_message("No images selected to assign path to.", "warning")
            return
            
        ayon_path = f"{folder_path}/{task_name}"
        for row in selected_rows:
            item = self.model.items[row]
            item.ayon_path = ayon_path
            item.ayon_task_name = task_name
            item.ayon_task_type = task_type
            item.ayon_task_assignee = assignee
            
        # Notify the model that the AYON Path column (10) has changed for these rows
        start_idx = self.model.index(min(selected_rows), 10)
        end_idx = self.model.index(max(selected_rows), 10)
        self.model.dataChanged.emit(start_idx, end_idx)
        
        # Feedback
        self.log_message(f"Assigned '{ayon_path}' to {len(selected_rows)} items.")

    def _on_ayon_product_selected(self, folder_path, task_name, task_type, variant):
        """Assign AYON path AND update label to variant for selected items."""
        # 1. Set the AYON path (reuse existing logic)
        self._on_ayon_task_selected(folder_path, task_name, task_type)
        
        # 2. Update the labels for the same selected items
        # Re-fetching selection to be safe, though _on_ayon_task_selected doesn't clear it
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        selected_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        # Fallback to thumbs selection
        if not selected_rows:
            selected_thumbs = self.thumb_area.scene.selectedItems()
            if selected_thumbs:
                for thumb in selected_thumbs:
                    try:
                        row = self.model.items.index(thumb.data)
                        selected_rows.append(row)
                    except ValueError: continue
                selected_rows = sorted(list(set(selected_rows)))
                
        if not selected_rows:
            return
            
        for row in selected_rows:
            item = self.model.items[row]
            item.label = variant
            
        # Notify model that Label column (2) has changed
        start_idx = self.model.index(min(selected_rows), 2)
        end_idx = self.model.index(max(selected_rows), 2)
        self.model.dataChanged.emit(start_idx, end_idx)
        
        # Feedback
        self.log_message(f"Updated labels to '{variant}' for {len(selected_rows)} items.", "success")

    def _update_ayon_visuals(self):
        """Highlight assigned tasks in the AYON panel."""
        assigned_paths = set(item.ayon_path for item in self.model.items if item.ayon_path)
        if hasattr(self, "_last_assigned_paths") and self._last_assigned_paths == assigned_paths:
            self.update_ayon_thumbnails()
            return
        self._last_assigned_paths = assigned_paths
        self.ayon_panel.update_assigned_status(assigned_paths)
        self.update_ayon_thumbnails()

    def _on_ayon_unassign(self, ayon_path):
        """Clear AYON path for all items assigned to this path."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path == ayon_path:
                item.ayon_path = ""
                item.ayon_task_name = ""
                item.ayon_task_type = ""
                item.ayon_task_assignee = ""
                affected += 1
        
        if affected:
            self.model.dataChanged.emit(self.model.index(0, 7), self.model.index(len(self.model.items)-1, 7))
            self.log_message(f"Unassigned '{ayon_path}' from {affected} items.")
            # Bold status will update via dataChanged signal -> _update_ayon_visuals

    def _on_ayon_select_assigned(self, ayon_path):
        """Select all items that have this AYON path."""
        is_csv = self.spreadsheet._is_csv_mode
        target_model = self.csv_preview_model if is_csv else self.model
        items_list = self.csv_preview_model.tagged_items if is_csv else self.model.items
        
        selection_model = self.spreadsheet.table.selectionModel()
        selection_model.clearSelection()
        
        selection = QItemSelection()
        first_idx = None
        count = 0
        
        for i, item in enumerate(items_list):
            if item.ayon_path == ayon_path:
                idx = target_model.index(i, 0)
                # Select the full row
                tl = target_model.index(i, 0)
                br = target_model.index(i, target_model.columnCount() - 1)
                selection.select(tl, br)
                if first_idx is None: first_idx = idx
                count += 1
        
        if not selection.isEmpty():
            selection_model.select(selection, QItemSelectionModel.Select)
            if first_idx:
                self.spreadsheet.table.scrollTo(first_idx)
            self.log_message(f"Selected {count} items assigned to '{ayon_path}'.")
            
            # Sync to Thumbs and Filter Panel
            self._sync_selection_to_thumbs()
        else:
            self.log_message(f"No items assigned to '{ayon_path}' found.", "warning")

    def _on_ayon_clear_all(self):
        """Reset all AYON path assignments."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path:
                item.ayon_path = ""
                item.ayon_task_name = ""
                item.ayon_task_type = ""
                item.ayon_task_assignee = ""
                affected += 1
        
        if affected:
            # Column 10 is AYON Path
            self.model.dataChanged.emit(self.model.index(0, 10), self.model.index(len(self.model.items)-1, 10))
            self.log_message(f"Cleared all AYON assignments from {affected} items.", "warning")

    def _on_ayon_info_requested(self, folder_id):
        """Lazy load products for the selected folder."""
        project = self.ayon_panel.combo_project.currentText()
        if not project: return
        
        if hasattr(self, "_prod_thread") and self._prod_thread.isRunning():
            try:
                self._prod_thread.finished.disconnect()
            except Exception:
                pass
            self._prod_thread.terminate()
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._prod_thread)

        class ProductThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project, f_id):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.f_id = f_id
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull products for folder ID '{self.f_id}' in project '{self.project}' from AYON...")
                products = self.ayon.get_products_for_folder(self.project, self.f_id)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling products for folder ID '{self.f_id}' in project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(products)

        self._prod_thread = ProductThread(self.ayon, project, folder_id)
        self._prod_thread.finished.connect(self.ayon_panel.set_products)
        self._prod_thread.start()

    def _on_show_thumbs_toggled(self, checked):
        print(f"[Debug] Show Thumbs toggled: {checked}")
        self.log_message(f"[Debug] Show Thumbs toggled: {checked}", "info")
        self.model.show_thumbs = checked
        if checked:
            self.update_ayon_thumbnails()
            self.trigger_ayon_thumbnail_downloads()
        self.model.layoutChanged.emit()
        self._refresh_ayon_panel_icons()

    def _refresh_ayon_panel_icons(self):
        show_thumbs = self.ayon_panel.btn_show_thumbs.isChecked()
        cache_root = self.config.get("ayon_thumbnails_cache", "")
        if not cache_root:
            cache_root = "_ayon_thumbs_cache"
        from utils import expand_env_vars
        cache_root = expand_env_vars(cache_root)
        
        project_name = self.ayon_panel.combo_project.currentText()
        if project_name:
            self.ayon_panel.refresh_icons(show_thumbs, cache_root, project_name)

    def trigger_ayon_thumbnail_downloads(self):
        if not self.config.get("get_ayon_thumbnails", True):
            self.log_message("AYON task thumbnails download is disabled in preferences.", "info")
            return

        if not self.ayon_panel.btn_show_thumbs.isChecked():
            return

        project_name = self.ayon_panel.combo_project.currentText()
        if not project_name:
            return

        # Find all task thumbnail IDs from the current tree
        tasks_info = []
        def _recurse_model(parent_item):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item:
                    continue
                data = item.data(Qt.UserRole)
                if data and "folderId" in data: # It's a task!
                    thumb_id = data.get("thumbnailId")
                    if thumb_id:
                        tasks_info.append({
                            "name": data.get("name"),
                            "thumbnailId": thumb_id
                        })
                _recurse_model(item)

        _recurse_model(self.ayon_panel.model.invisibleRootItem())
        
        if not tasks_info:
            return
            
        if hasattr(self, "_ayon_thumb_download_thread") and self._ayon_thumb_download_thread.isRunning():
            return # Let the current run finish
            
        cache_root = self.config.get("ayon_thumbnails_cache", "")
        if not cache_root:
            cache_root = "_ayon_thumbs_cache"
        from utils import expand_env_vars
        cache_root = expand_env_vars(cache_root)
        
        project_cache_dir = os.path.join(cache_root, project_name)
        
        # Filter tasks_info based on local disk state and known states
        filtered_tasks_info = []
        changed = False
        for info in tasks_info:
            thumb_id = info["thumbnailId"]
            target_path = os.path.join(project_cache_dir, f"{thumb_id}.jpg")
            
            if os.path.exists(target_path):
                if self.ayon_thumb_states.get(thumb_id) != "cached":
                    self.ayon_thumb_states[thumb_id] = "cached"
                    changed = True
                continue
                
            state = self.ayon_thumb_states.get(thumb_id)
            if state in ("not available", "downloading", "downloaded", "cached"):
                continue
                
            filtered_tasks_info.append(info)
            self.ayon_thumb_states[thumb_id] = "downloading"
            changed = True
            
        if changed:
            self.save_ayon_thumb_states()
            
        if not filtered_tasks_info:
            self._refresh_ayon_panel_icons()
            return
            
        self._ayon_thumb_download_thread = AyonThumbnailDownloadThread(
            project_name, filtered_tasks_info, project_cache_dir
        )
        self._ayon_thumb_download_thread.log.connect(lambda msg: self.log_message(msg, "info"))
        self._ayon_thumb_download_thread.state_changed.connect(self._on_task_thumb_state_changed)
        self._ayon_thumb_download_thread.finished.connect(self._refresh_ayon_panel_icons)
        self._ayon_thumb_download_thread.start()

    def load_ayon_thumb_states(self):
        cache_root = self.config.get("ayon_thumbnails_cache", "")
        if not cache_root:
            cache_root = "_ayon_thumbs_cache"
        from utils import expand_env_vars
        cache_root = expand_env_vars(cache_root)
        os.makedirs(cache_root, exist_ok=True)
        
        path = os.path.join(cache_root, "ayon_thumb_states.json")
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    self.ayon_thumb_states = json.load(f)
                print(f"[Prefs] Loaded AYON thumbnail states from: {path}")
            except Exception as e:
                print(f"Error loading AYON thumbnail states: {e}")
                self.ayon_thumb_states = {}
        else:
            self.ayon_thumb_states = {}

    def save_ayon_thumb_states(self):
        cache_root = self.config.get("ayon_thumbnails_cache", "")
        if not cache_root:
            cache_root = "_ayon_thumbs_cache"
        from utils import expand_env_vars
        cache_root = expand_env_vars(cache_root)
        os.makedirs(cache_root, exist_ok=True)
        
        path = os.path.join(cache_root, "ayon_thumb_states.json")
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.ayon_thumb_states, f, indent=4)
        except Exception as e:
            print(f"Error saving AYON thumbnail states: {e}")

    def _on_task_thumb_state_changed(self, thumb_id, state):
        self.ayon_thumb_states[thumb_id] = state
        self.save_ayon_thumb_states()


    def update_ayon_thumbnails(self):
        if not getattr(self.model, "show_thumbs", False):
            return
            
        project = self.ayon_panel.combo_project.currentText()
        if not project:
            return
            
        path_map = self.ayon_panel.get_path_to_id_map()
        if not path_map:
            return
            
        changed = False
        for item in self.model.items:
            if not item.ayon_path:
                print(f"debug: ayon_path is empty for item: {item}")
                continue
                
            # ayon_path is /Project/Folder/Task - we need the folder path
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            
            if not f_id:
                print(f"debug: f_id not found for folder path '{folder_path}' in path_map")
                continue
                
            if f_id in self.ayon_thumb_cache:
                print(f"debug: f_id '{f_id}' found in ayon_thumb_cache for item: {item}")
                item.ayon_thumbnail = self.ayon_thumb_cache[f_id]
                continue
                
            # Check local file first
            try:
                local_thumb_path = self._get_ayon_thumb_path(item)
                if os.path.exists(local_thumb_path):
                    from PySide6.QtGui import QPixmap
                    pixmap = QPixmap(local_thumb_path)
                    if not pixmap.isNull():
                        self.ayon_thumb_cache[f_id] = pixmap
                        if self.ayon_thumb_states.get(f_id) != "cached":
                            self.ayon_thumb_states[f_id] = "cached"
                            changed = True
                        item.ayon_thumbnail = pixmap
                        item.thumbnail = pixmap
                        continue
            except Exception as e:
                print(f"Error checking/loading local thumbnail: {e}")
                
            state = self.ayon_thumb_states.get(f_id)
            if state in ("not available", "downloading", "downloaded", "cached"):
                continue
                
            # If not cached and not currently downloading, start download
            print(f"Downloading thumbnail for folder ID '{f_id}' in project '{project}' from AYON...")
            self.ayon_thumb_states[f_id] = "downloading"
            changed = True
            self.ayon_thumb_downloading.add(f_id)
            
            # Start background thread
            thread = AyonFolderThumbnailThread(self.ayon, project, f_id)
            thread.download_finished.connect(self._on_ayon_thumbnail_downloaded)
            # Keep thread reference
            self._thumb_threads.append(thread)
            thread.start()

        if changed:
            self.save_ayon_thumb_states()

    def _get_ayon_thumb_path(self, item):
        """Construct a thumbnail path using AYON folder path, replacing slashes with dashes, adding suffix '_thumbAyon'."""
        import os
        source_file = item.file_path.replace("\\", "/")
        base_dir = os.path.dirname(source_file)
        
        target_dir = base_dir
        thumb_loc = self.config.get("thumb_location", "Relative to Source Folder")
        thumb_loc_path = self.config.get("thumb_location_path", "_thumbs")
        
        if thumb_loc == "Relative to Source Folder":
            if self.model.source_folder:
                target_dir = os.path.join(self.model.source_folder, thumb_loc_path).replace("\\", "/")
        elif thumb_loc == "Custom":
            target_dir = thumb_loc_path.replace("\\", "/")
            
        # Get AYON folder path
        folder_path = "/".join(item.ayon_path.split("/")[:-1])
        clean_path = folder_path.strip("/")
        dashed_path = clean_path.replace("/", "-")
        
        # Suffix and format
        ext = self.config.get("thumb_format", ".jpg")
        target_filename = f"{dashed_path}_thumbAyon{ext}"
        
        return os.path.join(target_dir, target_filename).replace("\\", "/")

    def _on_ayon_thumbnail_downloaded(self, folder_id, data):
        # Remove completed threads from tracking
        self._thumb_threads = [t for t in self._thumb_threads if t.isRunning()]
        
        if folder_id in self.ayon_thumb_downloading:
            self.ayon_thumb_downloading.remove(folder_id)
            
        if data:
            from PySide6.QtGui import QImage, QPixmap
            image = QImage()
            if image.loadFromData(data):
                pixmap = QPixmap.fromImage(image)
                # Cache it
                self.ayon_thumb_cache[folder_id] = pixmap
                self.ayon_thumb_states[folder_id] = "downloaded"
                
                # Assign to all items with matching folder path
                path_map = self.ayon_panel.get_path_to_id_map()
                if path_map:
                    for item in self.model.items:
                        if item.ayon_path:
                            folder_path = "/".join(item.ayon_path.split("/")[:-1])
                            f_id = path_map.get(folder_path)
                            if f_id == folder_id:
                                item.ayon_thumbnail = pixmap
                                try:
                                    local_thumb_path = self._get_ayon_thumb_path(item)
                                    import os
                                    os.makedirs(os.path.dirname(local_thumb_path), exist_ok=True)
                                    print(f"[Debug] Storing AYON thumbnail locally to: {local_thumb_path}")
                                    self.log_message(f"[Debug] Storing AYON thumbnail locally to: {local_thumb_path}", "info")
                                    with open(local_thumb_path, "wb") as f:
                                        f.write(data)
                                    item.thumbnail = pixmap
                                except Exception as e:
                                    print(f"Failed to save AYON thumbnail locally: {e}")
                
                # Refresh views
                self.model.layoutChanged.emit()
                if self.spreadsheet._is_csv_mode:
                    self.csv_preview_model._refresh_data()
            else:
                self.ayon_thumb_states[folder_id] = "not available"
        else:
            self.ayon_thumb_states[folder_id] = "not available"
        self.save_ayon_thumb_states()

    def _on_ayon_representations_requested(self, project, product_id):
        """Asynchronously load representations for the selected product."""
        if not project or not product_id:
            return
            
        if hasattr(self, "_repre_thread") and self._repre_thread.isRunning():
            try:
                self._repre_thread.finished.disconnect()
            except Exception:
                pass
            self._repre_thread.terminate()
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._repre_thread)

        class RepreThread(QThread):
            finished = Signal(list)
            def __init__(self, ayon, project, prod_id):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.prod_id = prod_id
            def run(self):
                import time
                import ayon_api
                try:
                    start_t = time.perf_counter()
                    print(f"[Timer] Starting to pull representations for product ID '{self.prod_id}' in project '{self.project}' from AYON...")
                    
                    # 1. Fetch versions for this product
                    versions = list(ayon_api.get_versions(self.project, product_ids=[self.prod_id]))
                    v_ids = [v.get('id') for v in versions]
                    
                    # 2. Fetch representations
                    repres = []
                    if v_ids:
                        repres = list(ayon_api.get_representations(self.project, version_ids=v_ids))
                        
                    elapsed = time.perf_counter() - start_t
                    print(f"[Timer] Pulling representations took {elapsed:.4f} seconds.")
                    self.finished.emit(repres)
                except Exception as e:
                    print(f"Error fetching representations in thread: {e}")
                    self.finished.emit([])

        self._repre_thread = RepreThread(self.ayon, project, product_id)
        self._repre_thread.finished.connect(self.ayon_panel.set_representations)
        self._repre_thread.start()

    def _parse_item_tags(self, item):
        """Parse filename using regexes and store in item.metadata."""
        filename = os.path.splitext(os.path.basename(item.file_path))[0]
        
        # Version
        v_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        if v_regex:
            v_match = re.search(v_regex, filename)
            if v_match:
                try:
                    groups = v_match.groups()
                    if len(groups) >= 2:
                        item.version = int(groups[1])
                    elif len(groups) == 1:
                        item.version = int(groups[0])
                except (ValueError, IndexError):
                    pass
        
        # New Tags
        tag_regexes = {
            "folder_name": self.config.get("folder_regex"),
            "task_name": self.config.get("task_regex"),
            "sequence": self.config.get("sequence_regex"),
            "episode": self.config.get("episode_regex")
        }
        
        for tag, pattern in tag_regexes.items():
            if tag == "task_name" and self.config.get("fixed_task_name_enabled", False):
                val = self.config.get("fixed_task_name", "")
                item.metadata["task_name"] = val
                logging.info(f"Using fixed task_name={val} for {filename}")
                continue
                
            if not pattern: continue
            try:
                match = re.search(pattern, filename)
                if match and match.groups():
                    val = match.group(1)
                    item.metadata[tag] = val
                    logging.info(f"Parsed tag {tag}={val} from {filename}")
                else:
                    logging.debug(f"Regex {tag} did not match {filename} with pattern {pattern}")
            except re.error as e:
                logging.error(f"Regex error for {tag}: {e}")
                continue

    def perform_auto_assign(self):
        """Automatically match scanned items to AYON paths based on leaf folder names."""
        if not self.ayon.is_connected:
            self.log_message("AYON is not connected. Cannot auto-assign.", "error")
            return
            
        # 1. Get items to process (selection or all)
        items_to_process = []
        selected_thumbs = self.thumb_area.scene.selectedItems()
        if selected_thumbs:
            items_to_process = [thumb.data for thumb in selected_thumbs]
        else:
            # Check table selection
            selection_model = self.spreadsheet.table.selectionModel()
            selected_indexes = selection_model.selectedRows()
            if selected_indexes:
                items_to_process = [self.model.items[idx.row()] for idx in selected_indexes]
            else:
                # Process all items
                items_to_process = self.model.items
        
        if not items_to_process:
            self.log_message("No items to auto-assign.", "warning")
            return
            
        multi_match = self.config.get("auto_assign_multi_match", False)
        fallback_task = self.config.get("auto_assign_fallback_task", False)
        
        count = 0
        for item in items_to_process:
            # 1. Parse tags from filename
            self._parse_item_tags(item)
            
            # 2. Get names for matching
            folder_name = item.metadata.get("folder_name")
            if not folder_name:
                # Fallback to leaf folder name of the local path
                folder_name = os.path.basename(os.path.dirname(item.file_path))
            
            if not folder_name:
                continue
                
            if self.config.get("fixed_task_name_enabled", False):
                task_name = self.config.get("fixed_task_name", "")
            else:
                task_name = item.metadata.get("task_name")
                
            match = self.ayon_panel.find_best_match(
                folder_name, 
                task_name=task_name,
                multi_match=multi_match, 
                fallback_task=fallback_task
            )
            
            if match:
                ayon_path = f"{match['folder_path']}/{match['task_name']}"
                if item.ayon_path != ayon_path:
                    item.ayon_path = ayon_path
                    item.ayon_task_name = match.get("task_name", "")
                    item.ayon_task_type = match.get("task_type", "")
                    item.ayon_task_assignee = match.get("assignee", "")
                    count += 1
        
        if count:
            # Column 10 is AYON Path
            self.model.dataChanged.emit(self.model.index(0, 10), self.model.index(len(self.model.items)-1, 10))
            self.log_message(f"Auto-assigned {count} items based on folder name matches.", "success")
            self._update_ayon_visuals()
        else:
            self.log_message("No automatic matches found.")

    def perform_duplicate_check(self):
        """Identify items sharing same {ayon_path}{product_name}{version} strings."""
        self.log_message("Starting duplicate check...")
        
        is_csv = self.spreadsheet._is_csv_mode
        
        # 1. Gather candidate items based on criteria
        # - tagged on
        # - valid AYON path assigned (only required if not in CSV mode)
        # - visible according to current UI filters
        candidates = []
        for item in self.model.items:
            item.is_duplicate = False # Reset status for all
            
            if not item.is_tagged:
                continue
            
            if not is_csv and not item.ayon_path:
                continue
            
            if not is_csv:
                # Check if fits the right filter panel
                age_min = item.age_minutes
                label = item.label
                matches_search = not self._search_filter_text or self._search_filter_text in label.lower()
                matches_age = not self._age_filter_enabled or (age_min <= self._age_filter_value)
                
                if not (matches_search and matches_age):
                    continue
            
            candidates.append(item)

        if not candidates:
            self.log_message("No candidate items (tagged, assigned, and filtered) for duplicate check.", "warning")
            self.model.layoutChanged.emit()
            if is_csv:
                self.csv_preview_model._refresh_data()
            return

        # 2. Group by identity string: {ayon_path}{product_name}{version}
        identity_map = {}
        for item in candidates:
            # Product name expanded from template
            prod_name = self.model._expand_string(self.model.product_name_template, item, use_global_camel=True)
            ayon_path_val = item.ayon_path or ""
            identity = f"{ayon_path_val}{prod_name}{item.version}"
            
            if identity not in identity_map:
                identity_map[identity] = []
            identity_map[identity].append(item)

        # 3. Mark items in groups with more than one item as duplicates
        duplicate_items_count = 0
        for identity, items in identity_map.items():
            if len(items) > 1:
                for item in items:
                    item.is_duplicate = True
                duplicate_items_count += len(items)

        # 4. Refresh view to show updated {is_duplicate} in Key Value Pairs column
        self.model.layoutChanged.emit()
        if is_csv:
            self.csv_preview_model._refresh_data()
        
        if duplicate_items_count > 0:
            self.log_message(f"Duplicate check complete: Found {duplicate_items_count} items sharing {len([k for k,v in identity_map.items() if len(v)>1])} unique identities.", "warning")
        else:
            self.log_message("Duplicate check complete: No duplicates found among candidate items.", "success")

    def perform_version_collision_check(self):
        """Batch check current versions in AYON for tagged and filtered items."""
        project = self.ayon_panel.combo_project.currentText()
        if not project: 
            self.log_message("No project selected for version check.", "warning")
            return
        
        is_csv = self.spreadsheet._is_csv_mode
        
        # 1. Gather candidate items based on criteria
        candidates = []
        for item in self.model.items:
            if not (item.is_tagged and item.ayon_path):
                continue
            
            if not is_csv:
                # Check if fits the right filter panel
                age_min = item.age_minutes
                label = item.label
                matches_search = not self._search_filter_text or self._search_filter_text in label.lower()
                matches_age = not self._age_filter_enabled or (age_min <= self._age_filter_value)
                
                if not (matches_search and matches_age):
                    continue
            
            candidates.append(item)

        self.log_message(f"Version Check: Found {len(candidates)} candidate items.")

        if not candidates:
            self.log_message("No candidate items (tagged, assigned, and filtered) for version collision check.", "warning")
            return
        
        path_map = self.ayon_panel.get_path_to_id_map()
        folder_ids = set()
        items_to_check = []
        
        for item in candidates:
            # ayon_path is /Project/Folder/Task - we need the folder path
            folder_path = "/".join(item.ayon_path.split("/")[:-1])
            f_id = path_map.get(folder_path)
            
            variant = self.model._expand_string(item.variant, item)
            prod_name = self.model._expand_string(self.model.product_name_template, item, use_global_camel=True)
            
            self.log_message(f"Debug Item: {item.filename} | Variant: {variant} | Product: {prod_name}", "info")
            
            if f_id:
                folder_ids.add(f_id)
                items_to_check.append((item, f_id, prod_name))
            else:
                self.log_message(f"Debug: Could not find folder ID for path '{folder_path}' in path_map", "warning")

        if not folder_ids:
            self.log_message(f"Could not resolve any AYON folder IDs. Path map size: {len(path_map)}", "error")
            return
            
        self.log_message(f"Checking AYON versions for {len(candidates)} items across {len(folder_ids)} folders...")
        
        if hasattr(self, "_ver_thread") and self._ver_thread.isRunning():
            try:
                self._ver_thread.finished.disconnect()
            except Exception:
                pass
            self._ver_thread.terminate()
            if not hasattr(self, "_old_threads"):
                self._old_threads = []
            self._old_threads = [t for t in self._old_threads if t.isRunning()]
            self._old_threads.append(self._ver_thread)

        class VersionThread(QThread):
            finished = Signal(object)
            def __init__(self, ayon, project, f_ids):
                super().__init__()
                self.ayon = ayon
                self.project = project
                self.f_ids = f_ids
            def run(self):
                import time
                start_t = time.perf_counter()
                print(f"[Timer] Starting to pull last versions for {len(self.f_ids)} folder IDs in project '{self.project}' from AYON...")
                versions = self.ayon.get_last_versions(self.project, self.f_ids)
                elapsed = time.perf_counter() - start_t
                print(f"[Timer] Pulling last versions for folder IDs in project '{self.project}' from AYON took {elapsed:.4f} seconds.")
                self.finished.emit(versions)

        self._ver_thread = VersionThread(self.ayon, project, list(folder_ids))
        self._ver_thread.finished.connect(lambda v_map: self._on_versions_fetched(v_map, items_to_check))
        self._ver_thread.start()

    def _on_versions_fetched(self, v_map, items_to_check):
        updated = 0
        collision_mode = self.config.get("version_collision", "fail")
        
        self.log_message(f"Debug: Received {len(v_map)} product versions from AYON.")
        
        for item, f_id, prod_name in items_to_check:
            # Key is f"{f_id}|{prod_name}|{prod_type}"
            key = f"{f_id}|{prod_name}|{item.product_type}"
            last_v = v_map.get(key)
            
            if last_v is not None:
                item.last_ayon_version = last_v
                item.version_collision = (last_v >= item.version)
                
                if collision_mode == "lowest":
                    item.version = last_v + 1
                    item.version_collision = (last_v >= item.version)
                    
                updated += 1
            else:
                # Debug log for missing product
                if len(v_map) > 0:
                    self.log_message(f"Debug: No match for {prod_name} ({item.product_type}) in folder {f_id}", "info")
                item.last_ayon_version = 0 
                item.version_collision = None 
        
        # Refresh Version (7), Last Version (8), and Key Value Pairs (11) columns
        self.model.dataChanged.emit(
            self.model.index(0, 7), 
            self.model.index(len(self.model.items)-1, 11)
        )
        if self.spreadsheet._is_csv_mode:
            self.csv_preview_model._refresh_data()
        self.log_message(f"Version check complete. Updated {updated} items.", "success")

    def log_message(self, message, level="info"):
        """Log a message to both status bar and console."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = f"[{timestamp}] "
        
        color_map = {
            "info": "#aaaaaa",
            "warning": "#ffcc00",
            "error": "#ff4444",
            "success": "#a6e22e"
        }
        color = color_map.get(level, "#aaaaaa")
        
        # Append to console with HTML color
        self.log_console.appendHtml(f'<span style="color: {color};">{prefix}{message}</span>')
        
        # Show in status bar
        self.statusBar().showMessage(message, 5000)
        
        # Auto-scroll console
        self.log_console.verticalScrollBar().setValue(self.log_console.verticalScrollBar().maximum())

    def _toggle_log(self, checked):
        if checked:
            self.log_console.show()
        else:
            self.log_console.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
            
        # Take the first one
        path = urls[0].toLocalFile()
        if os.path.exists(path):
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            # Start scan
            self.top_bar.path_display.setText(path)
            self.start_scan(path)
            event.acceptProposedAction()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'help_overlay'):
            self.help_overlay.setGeometry(self.rect())

    def update_preset_dropdown(self):
        """Populate the TopBar preset combobox with available presets from presets_folder."""
        self.top_bar.combo_preset.blockSignals(True)
        self.top_bar.combo_preset.clear()
        self.top_bar.combo_preset.addItem("(None / Active)")
        
        presets_folder = self.secrets.get("presets_folder")
        if presets_folder and os.path.exists(presets_folder):
            try:
                for filename in os.listdir(presets_folder):
                    if filename.endswith(".json"):
                        preset_name = os.path.splitext(filename)[0]
                        self.top_bar.combo_preset.addItem(preset_name)
            except Exception as e:
                print(f"Error listing presets: {e}")
                
        # Set current preset in combobox if active in config
        active_preset = self.config.get("active_preset", "")
        if active_preset:
            index = self.top_bar.combo_preset.findText(active_preset)
            if index >= 0:
                self.top_bar.combo_preset.setCurrentIndex(index)
        else:
            self.top_bar.combo_preset.setCurrentIndex(0)
            
        self.top_bar.combo_preset.blockSignals(False)

    def _on_preset_changed(self, preset_name):
        # Capture the actual active settings BEFORE loading the preset
        old_detect = self.config.get("detect_sequences", True)
        old_thumb = self.config.get("seq_thumb_frame", "Middle")
        old_regex = self.config.get("version_regex", r"([._]v|v)(\d+)")
        old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)

        if not preset_name or preset_name == "(None / Active)":
            try:
                # Load config.json in app root as the target config
                config_root = {}
                if os.path.exists("config.json"):
                    with open("config.json", "r") as f:
                        config_root = json.load(f)
                
                # Migrate any keys if present
                self._migrate_keys_to_secrets(config_root)
                
                # Retain session-specific/local-only settings
                geom = self.config.get("geometry")
                h_split = self.config.get("h_splitter")
                v_split = self.config.get("v_splitter")
                last_folder = config_root.get("last_source_folder") or self.config.get("last_source_folder")
                recent = self.config.get("recent_folders")
                
                # Apply preset
                self.config = config_root
                self.config["active_preset"] = ""
                
                # Restore retained
                if geom: self.config["geometry"] = geom
                if h_split: self.config["h_splitter"] = h_split
                if v_split: self.config["v_splitter"] = v_split
                if last_folder: self.config["last_source_folder"] = last_folder
                if recent: self.config["recent_folders"] = recent
                
                # Save config
                self.save_config()
                
                # Apply preferences
                self._apply_preferences(self.config, self.secrets, old_detect, old_thumb, old_regex, old_exts, show_message=False)
                
                # Restore GUI state widgets
                self._restore_gui_state()
                
                # Restore folder scan
                if last_folder and os.path.exists(last_folder):
                    self.top_bar.path_display.setText(last_folder)
                    self.start_scan(last_folder)
                
                # Restore AYON selection
                project = self.config.get("ayon_project")
                if project:
                    if self.ayon_panel.combo_project.currentText() != project:
                        self.ayon_panel.combo_project.setCurrentText(project)
                    else:
                        self._restore_ayon_selection()
                
                self.log_message("Successfully reset to default (None / Active) config.", "success")
            except Exception as e:
                self.log_message(f"Error resetting to default config: {e}", "error")
            return
            
        presets_folder = self.secrets.get("presets_folder")
        if not presets_folder:
            return
            
        preset_path = os.path.join(presets_folder, f"{preset_name}.json")
        if os.path.exists(preset_path):
            try:
                with open(preset_path, "r") as f:
                    preset_config = json.load(f)
                
                # Migrate any keys if present
                self._migrate_keys_to_secrets(preset_config)
                    
                # Retain session-specific/local-only settings
                geom = self.config.get("geometry")
                h_split = self.config.get("h_splitter")
                v_split = self.config.get("v_splitter")
                last_folder = preset_config.get("last_source_folder") or self.config.get("last_source_folder")
                recent = self.config.get("recent_folders")
                
                # Apply preset
                self.config = preset_config
                self.config["active_preset"] = preset_name
                
                # Restore retained
                if geom: self.config["geometry"] = geom
                if h_split: self.config["h_splitter"] = h_split
                if v_split: self.config["v_splitter"] = v_split
                if last_folder: self.config["last_source_folder"] = last_folder
                if recent: self.config["recent_folders"] = recent
                
                # Save it so config.json and user-centric json are actually the preset json!
                self.save_config()
                
                # Re-apply config and trigger proper refreshes/rescans
                self._apply_preferences(self.config, self.secrets, old_detect, old_thumb, old_regex, old_exts, show_message=False, save=False)
                
                # Restore GUI state widgets
                self._restore_gui_state()
                
                # Restore folder scan
                if last_folder and os.path.exists(last_folder):
                    self.top_bar.path_display.setText(last_folder)
                    self.start_scan(last_folder)
                
                # Restore AYON selection
                project = self.config.get("ayon_project")
                if project:
                    if self.ayon_panel.combo_project.currentText() != project:
                        self.ayon_panel.combo_project.setCurrentText(project)
                    else:
                        self._restore_ayon_selection()
                
                self.log_message(f"Successfully loaded preset '{preset_name}'.", "success")
            except Exception as e:
                self.log_message(f"Error loading preset '{preset_name}': {e}", "error")

    def save_preset_as(self):
        presets_folder = self.secrets.get("presets_folder")
        if not presets_folder:
            QMessageBox.warning(self, "Save Preset", "Presets Folder is not configured in Preferences -> General Tab.")
            return
            
        name, ok = QInputDialog.getText(self, "Save Preset As", "Enter preset name:")
        if not ok or not name.strip():
            return
            
        preset_name = name.strip()
        # Sanitize preset name to be safe for filenames
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', preset_name)
        if not safe_name:
            QMessageBox.warning(self, "Save Preset", "Invalid preset name.")
            return
            
        preset_path = os.path.join(presets_folder, f"{safe_name}.json")
        if os.path.exists(preset_path):
            reply = QMessageBox.question(self, "Save Preset", f"Preset '{safe_name}' already exists. Overwrite?", 
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
                
        try:
            os.makedirs(presets_folder, exist_ok=True)
            
            # Keep identical structure to config.json
            clean_config = self.config.copy()
            
            shifted_keys = [
                "presets_folder",
                "ayon_server_url",
                "traypublisher_path",
                "ffmpeg_path",
                "ffprobe_path",
                "oiiotool_path",
                "vfxtranscode",
                "ocio_config",
                "ayon_api_key",
                "ingest_log_folder",
                "per_project_logging"
            ]
            for key in shifted_keys:
                if key in clean_config:
                    del clean_config[key]
                    
            if "thumbnails_per_row" in clean_config:
                del clean_config["thumbnails_per_row"]
                
            # Filter out local-only parameters from the saved preset template so they don't lock
            local_keys = ["geometry", "h_splitter", "v_splitter", "recent_folders"]
            for key in local_keys:
                if key in clean_config:
                    del clean_config[key]
            
            with open(preset_path, "w") as f:
                json.dump(clean_config, f, indent=4)
                
            # Make the newly saved preset the active one
            self.config["active_preset"] = safe_name
            self.save_config()
            self.update_preset_dropdown()
            
            self.log_message(f"Successfully saved preset '{safe_name}' to {preset_path}.", "success")
            QMessageBox.information(self, "Save Preset", f"Preset '{safe_name}' successfully saved and set as active.")
        except Exception as e:
            QMessageBox.critical(self, "Save Preset Error", f"Error saving preset: {e}")


class AyonFolderThumbnailThread(QThread):
    download_finished = Signal(str, bytes)  # (folder_id, image_bytes)

    def __init__(self, ayon, project, folder_id):
        super().__init__()
        self.ayon = ayon
        self.project = project
        self.folder_id = folder_id

    def run(self):
        try:
            import ayon_api
            thumb = ayon_api.get_folder_thumbnail(self.project, self.folder_id)
            if thumb and thumb.is_valid and thumb.content:
                self.download_finished.emit(self.folder_id, thumb.content)
            else:
                self.download_finished.emit(self.folder_id, b"")
        except Exception as e:
            print(f"Error fetching thumbnail for folder {self.folder_id}: {e}")
            self.download_finished.emit(self.folder_id, b"")


class AyonThumbnailDownloadThread(QThread):
    finished = Signal()
    log = Signal(str)
    state_changed = Signal(str, str)  # (thumb_id, state)

    def __init__(self, project_name, tasks_info, cache_dir):
        super().__init__()
        self.project_name = project_name
        self.tasks_info = tasks_info
        self.cache_dir = cache_dir

    def run(self):
        import os
        import ayon_api
        from PySide6.QtGui import QImage
        os.makedirs(self.cache_dir, exist_ok=True)

        download_count = 0
        skip_count = 0
        for info in self.tasks_info:
            thumb_id = info["thumbnailId"]
            target_path = os.path.join(self.cache_dir, f"{thumb_id}.jpg")
            if os.path.exists(target_path):
                skip_count += 1
                self.state_changed.emit(thumb_id, "cached")
                continue

            try:
                thumbnail = ayon_api.get_thumbnail_by_id(self.project_name, thumb_id)
                if thumbnail and thumbnail.content:
                    image = QImage()
                    if image.loadFromData(thumbnail.content):
                        image.save(target_path, "JPG")
                        download_count += 1
                        self.state_changed.emit(thumb_id, "downloaded")
                    else:
                        self.state_changed.emit(thumb_id, "not available")
                else:
                    self.state_changed.emit(thumb_id, "not available")
            except Exception as e:
                self.state_changed.emit(thumb_id, "not available")

        if download_count > 0 or skip_count > 0:
            self.log.emit(f"AYON task thumbnails update finished. Downloaded: {download_count}, Skipped: {skip_count}")
        self.finished.emit()


