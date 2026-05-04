import os
import json
import csv
import tempfile
import subprocess
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, 
                             QPushButton, QMessageBox, QInputDialog, QApplication,
                             QDialog, QLineEdit, QLabel, QHBoxLayout, QPlainTextEdit, QFormLayout)
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel, QItemSelection, QThread, Signal, QRect
from PySide6.QtGui import QKeySequence, QCursor, QShortcut, QPainter, QColor

from gui.top_bar import TopBar
from gui.ayon_panel import AyonPanel
from gui.filter_panel import FilterPanel
from gui.thumbnail_area import ThumbnailArea
from gui.spreadsheet_panel import SpreadsheetPanel
from gui.prefs_dialog import PreferencesDialog
from logic.image_model import ImageTableModel
from logic.scanner import ImageScanner
from ayon_client import AyonClient


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

class HelpOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()
        
    def show_help(self):
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
        self.hide_help()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dim background
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())
        
        # Main Box
        box_width = 650
        box_height = 550
        box_rect = QRect((self.width() - box_width) // 2, (self.height() - box_height) // 2, box_width, box_height)
        
        # Background with border
        painter.setBrush(QColor(25, 25, 25, 250))
        painter.setPen(QColor(80, 80, 80))
        painter.drawRoundedRect(box_rect, 4, 4)
        
        # Header
        header_rect = QRect(box_rect.left(), box_rect.top(), box_rect.width(), 60)
        painter.setBrush(QColor(40, 40, 40))
        painter.drawRoundedRect(header_rect, 4, 4)
        
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(25, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, "INGESTDESKTOP KEYBOARD GUIDE")
        
        # Columns
        col1_rect = box_rect.adjusted(30, 80, -box_width//2 - 10, -50)
        col2_rect = box_rect.adjusted(box_width//2 + 10, 80, -30, -50)
        
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
            p.drawText(rect.adjusted(120, y_off, 0, 0), Qt.AlignLeft, desc)
            return y_off + 25

        # Col 1
        y = 0
        painter.setPen(QColor(100, 100, 100))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(col1_rect.adjusted(0, y, 0, 0), Qt.AlignLeft, "GENERAL")
        y += 30
        y = draw_shortcut(painter, col1_rect, "Ctrl + A", "Select All (contextual)", y)
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
        y = 0
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
        
        # Footer
        painter.setPen(QColor(120, 120, 120))
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(box_rect.adjusted(0, 0, -25, -20), Qt.AlignBottom | Qt.AlignRight, "Click anywhere or press ESC to exit")

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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IngestDesktop - AYON Pipeline Tool")
        self.resize(1200, 800)

        # Load Config
        self.config = self.load_config()

        # Logic
        self.model = ImageTableModel()
        
        # Clean credentials
        server_url = self.config.get("ayon_server_url", "").strip()
        api_key = self.config.get("ayon_api_key", "").strip()
        
        self.ayon = AyonClient(server_url, api_key)
        self._is_maximized = False
        self._last_h_state = None
        self._last_v_state = None
        self._selection_lock = False

        # UI Components
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # 1. Top Bar
        self.top_bar = TopBar()
        self.top_bar.setObjectName("TopBar")
        self.top_bar.folder_selected.connect(self.start_scan)
        self.top_bar.project_changed.connect(self._on_project_changed)
        self.top_bar.prefs_requested.connect(self.show_preferences)
        self.top_bar.rescan_requested.connect(self.rescan_current)
        self.top_bar.help_requested.connect(self.show_help)
        self.main_layout.addWidget(self.top_bar, 0)

        # Main Splitter (Left, Center, Right)
        self.h_splitter = QSplitter(Qt.Horizontal)
        
        # 2. Left Panel (AYON)
        self.ayon_panel = AyonPanel()
        self.ayon_panel.task_selected.connect(self._on_ayon_task_selected)
        self.ayon_panel.unassign_requested.connect(self._on_ayon_unassign)
        self.ayon_panel.select_assigned_requested.connect(self._on_ayon_select_assigned)
        self.ayon_panel.clear_all_requested.connect(self._on_ayon_clear_all)
        self.ayon_panel.btn_refresh.clicked.connect(self.refresh_ayon)
        self.h_splitter.addWidget(self.ayon_panel)

        # 3. Center Area (Thumbnails + Spreadsheet)
        self.v_splitter = QSplitter(Qt.Vertical)
        
        self.thumb_area = ThumbnailArea()
        self.thumb_area.setModel(self.model)
        self.thumb_area.tag_toggle_requested.connect(self._on_tag_selection)
        self.thumb_area.label_action_requested.connect(self._on_label_action)
        self.thumb_area.maximize_toggle_requested.connect(lambda: self.toggle_maximize("thumbs"))
        self.v_splitter.addWidget(self.thumb_area)
        
        self.spreadsheet = SpreadsheetPanel()
        self.spreadsheet.set_model(self.model)
        self.spreadsheet.btn_tag_sel.clicked.connect(self._on_tag_selection)
        self.spreadsheet.maximize_toggle_requested.connect(lambda: self.toggle_maximize("spreadsheet"))
        self.spreadsheet.label_action_requested.connect(self._on_label_action)
        self.v_splitter.addWidget(self.spreadsheet)
        
        # Connect selection after model is set
        self.spreadsheet.table.selectionModel().selectionChanged.connect(self._sync_selection_to_thumbs)
        self.thumb_area.scene.selectionChanged.connect(self._sync_selection_to_table)
        
        # Sync visuals
        self.model.dataChanged.connect(lambda: self.filter_panel.refresh_colors())
        self.model.dataChanged.connect(self._update_ayon_visuals)
        
        self.h_splitter.addWidget(self.v_splitter)

        # 4. Right Panel (Filtering)
        self.filter_panel = FilterPanel(self.model)
        self.filter_panel.folder_selected.connect(self._on_filter_folder_selected)
        self.filter_panel.age_changed.connect(self._on_age_filter_changed)
        self.filter_panel.search_changed.connect(self._on_filter_search_changed)
        self.h_splitter.addWidget(self.filter_panel)

        self.main_layout.addWidget(self.h_splitter, 1)

        # 5. Big Ingest Button
        self.btn_ingest_big = QPushButton("Ingest Tagged to AYON")
        self.btn_ingest_big.setObjectName("IngestButton")
        self.btn_ingest_big.setMinimumHeight(50)
        self.btn_ingest_big.clicked.connect(self.perform_ingest)
        self.main_layout.addWidget(self.btn_ingest_big, 0)
        
        # 6. Log Console (expandable)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(100)
        self.log_console.setStyleSheet("background-color: #0c0c0c; color: #cccccc; font-family: Consolas, monospace;")
        self.main_layout.addWidget(self.log_console, 0)
        
        # 7. Help Overlay
        self.help_overlay = HelpOverlay(self)
        
        # Initial config
        self.load_config()

        self.btn_toggle_log = QPushButton("Log History")
        self.btn_toggle_log.setFlat(True)
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setStyleSheet("color: #888888; text-decoration: underline;")
        self.btn_toggle_log.clicked.connect(self._toggle_log)
        self.statusBar().addPermanentWidget(self.btn_toggle_log)

        # 6. Select All Shortcut
        self.shortcut_all = QShortcut(QKeySequence("Ctrl+A"), self)
        self.shortcut_all.activated.connect(self._on_select_all)
        
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

    def load_config(self):
        try:
            with open("config.json", "r") as f:
                return json.load(f)
        except:
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
        self.thumb_area.slider_cols.setValue(self.config.get("default_columns", 12))
        self.thumb_area.slider_cols.valueChanged.connect(self._on_cols_changed)

        # Update model presets mapping
        self._update_model_presets()

        # Async AYON Load
        self.refresh_ayon_async()

        last_folder = self.config.get("last_source_folder")
        if last_folder and not os.path.exists(last_folder):
            last_folder = self.config.get("default_scan_folder")
            
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

    def start_scan(self, directory):
        self.log_message(f"Starting scan of directory: {directory}")
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()

        self.model.clear()
        self.filter_panel.set_root_folder(directory)
        self.top_bar.set_path(directory)
        
        self.scanner = ImageScanner(
            directory, 
            version_regex=self.config.get("version_regex", "_v(\\d+)"),
            thumbnail_size=self.config.get("thumbnail_size", 150),
            age_source=self.config.get("age_source", "Modification Date"),
            detect_sequences=self.config.get("detect_sequences", True),
            seq_thumb_frame=self.config.get("seq_thumb_frame", "Middle"),
            extensions=self.config.get("extensions", {}),
            presets=self.config.get("presets", {})
        )
        self.scanner.finished.connect(lambda items: self.log_message(f"Scan complete. Found {len(items)} items.", "success"))
        self.scanner.finished.connect(self.model.add_items)
        self.scanner.start()
        
        # Update config
        self.config["last_source_folder"] = directory
        self.save_config()

    def rescan_current(self):
        """Scan for new files in the current directory without clearing existing data."""
        directory = self.top_bar.path_display.text()
        if not directory or not os.path.exists(directory):
            self.log_message("No valid directory to rescan.", "warning")
            return
            
        self.log_message(f"Rescanning directory: {directory}")
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.cancel()
            self.scanner.wait()
            
        self.scanner = ImageScanner(
            directory, 
            version_regex=self.config.get("version_regex", "_v(\\d+)"),
            thumbnail_size=self.config.get("thumbnail_size", 150),
            age_source=self.config.get("age_source", "Modification Date"),
            detect_sequences=self.config.get("detect_sequences", True),
            seq_thumb_frame=self.config.get("seq_thumb_frame", "Middle"),
            extensions=self.config.get("extensions", {}),
            presets=self.config.get("presets", {})
        )
        self.scanner.finished.connect(self._on_rescan_finished)
        self.scanner.start()

    def _on_rescan_finished(self, items):
        """Filter for new items and add them to the model."""
        existing_paths = {item.file_path for item in self.model.items}
        new_items = [it for it in items if it.file_path not in existing_paths]
        
        if new_items:
            self.model.add_items(new_items)
            self.log_message(f"Rescan complete. Added {len(new_items)} new items.", "success")
        else:
            self.log_message("Rescan complete. No new items found.")

    def _on_project_changed(self, project_name):
        """Called when user selects a different project in the top bar."""
        if not project_name or not self.ayon.is_connected:
            return
            
        # Save last project to config
        self.config["last_ayon_project"] = project_name
        self.save_config()
        
        self.refresh_hierarchy_async(project_name)

    def _update_model_presets(self):
        """Update the model's category-to-preset-name mapping."""
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

    def refresh_ayon(self):
        self.refresh_ayon_async(reconnect=False)

    def refresh_ayon_async(self, reconnect=False):
        """Asynchronously connect and refresh AYON projects list."""
        if hasattr(self, "_conn_thread") and self._conn_thread.isRunning():
            return
            
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
                if self.do_connect:
                    self.ayon.connect(self.url, self.key)
                projects = self.ayon.get_projects()
                self.finished.emit(self.ayon.is_connected, projects)

        server_url = self.config.get("ayon_server_url", "").strip()
        api_key = self.config.get("ayon_api_key", "").strip()
        
        self._conn_thread = ConnectionThread(self.ayon, server_url, api_key, reconnect)
        self._conn_thread.finished.connect(self._on_ayon_refreshed)
        self._conn_thread.start()

    def _on_ayon_refreshed(self, is_connected, projects):
        """Called when project list refresh is done."""
        self.ayon_panel.set_connection_status(is_connected, self.ayon.server_url)
        
        # Block signals to avoid feedback loop when setting project list
        self.top_bar.combo_project.blockSignals(True)
        current = self.top_bar.combo_project.currentText()
        if not current:
            current = self.config.get("last_ayon_project")
            
        self.top_bar.set_projects(projects)
        if current in projects:
            self.top_bar.combo_project.setCurrentText(current)
        self.top_bar.combo_project.blockSignals(False)
        
        if is_connected:
            project = self.top_bar.combo_project.currentText()
            if project:
                self.refresh_hierarchy_async(project)

    def refresh_hierarchy_async(self, project_name):
        """Asynchronously fetch folder hierarchy for a specific project."""
        if hasattr(self, "_hier_thread") and self._hier_thread.isRunning():
            self._hier_thread.terminate() # Kill old fetch if switching fast
            
        class HierarchyThread(QThread):
            finished = Signal(list)
            def __init__(self, ayon, project):
                super().__init__()
                self.ayon = ayon
                self.project = project
            def run(self):
                hierarchy = self.ayon.get_project_hierarchy(self.project)
                self.finished.emit(hierarchy)

        self._hier_thread = HierarchyThread(self.ayon, project_name)
        self._hier_thread.finished.connect(self.ayon_panel.set_hierarchy)
        self._hier_thread.finished.connect(self._update_ayon_visuals)
        self._hier_thread.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'help_overlay'):
            self.help_overlay.setGeometry(self.rect())

    def show_help(self):
        self.help_overlay.show_help()

    def show_preferences(self):
        # Store old values to check if re-scan is needed
        old_detect = self.config.get("detect_sequences", True)
        old_thumb = self.config.get("seq_thumb_frame", "Middle")
        old_regex = self.config.get("version_regex", "_v(\\d+)")
        old_exts = json.dumps(self.config.get("extensions", {}), sort_keys=True)

        dialog = PreferencesDialog(self.config, self)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.config.update(new_settings)
            self.thumb_area.slider_cols.setValue(self.config.get("default_columns", 12))
            
            # Apply label regex update
            label_regex = self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$")
            self.model.label_allowed_regex = label_regex
            self.thumb_area.update_label_validator(label_regex)
            
            self.save_config()
            self._update_model_presets()
            
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
            
            QMessageBox.information(self, "Preferences", "Settings saved. View has been refreshed to reflect scanner changes.")

    def _on_cols_changed(self, value):
        self.config["default_columns"] = value
        self.save_config()

    def _on_age_filter_changed(self, value, units):
        self.model.set_age_unit(units)

    def _update_ages(self):
        import time
        current_time = time.time()
        source = self.config.get("age_source", "Modification Date")
        
        for item in self.model.items:
            source_time = item.modification_time if source == "Modification Date" else item.creation_time
            item.age_minutes = int((current_time - source_time) / 60)
        
        # Notify the model that the age column (index 5) has changed
        if self.model.items:
            self.model.dataChanged.emit(
                self.model.index(0, 5), 
                self.model.index(len(self.model.items)-1, 5)
            )

    def save_config(self):
        with open("config.json", "w") as f:
            json.dump(self.config, f, indent=4)

    def perform_ingest(self):
        tagged_items = [item for item in self.model.items if item.is_tagged]
        if not tagged_items:
            QMessageBox.warning(self, "Ingest", "No images tagged for ingest.")
            return

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
            return

        # 2. Check versions (AYON API check)
        project = self.top_bar.combo_project.currentText()
        for item in tagged_items:
            if not item.ayon_path: continue
            
            # expected path: folder/task
            parts = item.ayon_path.split("/")
            if len(parts) >= 1:
                folder_path = parts[0]
                # Assuming product name is same as label for now, or derived from it
                # In a real tool this would be more complex
                last_v = self.ayon.get_last_version(project, folder_path, item.label)
                if last_v is not None:
                    item.last_ayon_version = last_v
        
        self.model.dataChanged.emit(self.model.index(0, 4), self.model.index(len(self.model.items)-1, 4))

        # 3. Create CSV
        csv_path = os.path.join(tempfile.gettempdir(), "ayon_ingest.csv")
        try:
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                # Header
                writer.writerow(["File Path", "Folder Path", "Task Name", "Variant", "Version"])
                for item in tagged_items:
                    # Parse ayon_path (expected: /project/folder/task)
                    # Simplified for now
                    writer.writerow([
                        item.file_path, 
                        item.ayon_path, 
                        "GenericTask", # Placeholder
                        item.label, 
                        item.version
                    ])
        except Exception as e:
            QMessageBox.critical(self, "Ingest", f"Failed to create CSV: {e}")
            return

        # 4. Call external process
        tray_path = self.config.get("traypublisher_path", "ayon_console.exe")
        project = self.top_bar.combo_project.currentText()
        
        cmd = [
            tray_path, "addon", "traypublisher", "ingestcsv",
            "--filepath", csv_path,
            "--project", project
        ]

        try:
            subprocess.Popen(cmd)
            self.log_message(f"Ingest CSV created and TrayPublisher started.", "success")
            self.log_message(f"CSV Path: {csv_path}")
        except Exception as e:
            self.log_message(f"Failed to start TrayPublisher: {e}", "error")
            QMessageBox.critical(self, "Ingest", f"Failed to start TrayPublisher: {e}")

    def _on_selection_changed(self, selected, deselected):
        pass # Handle via sync methods now

    def _sync_selection_to_thumbs(self):
        if self._selection_lock: return
        if not hasattr(self, 'thumb_area') or not self.thumb_area.scene: return
        
        self._selection_lock = True
        try:
            self.thumb_area.scene.clearSelection()
            selected_rows = [idx.row() for idx in self.spreadsheet.table.selectionModel().selectedRows()]
            selected_paths = []
            for row in selected_rows:
                if row < len(self.model.items):
                    item_data = self.model.items[row]
                    if item_data in self.thumb_area.item_to_thumb:
                        self.thumb_area.item_to_thumb[item_data].setSelected(True)
                        selected_paths.append(item_data.file_path)
            
            # Sync to FilterPanel
            self.filter_panel.select_paths(selected_paths)
        finally:
            self._selection_lock = False

    def _sync_selection_to_table(self):
        if self._selection_lock: return
        if not hasattr(self, 'spreadsheet') or not self.spreadsheet.table.selectionModel(): return
        
        self._selection_lock = True
        try:
            self.spreadsheet.table.selectionModel().clearSelection()
            
            selection = QItemSelection()
            selected_paths = []
            for item in self.thumb_area.scene.selectedItems():
                # Find the current row for this data object
                try:
                    row = self.model.items.index(item.data)
                    # Select the full row for robust F2 operation
                    tl = self.model.index(row, 0)
                    br = self.model.index(row, self.model.columnCount() - 1)
                    selection.select(tl, br)
                    selected_paths.append(item.data.file_path)
                except (ValueError, AttributeError):
                    continue
            
            if not selection.isEmpty():
                self.spreadsheet.table.selectionModel().select(selection, QItemSelectionModel.Select)
            
            # Sync to FilterPanel
            self.filter_panel.select_paths(selected_paths)
        finally:
            self._selection_lock = False

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
        """F2 Rename for the currently selected item."""
        # Get selected items
        selection_model = self.spreadsheet.table.selectionModel()
        selected_indexes = selection_model.selectedIndexes()
        
        # Get unique rows
        unique_rows = sorted(list(set(idx.row() for idx in selected_indexes)))
        
        if len(unique_rows) != 1:
            # Fallback: check thumbnail area directly in case of sync lag
            selected_thumbs = self.thumb_area.scene.selectedItems()
            if len(selected_thumbs) == 1:
                item_data = selected_thumbs[0].data
                try:
                    row = self.model.items.index(item_data)
                    unique_rows = [row]
                except ValueError:
                    pass
                    
        if len(unique_rows) != 1:
            return
            
        row = unique_rows[0]
        item_data = self.model.items[row]
        
        # Trigger the rename action with the specific row index
        self._on_label_action("rename", (row, item_data))

    def _on_filter_search_changed(self, text):
        if self._selection_lock: return
        self._selection_lock = True
        
        selection_model = self.spreadsheet.table.selectionModel()
        selection_model.clearSelection()
        
        if not text:
            self._selection_lock = False
            return

        # Select items that contain the search text (case-insensitive)
        selection = QItemSelection()
        first_idx = None
        
        search_term = text.lower()
        for i, item in enumerate(self.model.items):
            if search_term in item.label.lower():
                idx = self.model.index(i, 0)
                selection.select(idx, idx)
                if first_idx is None: first_idx = idx
        
        selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self._selection_lock = False
        
        if first_idx:
            self.spreadsheet.table.scrollTo(first_idx)

    def _on_filter_folder_selected(self, path):
        # Determine mode from filter panel
        is_select_mode = self.filter_panel.btn_select.isChecked()
        
        if is_select_mode:
            # Select items that are in this folder
            selection_model = self.spreadsheet.table.selectionModel()
            selection_model.clearSelection()
            
            selection = QItemSelection()
            first_idx = None
            
            for i, item in enumerate(self.model.items):
                # Check if item file path starts with filter path
                # Use normpath for reliable comparison
                item_abs = os.path.normpath(os.path.abspath(item.file_path))
                filter_abs = os.path.normpath(os.path.abspath(path))
                
                if item_abs == filter_abs or item_abs.startswith(filter_abs + os.sep):
                    idx = self.model.index(i, 0)
                    selection.select(idx, idx)
                    if first_idx is None: first_idx = idx
            
            selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            if first_idx:
                self.spreadsheet.table.scrollTo(first_idx)
        else:
            # 'Show' mode - Filter the thumbnails
            self.thumb_area.set_path_filter(path)

    def _on_label_action(self, action, data):
        if action == "tag":
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
        action_str = "Tagged (Selected for ingest)" if sample_item.is_tagged else "Untagged (Excluded from ingest)"
        level = "success" if sample_item.is_tagged else "info"
        self.log_message(f"{action_str}: {count} items.", level)

    def closeEvent(self, event):
        """Save state before closing."""
        self.config["geometry"] = self.saveGeometry().toHex().data().decode()
        self.config["h_splitter"] = self.h_splitter.saveState().toHex().data().decode()
        self.config["v_splitter"] = self.v_splitter.saveState().toHex().data().decode()
        
        with open("config.json", "w") as f:
            json.dump(self.config, f, indent=4)
        super().closeEvent(event)

    def toggle_maximize(self, source="thumbs"):
        """Toggle maximize state of the middle panel or spreadsheet."""
        if not self._is_maximized:
            # Maximize
            self._last_h_state = self.h_splitter.saveState()
            self._last_v_state = self.v_splitter.saveState()
            
            self.ayon_panel.hide()
            self.filter_panel.hide()
            self.top_bar.hide()
            self.btn_ingest_big.hide()
            
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
            self.btn_ingest_big.show()
            
            self.thumb_area.btn_maximize.setText("Maximize")
            self.thumb_area.btn_maximize.setChecked(False)
            
            if self._last_h_state:
                self.h_splitter.restoreState(self._last_h_state)
            if self._last_v_state:
                self.v_splitter.restoreState(self._last_v_state)
            
            self._is_maximized = False
        
        # Reframe thumbnails after layout change
        if self.thumb_area.isVisible():
            self.thumb_area.frame_all()

    def _on_ayon_task_selected(self, folder_path, task_name, task_type):
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
            
        # Notify the model that the AYON Path column (7) has changed for these rows
        start_idx = self.model.index(min(selected_rows), 7)
        end_idx = self.model.index(max(selected_rows), 7)
        self.model.dataChanged.emit(start_idx, end_idx)
        
        # Feedback
        self.log_message(f"Assigned '{ayon_path}' to {len(selected_rows)} items.")

    def _update_ayon_visuals(self):
        """Highlight assigned tasks in the AYON panel."""
        assigned_paths = set(item.ayon_path for item in self.model.items if item.ayon_path)
        self.ayon_panel.update_assigned_status(assigned_paths)

    def _on_ayon_unassign(self, ayon_path):
        """Clear AYON path for all items assigned to this path."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path == ayon_path:
                item.ayon_path = ""
                affected += 1
        
        if affected:
            self.model.dataChanged.emit(self.model.index(0, 7), self.model.index(len(self.model.items)-1, 7))
            self.log_message(f"Unassigned '{ayon_path}' from {affected} items.")
            # Bold status will update via dataChanged signal -> _update_ayon_visuals

    def _on_ayon_select_assigned(self, ayon_path):
        """Select all items that have this AYON path."""
        selection_model = self.spreadsheet.table.selectionModel()
        selection_model.clearSelection()
        
        selection = QItemSelection()
        first_idx = None
        count = 0
        
        for i, item in enumerate(self.model.items):
            if item.ayon_path == ayon_path:
                idx = self.model.index(i, 0)
                # Select the full row
                tl = self.model.index(i, 0)
                br = self.model.index(i, self.model.columnCount() - 1)
                selection.select(tl, br)
                if first_idx is None: first_idx = idx
                count += 1
        
        if not selection.isEmpty():
            selection_model.select(selection, QItemSelectionModel.Select)
            if first_idx:
                self.spreadsheet.table.scrollTo(first_idx)
            self.log_message(f"Selected {count} items assigned to '{ayon_path}'.")
        else:
            self.log_message(f"No items assigned to '{ayon_path}' found.", "warning")

    def _on_ayon_clear_all(self):
        """Reset all AYON path assignments."""
        affected = 0
        for item in self.model.items:
            if item.ayon_path:
                item.ayon_path = ""
                affected += 1
        
        if affected:
            self.model.dataChanged.emit(self.model.index(0, 7), self.model.index(len(self.model.items)-1, 7))
            self.log_message(f"Cleared all AYON assignments from {affected} items.", "warning")

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
            self.btn_toggle_log.setText("Hide Log")
        else:
            self.log_console.hide()
            self.btn_toggle_log.setText("Log History")
