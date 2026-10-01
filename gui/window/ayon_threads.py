"""Background threads for AYON thumbnails and representations."""
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


class AyonGetRepreThread(QThread):
    finished_items = Signal(list)

    def __init__(self, ayon_client, project_name, mode, target_data, config, secrets=None):
        super().__init__()
        self.ayon_client = ayon_client
        self.project_name = project_name
        self.mode = mode
        self.target_data = target_data
        self.config = config
        self.secrets = secrets or {}

    def run(self):
        from logic.ayon_autopick import (
            autopick_task, autopick_product, autopick_version, autopick_representation
        )
        from logic.image_model import ImageItem

        task_type_prio = self.config.get("ayon_item_task_type_priority", "Compositing Editing")
        task_name_prio = self.config.get("ayon_item_task_name_priority", "comp")
        prod_type_prio = self.config.get("ayon_item_product_type_priority", "review render plate")
        prod_name_prio = self.config.get("ayon_item_product_name_priority", "main")
        ver_mode = self.config.get("ayon_item_product_version", "Max Version")
        ver_status = self.config.get("ayon_item_product_version_status", "")
        repre_prio = self.config.get("ayon_item_repre_priority_extension", "mp4 mov png")
        label_template = self.config.get("ayon_item_label", "{folder_name}/{task_name}/{product_name} v{version}")

        items = []

        from logic.image_model import ImageTableModel
        model_expander = ImageTableModel()

        def make_ayon_item(f_path, f_name, f_desc, f_stat, t_name, t_type, t_desc, t_stat, p_name, p_type, v_num, v_stat, p_src, r_name, path, rep_id=None, thumb_id=None):
            ver_str = f"v{v_num:03d}" if isinstance(v_num, int) else str(v_num)
            item = ImageItem(
                file_path=path or f"ayon://{self.project_name}/{f_path}/{p_name}.{r_name}",
                label="",
                version=v_num,
                category="AYON",
                product_type=p_type,
                representation=r_name,
                is_ayon_item=True
            )
            item.ayon_path = f"{f_path}/{t_name}" if t_name else f_path
            item.ayon_task_name = t_name
            item.ayon_task_type = t_type
            item.metadata.update({
                "folder_path": f_path,
                "folder_name": f_name,
                "folder_description": f_desc,
                "folder_status": f_stat,
                "task_name": t_name,
                "task_type": t_type,
                "task_description": t_desc,
                "task_status": t_stat,
                "product_name": p_name,
                "product_type": p_type,
                "product_version": ver_str,
                "product_status": v_stat,
                "product_source": p_src,
                "version": v_num,
                "representation": r_name,
            })
            item.label = model_expander._expand_string(label_template, item) or f"{f_name}/{t_name}/{p_name} v{v_num}"
            if rep_id:
                setattr(item, "repre_id", rep_id)
            if thumb_id:
                setattr(item, "thumbnail_id", thumb_id)
            return item

        if self.mode == "product":
            p = self.target_data
            prod_id = p.get("id")
            prod_name = p.get("name", "")
            prod_type = p.get("type") or p.get("productType", "")
            folder_id = p.get("folder_id") or p.get("folderId")
            folder_path = p.get("folder_path") or p.get("path") or ""
            folder_name = p.get("folder_name") or (os.path.basename(folder_path) if folder_path else "")
            folder_desc = p.get("folder_description") or p.get("description", "")
            folder_stat = p.get("folder_status") or p.get("status", "")
            task_name = p.get("task_name") or ""
            task_type = p.get("task_type") or ""
            task_desc = p.get("task_description") or ""
            task_stat = p.get("task_status") or ""
            ver_id = p.get("version_id")
            ver_num = p.get("version", 1)
            ver_stat = p.get("version_status", "")
            ver_src = p.get("product_source", "")

            if not ver_id and prod_id:
                versions = self.ayon_client.get_versions_for_product(self.project_name, prod_id)
                v_obj = autopick_version(versions, ver_mode, ver_status)
                if v_obj:
                    ver_id = v_obj.get("id")
                    ver_num = v_obj.get("version", ver_num)
                    ver_stat = v_obj.get("status", ver_stat)
                    ver_src = v_obj.get("attrib", {}).get("source") or v_obj.get("data", {}).get("source", ver_src)

            if ver_id:
                repres = self.ayon_client.get_representations_for_version(self.project_name, ver_id)
                rep = autopick_representation(repres, repre_prio)
                if rep:
                    path = rep.get("attrib", {}).get("path") or ""
                    rep_name = rep.get("name", "")
                    rep_id = rep.get("id", "")
                    thumb_id = rep.get("thumbnail_id") or rep.get("thumbnailId") or rep.get("thumbnail")
                    item = make_ayon_item(
                        folder_path, folder_name, folder_desc, folder_stat,
                        task_name, task_type, task_desc, task_stat,
                        prod_name, prod_type, ver_num, ver_stat, ver_src, rep_name,
                        path, rep_id, thumb_id
                    )
                    items.append(item)

        elif self.mode == "task":
            t = self.target_data
            task_id = str(t.get("id"))
            task_name = t.get("name", "")
            task_type = t.get("type", "")
            task_desc = t.get("description") or t.get("attrib", {}).get("description", "")
            task_stat = t.get("status", "")
            folder_id = t.get("folderId") or t.get("folder_id")
            folder_path = t.get("folder_path") or t.get("path") or ""
            folder_name = t.get("folder_name") or (os.path.basename(folder_path) if folder_path else "")
            folder_desc = t.get("folder_description", "")
            folder_stat = t.get("folder_status", "")

            if folder_id:
                products = self.ayon_client.get_products_for_folder(self.project_name, folder_id)
                task_prods = [p for p in products if p.get("task_id") == task_id or p.get("task_name") == task_name]
                candidates = task_prods if task_prods else products
                p_obj = autopick_product(candidates, prod_type_prio, prod_name_prio)
                if p_obj:
                    prod_id = p_obj.get("id")
                    prod_name = p_obj.get("name", "")
                    prod_type = p_obj.get("type") or p_obj.get("productType", "")
                    versions = self.ayon_client.get_versions_for_product(self.project_name, prod_id)
                    v_obj = autopick_version(versions, ver_mode, ver_status)
                    if v_obj:
                        ver_id = v_obj.get("id")
                        ver_num = v_obj.get("version", 1)
                        ver_stat = v_obj.get("status", "")
                        ver_src = v_obj.get("attrib", {}).get("source") or v_obj.get("data", {}).get("source", "")
                        repres = self.ayon_client.get_representations_for_version(self.project_name, ver_id)
                        rep = autopick_representation(repres, repre_prio)
                        if rep:
                            path = rep.get("attrib", {}).get("path") or ""
                            rep_name = rep.get("name", "")
                            rep_id = rep.get("id", "")
                            thumb_id = rep.get("thumbnail_id") or rep.get("thumbnailId") or rep.get("thumbnail")
                            item = make_ayon_item(
                                folder_path, folder_name, folder_desc, folder_stat,
                                task_name, task_type, task_desc, task_stat,
                                prod_name, prod_type, ver_num, ver_stat, ver_src, rep_name,
                                path, rep_id, thumb_id
                            )
                            items.append(item)

        elif self.mode == "folder":
            folders = self.target_data if isinstance(self.target_data, list) else [self.target_data]
            for f in folders:
                folder_id = str(f.get("id"))
                folder_path = f.get("path") or f.get("folder_path") or f.get("name") or ""
                folder_name = f.get("label") or f.get("name") or os.path.basename(folder_path)
                folder_desc = f.get("description") or f.get("attrib", {}).get("description", "")
                folder_stat = f.get("status", "")
                tasks = f.get("tasks", [])
                picked_t = autopick_task(tasks, task_type_prio, task_name_prio)
                task_id = str(picked_t.get("id")) if picked_t else None
                task_name = picked_t.get("name", "") if picked_t else ""
                task_type = picked_t.get("type", "") if picked_t else ""
                task_desc = (picked_t.get("description") or picked_t.get("attrib", {}).get("description", "")) if picked_t else ""
                task_stat = picked_t.get("status", "") if picked_t else ""

                products = self.ayon_client.get_products_for_folder(self.project_name, folder_id)
                task_prods = [p for p in products if p.get("task_id") == task_id or p.get("task_name") == task_name] if task_id else []
                candidates = task_prods if task_prods else products
                p_obj = autopick_product(candidates, prod_type_prio, prod_name_prio)
                if p_obj:
                    prod_id = p_obj.get("id")
                    prod_name = p_obj.get("name", "")
                    prod_type = p_obj.get("type") or p_obj.get("productType", "")
                    versions = self.ayon_client.get_versions_for_product(self.project_name, prod_id)
                    v_obj = autopick_version(versions, ver_mode, ver_status)
                    if v_obj:
                        ver_id = v_obj.get("id")
                        ver_num = v_obj.get("version", 1)
                        ver_stat = v_obj.get("status", "")
                        ver_src = v_obj.get("attrib", {}).get("source") or v_obj.get("data", {}).get("source", "")
                        repres = self.ayon_client.get_representations_for_version(self.project_name, ver_id)
                        rep = autopick_representation(repres, repre_prio)
                        if rep:
                            path = rep.get("attrib", {}).get("path") or ""
                            rep_name = rep.get("name", "")
                            rep_id = rep.get("id", "")
                            thumb_id = rep.get("thumbnail_id") or rep.get("thumbnailId") or rep.get("thumbnail")
                            item = make_ayon_item(
                                folder_path, folder_name, folder_desc, folder_stat,
                                task_name, task_type, task_desc, task_stat,
                                prod_name, prod_type, ver_num, ver_stat, ver_src, rep_name,
                                path, rep_id, thumb_id
                            )
                            items.append(item)

        elif self.mode == "repre":
            rep = self.target_data
            rep_id = rep.get("id", "")
            path = rep.get("attrib", {}).get("path") or ""
            rep_name = rep.get("name", "")
            thumb_id = rep.get("thumbnail_id") or rep.get("thumbnailId") or rep.get("thumbnail")
            ctx = rep.get("context") or {}
            folder_name = ctx.get("folder", {}).get("name") if isinstance(ctx.get("folder"), dict) else (ctx.get("folder_name") or ctx.get("folder") or "")
            folder_path = ctx.get("folder", {}).get("path") if isinstance(ctx.get("folder"), dict) else (ctx.get("folder_path") or folder_name)
            folder_desc = rep.get("folder_description", "")
            folder_stat = rep.get("folder_status", "")
            task_name = ctx.get("task", {}).get("name") if isinstance(ctx.get("task"), dict) else (ctx.get("task_name") or ctx.get("task") or "")
            task_type = ctx.get("task", {}).get("type") if isinstance(ctx.get("task"), dict) else (ctx.get("task_type") or ctx.get("task_type") or "")
            task_desc = rep.get("task_description", "")
            task_stat = rep.get("task_status", "")
            prod_name = ctx.get("product", {}).get("name") if isinstance(ctx.get("product"), dict) else (ctx.get("product_name") or ctx.get("product") or "")
            prod_type = ctx.get("product", {}).get("type") if isinstance(ctx.get("product"), dict) else (ctx.get("product_type") or "")
            ver_num = ctx.get("version") or rep.get("version", 1)
            ver_stat = rep.get("version_status", "")
            ver_src = rep.get("attrib", {}).get("source") or rep.get("data", {}).get("source", "")

            item = make_ayon_item(
                folder_path, folder_name, folder_desc, folder_stat,
                task_name, task_type, task_desc, task_stat,
                prod_name, prod_type, ver_num, ver_stat, ver_src, rep_name,
                path, rep_id, thumb_id
            )
            items.append(item)

        # Generate middle frame thumbnail for representation items missing AYON thumbnails
        from utils import ensure_repre_middle_frame_thumbnail
        sec_cfg = dict(self.config or {})
        sec_cfg.update(self.secrets or {})
        for item in items:
            try:
                ensure_repre_middle_frame_thumbnail(item, self.project_name, sec_cfg, ayon_client=self.ayon_client)
            except Exception as e:
                print(f"Error ensuring middle frame thumbnail for AYON item: {e}")

        self.finished_items.emit(items)
