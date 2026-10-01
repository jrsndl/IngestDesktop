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
from gui.window.dialogs import RenameDialog, HelpContentWidget, HelpOverlay, SearchReplaceDialog  # noqa: F401 (re-exported)
from gui.window.ayon_threads import AyonFolderThumbnailThread, AyonThumbnailDownloadThread, AyonGetRepreThread  # noqa: F401 (re-exported)
from gui.window.project import ProjectMixin
from gui.window.settings import SettingsMixin
from gui.window.scan import ScanMixin
from gui.window.conversions import ConversionMixin
from gui.window.publish import PublishMixin
from gui.window.selection import SelectionMixin
from gui.window.ayon import AyonMixin


class MainWindow(ProjectMixin, SettingsMixin, ScanMixin, ConversionMixin, PublishMixin,
                 SelectionMixin, AyonMixin, QMainWindow):
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
        self.show_reviews = True  # "Show Reviews" (spreadsheet controls) starts on
        
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
        self.top_bar.reveal_requested.connect(self.reveal_source_folder)
        self.top_bar.load_preset_requested.connect(self._on_preset_changed)
        self.top_bar.save_preset_requested.connect(self.perform_save_preset)
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
        self.ayon_panel.task_status_change_requested.connect(self._on_ayon_task_status_change)
        self.ayon_panel.version_status_change_requested.connect(self._on_ayon_version_status_change)
        self.ayon_panel.get_folder_repres_requested.connect(self._on_get_folder_repres)
        self.ayon_panel.get_task_repre_requested.connect(self._on_get_task_repre)
        self.ayon_panel.get_product_repre_requested.connect(self._on_get_product_repre)
        self.ayon_panel.get_repre_repre_requested.connect(self._on_get_repre_repre)
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
        self.spreadsheet.version_check_clicked.connect(lambda: self.perform_version_collision_check(fix=False))
        self.spreadsheet.version_collision_check_clicked.connect(lambda: self.perform_version_collision_check(fix=True))
        self.spreadsheet.label_action_requested.connect(self._on_label_action)
        self.spreadsheet.add_comment_requested.connect(self._on_add_comment)
        self.spreadsheet.replace_value_requested.connect(self._on_replace_value)
        self.spreadsheet.check_duplicates_clicked.connect(self.perform_duplicate_check)
        self.spreadsheet.show_grouped_toggled.connect(self._on_show_grouped_toggled)
        self.spreadsheet.show_reviews_toggled.connect(self._on_show_reviews_toggled)
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
        self.filter_panel.ignore_changed.connect(self._on_filter_ignore_changed)
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
        export_checks_layout = QHBoxLayout()
        export_checks_layout.setContentsMargins(2, 0, 2, 2)
        
        self.chk_check_versions = QCheckBox("Check Versions")
        self.chk_check_versions.setChecked(True)
        self.chk_check_versions.setToolTip("When checked, prevents exporting or publishing items with version numbers <= existing AYON versions.")
        self.chk_check_versions.toggled.connect(self.save_config)
        
        self.chk_check_duplicates = QCheckBox("Check Duplicates")
        self.chk_check_duplicates.setChecked(True)
        self.chk_check_duplicates.setToolTip("When checked, prevents exporting or publishing duplicate item identities.")
        self.chk_check_duplicates.toggled.connect(self.save_config)
        
        export_checks_layout.addWidget(self.chk_check_versions)
        export_checks_layout.addSpacing(15)
        export_checks_layout.addWidget(self.chk_check_duplicates)
        export_checks_layout.addStretch()
        
        self.main_layout.addLayout(export_checks_layout)

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
        act_load_preset.triggered.connect(self.perform_load_preset)
        file_menu.addAction(act_load_preset)
        
        act_save_preset_direct = QAction("Save Preset", self)
        act_save_preset_direct.triggered.connect(self.perform_save_preset)
        file_menu.addAction(act_save_preset_direct)

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

    def closeEvent(self, event):
        """Save state before closing."""
        self.config["geometry"] = self.saveGeometry().toHex().data().decode()
        self.config["h_splitter"] = self.h_splitter.saveState().toHex().data().decode()
        self.config["v_splitter"] = self.v_splitter.saveState().toHex().data().decode()
        if hasattr(self, 'center_top_splitter'):
            self.config["center_top_splitter"] = self.center_top_splitter.saveState().toHex().data().decode()
        
        self.save_config_now()

        # Stop background work so no scan or ffmpeg/oiiotool process outlives the app
        for attr in ("scanner", "_conv_worker", "_review_worker"):
            worker = getattr(self, attr, None)
            try:
                if worker is not None and worker.isRunning():
                    worker.cancel()
                    worker.wait(3000)
            except Exception as e:
                print(f"Error stopping {attr}: {e}")
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
