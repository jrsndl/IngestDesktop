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
from gui.canvas.widgets import ColorButton, BackdropDialog, NoteToolbar, DrawToolbar, SequenceRenameDialog, ArrangeDialog  # noqa: F401 (re-exported)
from gui.canvas.thumbnail_item import ThumbnailItem, ThumbnailWorkerSignals, ThumbnailWorker  # noqa: F401 (re-exported)
from gui.canvas.scene_items import NoteTextItem, TextNoteItem, BackdropItem, CanvasScene  # noqa: F401 (re-exported)
from gui.canvas.drawing import draw_arrow, get_non_transparent_rect, DrawingCanvasItem, DrawItem  # noqa: F401 (re-exported)
from gui.canvas.layout import CanvasLayoutMixin
from gui.canvas.annotations import CanvasAnnotationsMixin
from gui.canvas.video import CanvasVideoMixin


class ThumbnailArea(CanvasLayoutMixin, CanvasAnnotationsMixin, CanvasVideoMixin, QWidget):
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
        # Layout memory, keyed by file path (see _get_item_key). Survives rescans,
        # filtering, preference changes, etc. so user placement is never lost.
        self.item_positions = {}
        self.item_sizes = {}
        
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
        self.scene = CanvasScene(self)  # keeps Python items alive (see CanvasScene)
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

    def _on_scene_selection_changed(self):
        self._has_selection = bool(self.scene.selectedItems())
        # Note: Qt automatically schedules repaints for selection changes;
        # calling scene.update() here would cause a race with in-progress
        # item updates (e.g. QGraphicsTextItem cursor changes) and make notes disappear.
        self._update_note_toolbar()
        self.update_video_overlay_geometry()

    def setModel(self, model):
        self.model = model
        self.model.rowsInserted.connect(self._on_rows_inserted)
        self.model.rowsAboutToBeRemoved.connect(self._on_rows_removed)
        self.model.modelReset.connect(self.add_items)
        self.model.dataChanged.connect(self._on_data_changed)

    def update_label_validator(self, regex_str):
        # Temporarily disabled per user request
        pass

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
                    
                # Decide "empty canvas" before the placement marker is added under the mouse
                clicked_empty = self.view.itemAt(event.pos()) is None
                if event.button() == Qt.LeftButton:
                    if clicked_empty:
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
                    if clicked_empty:
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

        self._exec_context_menu(menu, event.globalPos())

    def _exec_context_menu(self, menu, global_pos):
        """Show the canvas context menu (separate so tests can capture it without a popup)."""
        menu.exec(global_pos)

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
