import os
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject, 
                             QMenu, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QCheckBox, 
                             QSpinBox, QLabel, QLineEdit, QSlider, QFrame)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize, QEvent, QTimer, QRegularExpression, QRunnable, QThreadPool, QObject
from PySide6.QtGui import QPainter, QPen, QColor, QAction, QPixmap, QFontMetrics, QRegularExpressionValidator, QImage, QFont, QTextOption
from utils import generate_thumbnail

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

    def boundingRect(self):
        # Dynamic height based on font size (approx 3.5 lines for label)
        font_size = getattr(self, 'font_size', 10)
        line_height = font_size * 1.5
        label_area = line_height * 3.5
        return QRectF(0, 0, self.size + 20, self.size + 20 + label_area)

    def paint(self, painter, option, widget):
        painter.save()
        # LOD check: skip complex stuff if tiny
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        
        pixmap = self.data.thumbnail
        if lod > 0.6:
            if self.data.high_res_thumbnail:
                pixmap = self.data.high_res_thumbnail
            elif not self.data.is_high_res_loading:
                self.request_high_res()

        if not pixmap:
            painter.fillRect(self.boundingRect(), QColor("#1e1e1e"))
            painter.restore()
            return

        # thumb_rect calculation - fixed area at top, label area below
        rect = QRectF(5, 5, self.boundingRect().width() - 10, self.size + 10)
        scaled = pixmap.size()
        scaled.scale(rect.size().toSize(), Qt.KeepAspectRatio)
        
        thumb_rect = QRectF(0, 0, scaled.width(), scaled.height())
        thumb_rect.moveCenter(rect.center())

        # Draw Borders - Use cosmetic pens for constant screen thickness
        # lod is inversely proportional to zoom-out.
        # base_w is the reference for overview thickness.
        base_w = 4
        if lod < 0.3:
            base_w = 12
        elif lod < 0.6:
            base_w = 8
            
        if self.isSelected():
            sel_width = base_w + 2
            pen = QPen(QColor("#ffffff"), sel_width)
            pen.setCosmetic(True)
            painter.setPen(pen)
        else:
            # Unselected border stays as is or follows base_w
            pen = QPen(QColor("#444444"), base_w // 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
        
        painter.drawRect(thumb_rect.adjusted(-4, -4, 4, 4))

        # Inner Border (Tagging) - Half of base_w
        if self.data.is_tagged:
            tag_color = QColor("#76ff03") if self.data.ayon_path else QColor("#558b2f")
        else:
            tag_color = QColor("#c62828")
        tag_pen = QPen(tag_color, base_w // 2)
        tag_pen.setCosmetic(True)
        painter.setPen(tag_pen)
        painter.drawRect(thumb_rect.adjusted(-2, -2, 2, 2))
        
        painter.drawPixmap(thumb_rect, pixmap, QRectF(pixmap.rect()))
        
        # Label - Only if zoomed in and NOT editing
        if lod > 0.2 and not self.is_editing:
            painter.setPen(QColor("#e0e0e0"))
            font = painter.font()
            font.setPointSize(getattr(self, 'font_size', 10))
            painter.setFont(font)
            
            fm = QFontMetrics(font)
            line_height = fm.lineSpacing()
            label_height = line_height * 3.2 # Room for 3 lines + small overflow
            
            # Align label area with the base thumbnail size (centered horizontally)
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

class ThumbnailWorkerSignals(QObject):
    finished = Signal(object, object) # item_data, pixmap

class ThumbnailWorker(QRunnable):
    def __init__(self, item_data, size=512):
        super().__init__()
        self.item_data = item_data
        self.size = size
        self.signals = ThumbnailWorkerSignals()

    def run(self):
        pixmap = generate_thumbnail(self.item_data.file_path, self.size)
        self.signals.finished.emit(self.item_data, pixmap)

class ThumbnailArea(QWidget):
    tag_toggle_requested = Signal()
    label_action_requested = Signal(str, object)
    maximize_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Controls Bar
        self.controls = QWidget()
        self.controls_layout = QHBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(5, 5, 5, 5)
        
        self.btn_frame_all = QPushButton("Frame All")
        self.btn_frame_all.clicked.connect(self.frame_all)
        
        self.btn_frame_sel = QPushButton("Frame Selection")
        self.btn_frame_sel.clicked.connect(self.frame_selection)
        
        self.slider_cols = QSpinBox()
        self.slider_cols.setRange(5, 100)
        self.slider_cols.setValue(12)
        self.slider_cols.valueChanged.connect(self._on_spinner_changed)

        self.slider_text_size = QSlider(Qt.Horizontal)
        self.slider_text_size.setRange(4, 64)
        self.slider_text_size.setValue(10)
        self.slider_text_size.setFixedWidth(100)
        self.slider_text_size.valueChanged.connect(self.update_font_size)

        self.slider_thumb_size = QSlider(Qt.Horizontal)
        self.slider_thumb_size.setRange(20, 1024)
        self.slider_thumb_size.setValue(150)
        self.slider_thumb_size.setFixedWidth(100)
        self.slider_thumb_size.valueChanged.connect(self.update_thumb_size)

        self.btn_tag_filter = QPushButton("Filter: All")
        self.btn_tag_filter.clicked.connect(self._cycle_tag_filter)
        self._tag_filter_state = "all" # all, tagged, untagged

        self.btn_maximize = QPushButton("Maximize")
        self.btn_maximize.setCheckable(True)
        self.btn_maximize.clicked.connect(self.maximize_toggle_requested.emit)

        def add_v_line(layout):
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("color: #444444; margin: 2px;")
            layout.addWidget(line)

        self.controls_layout.addWidget(self.btn_frame_all)
        self.controls_layout.addWidget(self.btn_frame_sel)
        add_v_line(self.controls_layout)
        self.controls_layout.addWidget(QLabel("Cols:"))
        self.controls_layout.addWidget(self.slider_cols)
        add_v_line(self.controls_layout)
        self.controls_layout.addWidget(QLabel("Text:"))
        self.controls_layout.addWidget(self.slider_text_size)
        self.controls_layout.addWidget(QLabel("Thumb:"))
        self.controls_layout.addWidget(self.slider_thumb_size)
        self.controls_layout.addStretch()
        self.controls_layout.addWidget(self.btn_tag_filter)
        self.controls_layout.addWidget(self.btn_maximize)
        
        self.layout.addWidget(self.controls)

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
        self.view.setScene(self.scene)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.view.setBackgroundBrush(QColor("#1e1e1e"))
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self) # For key logic
        
        self._is_panning = False
        self._last_pan_pos = None
        
        self.inline_editor = QLineEdit(self.view.viewport())
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
        
        # Robust Mapping: ImageItem instance -> ThumbnailItem
        self.item_to_thumb = {}
        self.model = None
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)
        self._has_selection = False
        self._path_filter = ""
        self._last_age_filter = (False, 0)
        self._last_search_text = ""

    def _on_scene_selection_changed(self):
        self._has_selection = bool(self.scene.selectedItems())
        self.scene.update()

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

        for item_data in items:
            thumb = ThumbnailItem(item_data)
            self.scene.addItem(thumb)
            self.item_to_thumb[item_data] = thumb
            
        self.rearrange_items()
        self.frame_all()

    def _on_rows_inserted(self, parent, first, last):
        for row in range(first, last + 1):
            item_data = self.model.items[row]
            if item_data not in self.item_to_thumb:
                thumb = ThumbnailItem(item_data)
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

        # Variables for folder-based layout
        current_folder = None
        current_row = 0
        current_col = 0
        y_offset = 0
        # Dynamic spacing based on current sizes
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()
        line_height = font_size * 1.5
        # thumb area + margins + label
        thumb_h = int(thumb_size + 25 + (line_height * 3.5))
        thumb_h = max(100, thumb_h)
        
        spacing_x = thumb_size + 50
        gap = int(thumb_h * 0.5 * 0.33)
        
        # Follow the order defined in the model
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
            
            if not (show_by_tag and in_path and is_young_enough and matches_search):
                item.hide()
                continue
            
            item.show()
            
            # Layout logic
            folder = os.path.dirname(item_data.file_path)
            if folder != current_folder:
                if current_folder is not None:
                    current_row += 1
                    y_offset += gap
                current_folder = folder
                current_col = 0
            
            # Snap to grid
            new_x = current_col * spacing_x
            new_y = (current_row * thumb_h) + y_offset
            
            if item.pos() != QPointF(new_x, new_y):
                item.setPos(new_x, new_y)
                item_data.position = (new_x, new_y)
            item.is_manually_moved = False
            
            current_col += 1
            if current_col >= cols:
                current_col = 0
                current_row += 1

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
        self.rearrange_items()

    def update_thumb_size(self):
        new_size = self.slider_thumb_size.value()
        for item in self.item_to_thumb.values():
            item.prepareGeometryChange()
            item.size = new_size
            item.update()
        self.rearrange_items()

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
                angle = event.angleDelta().y()
                factor = 1.15 if angle > 0 else 1 / 1.15
                self.view.scale(factor, factor)
                self.update_zoom_indicator()
                return True # Prevent default scrolling/panning
        
        if event.type() == QEvent.MouseButtonPress:
            if source is self.view.viewport():
                is_middle = event.button() == Qt.MiddleButton
                is_ctrl_left = event.button() == Qt.LeftButton and (event.modifiers() & Qt.ControlModifier)
                
                if is_middle or is_ctrl_left:
                    self._is_panning = True
                    self._last_pan_pos = event.pos()
                    self.view.viewport().setCursor(Qt.ClosedHandCursor)
                    return True
                    
                if not self.view.itemAt(event.pos()):
                    self.scene.clearSelection()

        if event.type() == QEvent.MouseMove:
            if self._is_panning:
                delta = event.pos() - self._last_pan_pos
                self._last_pan_pos = event.pos()
                
                # Use translate instead of scrollbars for "infinite" panning
                # We need to account for current scale
                factor = self.view.transform().m11()
                self.view.translate(delta.x() / factor, delta.y() / factor)
                return True

        if event.type() == QEvent.MouseButtonRelease:
            if self._is_panning:
                self._is_panning = False
                self.view.viewport().setCursor(Qt.ArrowCursor)
                return True
        
        if event.type() == QEvent.MouseButtonDblClick:
            if source is self.view.viewport():
                item = self.view.itemAt(event.pos())
                if item:
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
                
            # Global shortcuts (only when editor is NOT active)
            if event.key() == Qt.Key_Space:
                if self.view.underMouse():
                    self.maximize_toggle_requested.emit()
                    return True
            elif event.key() in [Qt.Key_Plus, Qt.Key_Equal]:
                if self.view.underMouse():
                    self.view.scale(1.15, 1.15)
                    self.update_zoom_indicator()
                    return True
            elif event.key() == Qt.Key_Minus:
                if self.view.underMouse():
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
        
        if event.type() == QEvent.Gesture:
            return self.gestureEvent(event)
            
        return super().eventFilter(source, event)

    def _start_inline_rename(self, item):
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
        editor_w = max(item.size, text_w)
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
        tag_action = QAction("Tag/Untag Selected", self)
        tag_action.triggered.connect(self.tag_toggle_requested.emit)
        menu.addAction(tag_action)
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
        menu.exec(event.globalPos())

    def wheelEvent(self, event):
        # Base wheel events for the widget itself (if any)
        super().wheelEvent(event)

    def load_high_res(self, graph_item):
        item_data = graph_item.data
        if item_data.is_high_res_loading or item_data.high_res_thumbnail:
            return
        item_data.is_high_res_loading = True
        worker = ThumbnailWorker(item_data, size=512)
        worker.signals.finished.connect(self._on_high_res_loaded)
        self.thread_pool.start(worker)

    def _on_high_res_loaded(self, item_data, pixmap):
        item_data.high_res_thumbnail = pixmap
        item_data.is_high_res_loading = False
        if item_data in self.item_to_thumb:
            self.item_to_thumb[item_data].on_high_res_ready()
