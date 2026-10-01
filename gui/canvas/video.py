"""Inline video players and high-resolution image loading.

Mixin of ThumbnailArea (gui/thumbnail_area.py).
"""
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
from gui.canvas.widgets import ColorButton, BackdropDialog, NoteToolbar, DrawToolbar, SequenceRenameDialog, ArrangeDialog
from gui.canvas.thumbnail_item import ThumbnailItem, ThumbnailWorkerSignals, ThumbnailWorker
from gui.canvas.scene_items import NoteTextItem, TextNoteItem, BackdropItem
from gui.canvas.drawing import draw_arrow, get_non_transparent_rect, DrawingCanvasItem, DrawItem


class CanvasVideoMixin:
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

    def _stop_all_players(self):
        if hasattr(self, "active_players"):
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
        if hasattr(self, "video_player"):
            self.video_player.clear_video()

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
