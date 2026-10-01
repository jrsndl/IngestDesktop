"""Thumbnail / review conversions, the conversion queue and Deadline submission.

Mixin of MainWindow (gui/main_window.py): methods use the window's
attributes (self.model, self.config, self.thumb_area, ...).
"""
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
from gui.window.dialogs import RenameDialog, HelpContentWidget, HelpOverlay, SearchReplaceDialog
from gui.window.ayon_threads import AyonFolderThumbnailThread, AyonThumbnailDownloadThread, AyonGetRepreThread


class ConversionMixin:
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
            
        selected_items = self.get_selected_items()
        self._queue_dialog.set_selected_items(selected_items)
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
        if getattr(item, "thumbnail_image", None) is not None:
            pass  # model.update_item() below turns the worker's QImage into the pixmap
        elif hasattr(item, "temp_qimage") and item.temp_qimage:
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
            selected_items = self._items_for_table_rows(selection_model.selectedRows())

        def requires_review(item):
            p_data = item.preset_data or {}
            return item.review_status == "waiting" or p_data.get("Convert Review", True)

        # 3. Filter review items based on selection
        if selected_items:
            review_items = [item for item in selected_items if requires_review(item)]
            if not review_items:
                show_info(self, "Deadline", "None of the selected items require review conversion.", self.config)
                return
        else:
            review_items = [item for item in self.model.items if requires_review(item)]
            if not review_items:
                show_info(self, "Deadline", "No items in the project require review conversion.", self.config)
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
        show_info(self, "Deadline Submission Summary", summary_msg, self.config)
