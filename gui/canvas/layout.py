"""Item placement: layout memory, rearrange/arrange, sizes, framing, z-order.

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


class CanvasLayoutMixin:
    def _get_item_key(self, item_data):
        if not item_data:
            return None
        if getattr(item_data, "file_path", None):
            return item_data.file_path
        if getattr(item_data, "ayon_path", None):
            return item_data.ayon_path
        return id(item_data)

    def _remember_layout(self, thumbs=None):
        """Store the live position/size of thumbnails so a rebuilt item gets them back."""
        for thumb in (thumbs if thumbs is not None else list(self.item_to_thumb.values())):
            key = self._get_item_key(getattr(thumb, "data", None))
            if not key or isinstance(key, int):
                continue
            if getattr(thumb, "_placed", False) or getattr(thumb, "is_manually_moved", False):
                pos = thumb.pos()
                self.item_positions[key] = (pos.x(), pos.y())
            if getattr(thumb, "is_custom_size", False):
                self.item_sizes[key] = thumb.size

    def _restore_size(self, item_data):
        """Re-apply a remembered custom size to freshly scanned item data."""
        key = self._get_item_key(item_data)
        if key in self.item_sizes and not getattr(item_data, "is_custom_size", False):
            item_data.size = self.item_sizes[key]
            item_data.is_custom_size = True

    def clear_thumbnails(self):
        """Remove only thumbnails (keep notes, backdrops and drawings), remembering their layout."""
        self._remember_layout()
        self._stop_all_players()
        for item in list(self.scene.items()):
            if isinstance(item, ThumbnailItem):
                self.scene.removeItem(item)
        self.item_to_thumb.clear()
        self.scene_items_changed.emit()

    def clear_canvas(self):
        """Completely clear the scene of all elements, including thumbnails, notes, and backdrops."""
        self._remember_layout()
        if hasattr(self, "active_players"):
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
        if hasattr(self, "video_player"):
            self.video_player.clear_video()
        self.scene.clear()
        self.item_to_thumb.clear()
        self._marked_placement_pos = None  # new canvas: next scan starts with a fresh grid
        self.scene_items_changed.emit()

    def add_items(self, items=None):
        """Initial populate or full reset."""
        self._remember_layout()
        if hasattr(self, "active_players"):
            for player in list(self.active_players.values()):
                player.clear_video()
                player.deleteLater()
            self.active_players.clear()
        if hasattr(self, "video_player"):
            self.video_player.clear_video()

        # Remove only ThumbnailItem instances from the scene, preserving notes/backdrops
        for item in list(self.scene.items()):
            if isinstance(item, ThumbnailItem):
                self.scene.removeItem(item)
        self.item_to_thumb.clear()
        
        if items is None and self.model:
            items = getattr(self.model, "all_items", self.model.items)
            
        if not items: return

        # Cache current sizes to apply to new items
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()

        for item_data in items:
            thumb = ThumbnailItem(item_data)
            self._restore_size(item_data)
            is_custom = getattr(item_data, "is_custom_size", False)
            if not is_custom:
                size_to_use = thumb_size
                item_data.size = thumb_size
            else:
                size_to_use = getattr(item_data, "size", thumb_size)
            thumb.size = size_to_use
            thumb.is_custom_size = is_custom
            thumb.font_size = font_size
            thumb.update_tooltip(self.tooltip_templates, self.model)
            self.scene.addItem(thumb)
            self.item_to_thumb[item_data] = thumb
            
        self.rearrange_items()
        self.frame_all()

    def _on_rows_inserted(self, parent, first, last):
        font_size = self.slider_text_size.value()
        thumb_size = self.slider_thumb_size.value()
        all_items = getattr(self.model, "all_items", self.model.items)
        
        for row in range(first, last + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data not in self.item_to_thumb:
                    thumb = ThumbnailItem(item_data)
                    self._restore_size(item_data)
                    is_custom = getattr(item_data, "is_custom_size", False)
                    if not is_custom:
                        size_to_use = thumb_size
                        item_data.size = thumb_size
                    else:
                        size_to_use = getattr(item_data, "size", thumb_size)
                    thumb.size = size_to_use
                    thumb.is_custom_size = is_custom
                    thumb.font_size = font_size
                    thumb.update_tooltip(self.tooltip_templates, self.model)
                    self.scene.addItem(thumb)
                    self.item_to_thumb[item_data] = thumb
        self.rearrange_items()

    def _on_rows_removed(self, parent, first, last):
        all_items = getattr(self.model, "all_items", self.model.items)
        for row in range(first, last + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data in self.item_to_thumb:
                    thumb = self.item_to_thumb.pop(item_data)
                    self._remember_layout([thumb])
                    if hasattr(self, "active_players") and thumb in self.active_players:
                        player = self.active_players.pop(thumb)
                        player.clear_video()
                        player.deleteLater()
                    self.scene.removeItem(thumb)

    def _on_data_changed(self, top_left, bottom_right, roles=None):
        all_items = getattr(self.model, "all_items", self.model.items)
        for row in range(top_left.row(), bottom_right.row() + 1):
            if 0 <= row < len(all_items):
                item_data = all_items[row]
                if item_data in self.item_to_thumb:
                    thumb = self.item_to_thumb[item_data]
                    thumb.cached_label = ""
                    thumb.update_tooltip(self.tooltip_templates, self.model)
                    thumb.update()

    def rearrange_items(self, age_filter=None, search_text=None, ignore_text=None, force=False):
        if not self.item_to_thumb or not self.model: return
        
        for item in self.item_to_thumb.values():
            item.cached_label = ""
        
        if age_filter is not None:
            self._last_age_filter = age_filter
        if search_text is not None:
            self._last_search_text = search_text
        if ignore_text is not None:
            self._last_ignore_text = ignore_text
            
        age_enabled, age_val = self._last_age_filter
        search_term = self._last_search_text
        ignore_strings = self._last_ignore_text.lower().split() if getattr(self, "_last_ignore_text", "") else []

        v_stack_enabled = getattr(self.model, "v_stack_enabled", False)

        # Canvas has its own "Show Reviews" toggle (the spreadsheet one is separate)
        show_reviews = getattr(self, "show_reviews", False)

        visible_items = []
        all_items = getattr(self.model, "all_items", self.model.items)
        for item_data in all_items:
            item = self.item_to_thumb.get(item_data)
            if not item: continue
            
            # Visibility logic
            is_tagged = item_data.is_tagged
            item_abs = os.path.normpath(os.path.abspath(item_data.file_path))
            filter_abs = os.path.normpath(os.path.abspath(self._path_filter))
            in_path = not self._path_filter or (item_abs == filter_abs or item_abs.startswith(filter_abs + os.sep))
            
            show_by_tag = True
            if self._tag_filter_state == "enabled": show_by_tag = is_tagged
            elif self._tag_filter_state == "disabled": show_by_tag = not is_tagged
            
            is_young_enough = not age_enabled or (item_data.age_minutes < age_val)
            matches_search = (not search_term or 
                              search_term in item_data.label.lower() or 
                              search_term in item_data.filename.lower())
            
            is_ignored = False
            if ignore_strings:
                lbl_lower = item_data.label.lower()
                fn_lower = item_data.filename.lower()
                for ign in ignore_strings:
                    if ign in lbl_lower or ign in fn_lower:
                        is_ignored = True
                        break
            
            is_visible_ver = not v_stack_enabled or self.model.is_item_visible_by_v_stack(item_data, True)
            is_rev = getattr(item_data, "is_review_repre", False)
            
            is_rev = is_rev or getattr(item_data, "is_review", False)
            if show_by_tag and in_path and is_young_enough and matches_search and not is_ignored and is_visible_ver and (show_reviews or not is_rev):
                item.show()
                visible_items.append(item)
            else:
                item.hide()

        if not visible_items:
            return
            
        # Use last arrangement values
        vals = self._last_arrange_vals.copy()
        
        # Calculate horizontal gap dynamically: 20% of default thumbnail size
        dynamic_gap_h = int(self.slider_thumb_size.value() * 0.20)
        vals["gap_h"] = dynamic_gap_h
        self._last_arrange_vals["gap_h"] = dynamic_gap_h
        
        # Calculate vertical gap dynamically: 40% of average thumbnail height (metadata-driven height)
        total_h = 0.0
        count = 0
        for item in visible_items:
            w = item.data.metadata.get("width", None)
            h = item.data.metadata.get("height", None)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
                
            item_size = getattr(item, "size", self.slider_thumb_size.value())
            total_h += item_size / aspect
            count += 1
            
        if count > 0:
            avg_height = total_h / count
            dynamic_gap_v = int(avg_height * 0.20)
            vals["gap_v"] = dynamic_gap_v
            self._last_arrange_vals["gap_v"] = dynamic_gap_v
            
        if force:
            self._apply_arrangement(visible_items, "grid", vals, anchor=(0, 0), ignore_manual=False)
        else:
            already_placed = []
            unplaced = []
            for thumb in visible_items:
                key = self._get_item_key(thumb.data)
                has_pos = (
                    getattr(thumb, "_placed", False) or
                    getattr(thumb.data, "has_placed_position", False) or
                    getattr(thumb, "is_manually_moved", False) or
                    getattr(thumb.data, "is_manually_moved", False) or
                    (key in self.item_positions)
                )
                if has_pos:
                    if getattr(thumb, "_placed", False):
                        # Already laid out in this scene: the live position is the truth
                        # (covers moves and corner-resizes that shifted the item).
                        live = thumb.pos()
                        px, py = live.x(), live.y()
                    elif key in self.item_positions:
                        px, py = self.item_positions[key]
                    else:
                        px, py = thumb.data.position
                    thumb.setPos(px, py)
                    thumb.data.position = (px, py)
                    thumb.data.has_placed_position = True
                    thumb._placed = True
                    if key: self.item_positions[key] = (px, py)
                    already_placed.append(thumb)
                else:
                    unplaced.append(thumb)

            if unplaced and not already_placed and self._marked_placement_pos is None:
                # Very first layout of a fresh scan: use the default grid
                # (Preferences > GUI > Default columns / thumbnail size).
                self._apply_arrangement(unplaced, "grid", vals, anchor=(0, 0))
                unplaced = []

            if unplaced:
                if self._marked_placement_pos is not None:
                    start_x = self._marked_placement_pos.x()
                    start_y = self._marked_placement_pos.y()
                elif already_placed:
                    max_x = max(t.sceneBoundingRect().right() for t in already_placed)
                    min_y = min(t.sceneBoundingRect().top() for t in already_placed)
                    start_x = max_x + vals["gap_h"]
                    start_y = min_y
                else:
                    start_x = 0.0
                    start_y = 0.0

                gap_h = vals["gap_h"]
                gap_v = vals["gap_v"]

                # Get existing placed bounding rects (placed thumbnails, notes, backdrops, etc.)
                placed_rects = [
                    it.sceneBoundingRect() for it in self.scene.items()
                    if it.isVisible() and it not in unplaced
                ]

                curr_x = start_x
                for thumb in unplaced:
                    rect = thumb.boundingRect()
                    item_w = rect.width() if rect.width() > 0 else getattr(thumb, "size", 150) + gap_h
                    item_h = rect.height() if rect.height() > 0 else getattr(thumb, "size", 150) + 50 + gap_v

                    test_x = curr_x
                    test_y = start_y

                    # Shift test_y down by one item height + vertical gap if overlap detected
                    step_y = max(item_h + gap_v, 50.0)
                    while True:
                        test_rect = QRectF(test_x, test_y, item_w, item_h)
                        if any(test_rect.intersects(r) for r in placed_rects):
                            test_y += step_y
                        else:
                            break

                    thumb.setPos(test_x, test_y)
                    thumb.data.position = (test_x, test_y)
                    thumb.data.has_placed_position = True
                    thumb._placed = True
                    key = self._get_item_key(thumb.data)
                    if key:
                        self.item_positions[key] = (test_x, test_y)

                    placed_rects.append(QRectF(test_x, test_y, item_w, item_h))
                    curr_x = test_x + item_w + gap_h

                self._marked_placement_pos = QPointF(curr_x, start_y)

        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    def set_path_filter(self, path):
        self._path_filter = path
        self.rearrange_items()

    def _cycle_tag_filter(self):
        states = ["all", "enabled", "disabled"]
        curr_idx = states.index(self._tag_filter_state)
        self._tag_filter_state = states[(curr_idx + 1) % len(states)]
        self.btn_tag_filter.setText(f"Filter: {self._tag_filter_state.capitalize()}")
        self.rearrange_items()
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
        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    # ---- Thumb slider (spring-loaded, relative) ------------------------------
    # Dragging scales the selected items (or all visible ones when nothing is
    # selected) relative to their own size at the start of the drag. The layout is
    # kept: positions are scaled around the top-left corner of the items, like
    # zooming the arrangement. Only the image part of an item scales - its frame
    # padding and label area keep their size - so each row/column of items moves
    # by that fixed part too, and items neither overlap nor drift apart.

    def _begin_thumb_scale(self):
        sel = [it for it in self.scene.selectedItems() if isinstance(it, ThumbnailItem) and it.isVisible()]
        targets = sel or [it for it in self.item_to_thumb.values() if it.isVisible()]
        if not targets:
            self._thumb_scale = None
            return
        default = self.slider_thumb_size.value()
        moved = list(targets)
        for t in targets:  # paired reviews follow their main item (also hidden ones)
            for r in (getattr(t.data, "paired_reviews", None) or []):
                rt = self.item_to_thumb.get(r)
                if rt is not None and rt not in moved:
                    moved.append(rt)
        ax = min(t.pos().x() for t in moved)
        ay = min(t.pos().y() for t in moved)

        def ranks(values):
            """value -> number of distinct rows/columns (1 px tolerance) before it"""
            uniq = []
            for v in sorted(values):
                if not uniq or v - uniq[-1] > 1.0:
                    uniq.append(v)
            return lambda v: sum(1 for u in uniq if u < v - 1.0)

        col_rank = ranks([t.pos().x() for t in moved])
        row_rank = ranks([t.pos().y() for t in moved])
        show_text = self.btn_show_text.isChecked()
        fs = self.slider_text_size.value()
        label_area = (fs * 1.5 * 3.5 + 10) if show_text else 0
        self._thumb_scale = {
            "sizes": {it: float(getattr(it, "size", None) or default) for it in moved},
            "pos": {it: (it.pos().x(), it.pos().y(), col_rank(it.pos().x()), row_rank(it.pos().y()))
                    for it in moved},
            "anchor": (ax, ay),
            "fixed_w": 20.0,               # frame padding (does not scale)
            "fixed_h": 20.0 + label_area,  # padding + label area
            "all": not sel,
            "default": default,
        }

    def _on_thumb_scale(self, factor):
        st = getattr(self, "_thumb_scale", None)
        if st is None:
            self._begin_thumb_scale()
            st = self._thumb_scale
            if st is None:
                return
        from gui.canvas.thumbnail_item import MAX_ITEM_SIZE
        for it, s0 in st["sizes"].items():
            new = int(max(20, min(MAX_ITEM_SIZE, round(s0 * factor))))
            if getattr(it, "size", None) != new:
                it.prepareGeometryChange()
                it.size = new
                it.data.size = new
                it.is_custom_size = True
                it.data.is_custom_size = True
                it.update()
        ax, ay = st["anchor"]
        k = 1.0 - factor
        for it, (x0, y0, col, row) in st["pos"].items():
            x = ax + (x0 - ax) * factor + st["fixed_w"] * k * col
            y = ay + (y0 - ay) * factor + st["fixed_h"] * k * row
            it.setPos(x, y)
            it.data.position = (x, y)
            it.data.has_placed_position = True
            it._placed = True
            it.is_manually_moved = True
            it.data.is_manually_moved = True
            key = self._get_item_key(it.data)
            if key:
                self.item_positions[key] = (x, y)
        if st["all"]:
            # the size new items get follows when everything was scaled
            self.slider_thumb_size.setValue(st["default"] * factor)
        self._grow_scene_rect()
        self.scene.update()
        self.view.viewport().update()
        self.update_video_overlay_geometry()

    def _end_thumb_scale(self):
        self._thumb_scale = None

    def update_thumb_size(self):
        """Kept for old callers: the thumb slider now scales through _on_thumb_scale."""
        return

    def _visible_content_rect(self, items=None):
        """Scene rect of what is actually shown: visible top-level items only.

        QGraphicsScene.itemsBoundingRect() counts hidden items too (filtered-out files,
        paired reviews while Show Reviews is off), which left big empty areas in Frame All.
        Fading click markers and the temporary drawing canvas are skipped as well."""
        from PySide6.QtCore import QRectF
        from gui.canvas.drawing import DrawingCanvasItem
        rect = QRectF()
        for it in (items if items is not None else self.scene.items()):
            if it.parentItem() is not None or not it.isVisible():
                continue
            if getattr(it, "_is_placement_marker", False) or isinstance(it, DrawingCanvasItem):
                continue
            rect = rect.united(it.sceneBoundingRect()) if not rect.isNull() else it.sceneBoundingRect()
        return rect

    def _fit_rect(self, rect):
        """Zoom and pan so `rect` (scene coords) fills the view.

        Done by hand instead of QGraphicsView.fitInView: centring is limited to the
        scene rect, and content beyond it (big thumbnails reach far) or wider than
        it ended up off-centre. The scene rect is grown so the target can always be
        centred. Uses the viewport size of this moment, so it is right after panels
        were shown / hidden."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QTransform
        if rect.isNull() or rect.isEmpty():
            return
        win = self.window()
        if win is not None and win.layout() is not None:
            win.layout().activate()  # apply a pending resize (panel just shown / hidden)
        vp = self.view.viewport().rect()
        if vp.width() < 4 or vp.height() < 4:
            return
        m = max(10.0, 0.03 * max(rect.width(), rect.height()))
        target = rect.adjusted(-m, -m, m, m)
        s = min(vp.width() / target.width(), vp.height() / target.height())
        if s <= 0:
            return
        # room around the target so it can be centred (and panned a bit) at this zoom
        half_w = vp.width() / s
        half_h = vp.height() / s
        need = QRectF(target.center().x() - half_w, target.center().y() - half_h, 2 * half_w, 2 * half_h)
        sr = self.scene.sceneRect()
        if not sr.contains(need):
            self.scene.setSceneRect(sr.united(need))
        self.view.setTransform(QTransform.fromScale(s, s))
        self.view.centerOn(target.center())
        self.update_zoom_indicator()

    def _grow_scene_rect(self, include_content=True):
        """Keep room to pan: the scene rect (the area QGraphicsView lets you scroll over)
        always reaches several view-widths beyond what is on screen and beyond all
        content. Called after layout changes, on pan and on zoom. A fixed rect made an
        invisible wall - close on screen when zoomed far out (big thumbnails)."""
        from PySide6.QtCore import QRectF
        vp = self.view.viewport().rect()
        vis = self.view.mapToScene(vp).boundingRect()
        need = vis.adjusted(-4 * vis.width(), -4 * vis.height(), 4 * vis.width(), 4 * vis.height())
        if include_content:  # skipped on pan / zoom (every mouse move): only the view matters there
            r = self._visible_content_rect()
            if not (r.isNull() or r.isEmpty()):
                pad = max(r.width(), r.height())
                need = need.united(r.adjusted(-pad, -pad, pad, pad))
        sr = self.scene.sceneRect()
        if sr.contains(need):
            return
        new = sr.united(need)
        # Qt scrolls in int pixels: a rect that is too big at this zoom would overflow,
        # so start again from what is needed now
        scale = abs(self.view.transform().m11()) or 1.0
        if max(new.width(), new.height()) * scale > 1.0e9:
            new = need
        center = vis.center()
        self.scene.setSceneRect(new)
        self.view.centerOn(center)  # changing the rect must not move the view

    def frame_all(self):
        self._fit_rect(self._visible_content_rect())

    def frame_selection(self):
        items = self.scene.selectedItems()
        if not items: return
        
        self._fit_rect(self._visible_content_rect(items))

    def _show_placement_marker(self, pos):
        from PySide6.QtWidgets import QGraphicsEllipseItem
        from PySide6.QtGui import QPen, QColor, QBrush
        from PySide6.QtCore import QVariantAnimation
        
        if not hasattr(self, "_active_marker_anims"):
            self._active_marker_anims = []
            
        # Same size on screen at any zoom: drawn in pixels around the click point
        r = 8
        marker = QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
        marker.setPos(pos)
        marker.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        pen = QPen(QColor(0, 255, 255), 2)
        pen.setCosmetic(True)
        marker.setPen(pen)
        marker.setBrush(QBrush(QColor(0, 255, 255, 80)))
        marker.setZValue(9999)
        marker._is_placement_marker = True  # ignored by clicks (ThumbnailArea._item_at)
        marker.setAcceptedMouseButtons(Qt.NoButton)
        self.scene.addItem(marker)
        
        anim = QVariantAnimation()
        anim.setStartValue(0.5)  # starts half transparent
        anim.setEndValue(0.0)
        anim.setDuration(267)  # fades 1.5x faster than the original 400 ms
        
        self._active_marker_anims.append(anim)
        
        def update_opacity(val):
            marker.setOpacity(val)
            
        def remove_marker():
            if marker in self.scene.items():
                self.scene.removeItem(marker)
            if anim in self._active_marker_anims:
                self._active_marker_anims.remove(anim)
                
        anim.valueChanged.connect(update_opacity)
        anim.finished.connect(remove_marker)
        anim.start()

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
        all_items = getattr(self.model, "all_items", self.model.items)
        for item_data in all_items:
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

    def _select_all_items_in_stack(self, item):
        if not self.model: return
        key = self.model.get_version_stack_key(item)
        stack = self.model.version_stacks.get(key)
        if not stack: return
        
        self.scene.blockSignals(True)
        self.scene.clearSelection()
        for it in stack["items"]:
            thumb = self.item_to_thumb.get(it)
            if thumb:
                thumb.setSelected(True)
        self.scene.blockSignals(False)
        self.scene.selectionChanged.emit()

    def move_selected_to_front(self):
        """Raise selected ThumbnailItems above all other thumbnails."""
        all_thumbs = [it for it in self.scene.items() if isinstance(it, ThumbnailItem)]
        selected = [it for it in all_thumbs if it.isSelected()]
        others = [it for it in all_thumbs if not it.isSelected()]
        if not selected:
            return
        # Find the highest z among non-selected thumbnails
        base_z = max((it.zValue() for it in others), default=0)
        # Place each selected item above: cap at 4999 (below text notes at 5000)
        for i, it in enumerate(selected):
            it.setZValue(min(base_z + 1 + i, 4999))
        self.scene_items_changed.emit()

    def move_selected_to_back(self):
        """Lower selected ThumbnailItems below all other thumbnails."""
        all_thumbs = [it for it in self.scene.items() if isinstance(it, ThumbnailItem)]
        selected = [it for it in all_thumbs if it.isSelected()]
        others = [it for it in all_thumbs if not it.isSelected()]
        if not selected:
            return
        # Find the lowest z among non-selected thumbnails
        base_z = min((it.zValue() for it in others), default=0)
        # Place each selected item below: floor at -999 (above backdrops at -1000)
        for i, it in enumerate(reversed(selected)):
            it.setZValue(max(base_z - 1 - i, -999))
        self.scene_items_changed.emit()

    def _on_arrange(self, mode):
        if hasattr(self, "_arrange_dialog") and self._arrange_dialog:
            self._arrange_dialog.close()
            
        # 1. Identify target items
        selected = self.scene.selectedItems()
        # Filter for ThumbnailItems only
        target_items = [it for it in selected if isinstance(it, ThumbnailItem)]
        
        if not target_items:
            # Arrange all visible ThumbnailItems
            target_items = []
            all_items = getattr(self.model, "all_items", getattr(self.model, "items", []))
            for item_data in all_items:
                item = self.item_to_thumb.get(item_data)
                if item and item.isVisible() and item not in target_items:
                    target_items.append(item)
            for item in self.scene.items():
                if isinstance(item, ThumbnailItem) and item.isVisible() and item not in target_items:
                    target_items.append(item)
                    
        if not target_items: return
        
        # Store initial positions and sizes for revert (paired reviews may move too: Paired Follow)
        snap_items = list(target_items)
        for t in target_items:
            for r in (getattr(t.data, "paired_reviews", None) or []):
                rt = self.item_to_thumb.get(r)
                if rt is not None and rt not in snap_items:
                    snap_items.append(rt)
        initial_pos = {item: item.pos() for item in snap_items}
        initial_sizes = {item: (getattr(item, "size", self.slider_thumb_size.value()), getattr(item, "is_custom_size", False)) for item in snap_items}
        
        if "thumb_size" not in self._last_arrange_vals:
            first_size = initial_sizes[target_items[0]][0] if target_items else self.slider_thumb_size.value()
            self._last_arrange_vals["thumb_size"] = int(first_size)

        # Calculate top-left anchor point once
        anchor_x = min(initial_pos[t].x() for t in target_items)
        anchor_y = min(initial_pos[t].y() for t in target_items)
        anchor = (anchor_x, anchor_y)
        
        # 2. Show dialog
        self._arrange_dialog = ArrangeDialog(mode, self._last_arrange_vals, self)
        
        # Connect live updates
        self._arrange_dialog.valuesChanged.connect(lambda vals: self._apply_arrangement(target_items, mode, vals, anchor, mark_manual=True))
        
        def finalize():
            vals = self._arrange_dialog.get_values()
            self._apply_arrangement(target_items, mode, vals, anchor, mark_manual=True)
            self._last_arrange_vals = vals # Save for next time
            if target_items:
                max_x = max(it.sceneBoundingRect().right() for it in target_items)
                min_y = min(it.sceneBoundingRect().top() for it in target_items)
                self._marked_placement_pos = QPointF(max_x + vals.get("gap_h", 20), min_y)
            self._arrange_dialog = None
            
        def revert():
            for item, pos in initial_pos.items():
                item.setPos(pos)
                item.data.position = (pos.x(), pos.y())
                key = self._get_item_key(item.data)
                if key:
                    self.item_positions[key] = (pos.x(), pos.y())
                if item in initial_sizes:
                    old_size, old_custom = initial_sizes[item]
                    item.prepareGeometryChange()
                    item.size = old_size
                    item.data.size = old_size
                    item.is_custom_size = old_custom
                    item.data.is_custom_size = old_custom
                    item.update()
            self.scene.update()
            self._arrange_dialog = None
            
        self._arrange_dialog.accepted.connect(finalize)
        self._arrange_dialog.rejected.connect(revert)
        
        # Initial preview
        self._apply_arrangement(target_items, mode, self._arrange_dialog.get_values(), anchor, mark_manual=True)
        
        self._arrange_dialog.show()
        self._arrange_dialog.raise_()
        self._arrange_dialog.activateWindow()

    def _apply_arrangement(self, items, mode, vals, anchor=None, ignore_manual=False, mark_manual=False):
        if not items: return
        
        if ignore_manual:
            items = [item for item in items if not item.is_manually_moved]
            if not items: return
        
        arr_thumb_size = vals.get("thumb_size")
        if arr_thumb_size is not None:
            for item in items:
                if getattr(item, "size", None) != arr_thumb_size:
                    item.prepareGeometryChange()
                    item.size = arr_thumb_size
                    item.data.size = arr_thumb_size
                    item.is_custom_size = True
                    item.data.is_custom_size = True
                    item.update()

        # "Paired Follow": arrange only main items; their paired reviews (also hidden
        # ones) are placed directly below them afterwards (place_followers)
        followers = {}
        if vals.get("paired_follow", True):
            in_set = set(items)
            mains = []
            for t in items:
                main = getattr(t.data, "pair_main", None)
                mt = self.item_to_thumb.get(main) if main is not None else None
                if mt is None or mt not in in_set:
                    mains.append(t)
            for mt in mains:
                revs = [self.item_to_thumb.get(r) for r in (getattr(mt.data, "paired_reviews", None) or [])]
                revs = [r for r in revs if r is not None]
                if revs:
                    followers[mt] = revs
                    for r in revs:
                        if arr_thumb_size is not None and getattr(r, "size", None) != arr_thumb_size:
                            r.prepareGeometryChange()
                            r.size = arr_thumb_size
                            r.data.size = arr_thumb_size
                            r.is_custom_size = True
                            r.data.is_custom_size = True
                            r.update()
            items = mains
            if not items:
                return

        sort_by = vals.get("sort_by", "File Name")
        reverse = vals.get("reverse", False)
        
        # Sort items based on criteria
        def sort_key(thumb):
            d = thumb.data
            if sort_by == "File Name": return d.filename.lower()
            if sort_by == "Label": return d.label.lower()
            if sort_by == "Version": return d.version
            if sort_by == "File Size": 
                try: return int(d.metadata.get("filesize", 0))
                except (TypeError, ValueError): return 0
            if sort_by == "Width": 
                try: return int(d.metadata.get("width", 0))
                except (TypeError, ValueError): return 0
            if sort_by == "Height": 
                try: return int(d.metadata.get("height", 0))
                except (TypeError, ValueError): return 0
            if sort_by == "Age": return d.modification_time
            if sort_by == "File Type":
                _, ext = os.path.splitext(d.file_path.lower())
                return ext
            return 0

        items = sorted(items, key=sort_key, reverse=reverse)
        
        if anchor:
            start_x, start_y = anchor
        else:
            start_x = items[0].scenePos().x()
            start_y = items[0].scenePos().y()
        
        gap_h = vals["gap_h"]
        gap_v = vals["gap_v"]
        cols = vals["cols"]
        
        show_text = self.btn_show_text.isChecked()
        font_size = self.slider_text_size.value()
        line_height = font_size * 1.5
        label_area = (line_height * 3.5) + 10 if show_text else 0

        def get_item_w(thumb):
            t_size = getattr(thumb, "size", self.slider_thumb_size.value())
            return t_size + 20

        follow_gap = 10  # space between a main item and its paired review(s)

        def get_item_h(thumb):
            # a main item's cell also holds its paired reviews below it
            return base_item_h(thumb) + sum(base_item_h(r) + follow_gap for r in followers.get(thumb, []))

        def place_followers():
            for main_t, revs in followers.items():
                y = main_t.pos().y() + base_item_h(main_t) + follow_gap
                for r in revs:
                    r.setPos(main_t.pos().x(), y)
                    r.data.position = (main_t.pos().x(), y)
                    r.data.has_placed_position = True
                    r._placed = True
                    key = self._get_item_key(r.data)
                    if key: self.item_positions[key] = (main_t.pos().x(), y)
                    if mark_manual:
                        r.is_manually_moved = True
                        r.data.is_manually_moved = True
                    y += base_item_h(r) + follow_gap

        def base_item_h(thumb):
            w = thumb.data.metadata.get("width", 1)
            h = thumb.data.metadata.get("height", 1)
            try:
                fw = float(w) if w is not None else 1.0
                fh = float(h) if h is not None else 1.0
                aspect = fw / fh if fh > 0 else 1.0
            except (ValueError, TypeError):
                aspect = 1.0
            t_size = getattr(thumb, "size", self.slider_thumb_size.value())
            return (t_size / aspect) + 20 + label_area

        # For grid, we need to track row heights to keep them aligned
        row_heights = []
        if mode == "grid":
            current_max_h = 0
            for i, item in enumerate(items):
                h = get_item_h(item)
                current_max_h = max(current_max_h, h)
                if (i + 1) % cols == 0 or (i + 1) == len(items):
                    row_heights.append(current_max_h)
                    current_max_h = 0

        group_cols = vals.get("group_cols", False)
        if mode == "grid" and group_cols:
            groups = {}
            for item in items:
                gk = getattr(item.data, "group_key", "")
                if gk not in groups:
                    groups[gk] = []
                groups[gk].append(item)
                
            group_keys = list(groups.keys())
            
            col_widths = []
            for gk in group_keys:
                max_w = 0
                for item in groups[gk]:
                    max_w = max(max_w, get_item_w(item))
                col_widths.append(max_w)
                
            for c_idx, gk in enumerate(group_keys):
                g_items = groups[gk]
                current_y_offset = 0
                x_pos = sum(col_widths[:c_idx]) + (c_idx * gap_h)
                
                for item in g_items:
                    h = get_item_h(item)
                    new_x = start_x + x_pos
                    new_y = start_y + current_y_offset
                    
                    item.setPos(new_x, new_y)
                    item.data.position = (new_x, new_y)
                    item.data.has_placed_position = True
                    item._placed = True
                    key = self._get_item_key(item.data)
                    if key: self.item_positions[key] = (new_x, new_y)
                    if mark_manual:
                        item.is_manually_moved = True
                        item.data.is_manually_moved = True
                    current_y_offset += h + gap_v
            
            place_followers()
            self._grow_scene_rect()
            self.scene.update()
            return
            
        col_widths = []
        if mode == "grid":
            col_widths = [0] * max(1, min(cols, len(items)))
            for i, item in enumerate(items):
                c = i % cols
                col_widths[c] = max(col_widths[c], get_item_w(item))
        current_y_offset = 0
        for i, item in enumerate(items):
            h = get_item_h(item)
            w = get_item_w(item)
            
            if mode == "horizontal":
                new_x = start_x + i * (w + gap_h)
                new_y = start_y
            elif mode == "vertical":
                new_x = start_x
                new_y = start_y + current_y_offset
                current_y_offset += h + gap_v
            else: # grid (column width = widest item in the column)
                row = i // cols
                col = i % cols
                new_x = start_x + sum(col_widths[:col]) + col * gap_h
                y_pos = sum(row_heights[:row]) + (row * gap_v)
                new_y = start_y + y_pos
            
            item.setPos(new_x, new_y)
            item.data.position = (new_x, new_y)
            item.data.has_placed_position = True
            item._placed = True
            key = self._get_item_key(item.data)
            if key: self.item_positions[key] = (new_x, new_y)
            if mark_manual:
                item.is_manually_moved = True
                item.data.is_manually_moved = True
            
        place_followers()
        self._grow_scene_rect()
        self.scene.update()
