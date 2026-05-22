import os
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, 
                             QHBoxLayout, QLabel, QSpinBox, QTreeView, QFileSystemModel, 
                             QButtonGroup, QComboBox, QAbstractItemView, QCheckBox,
                             QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication)
from PySide6.QtCore import Signal, Qt, QDir, QSortFilterProxyModel, QItemSelectionModel, QModelIndex, QRect
from PySide6.QtGui import QColor, QStandardItemModel, QStandardItem, QPalette, QFont, QPen, QIcon, QPixmap, QPainter
from utils import strip_sequence_counter, get_version_from_name

def get_review_icon(review_status):
    if not hasattr(get_review_icon, "_cache"):
        get_review_icon._cache = {}
    if review_status in get_review_icon._cache:
        return get_review_icon._cache[review_status]
        
    color_map = {
        "done": QColor("#44ff44"), # green
        "failed": QColor("#ff4444"), # red
        "processing": QColor("#ffaa00"), # orange
        "waiting": QColor("#ffaa00"), # orange
    }
    r_color = QColor("#888888") # default gray
    for status, color in color_map.items():
        if review_status == status or (isinstance(review_status, str) and review_status.startswith(status)):
            r_color = color
            break
            
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    
    font = QFont("Arial", 11, QFont.Bold)
    painter.setFont(font)
    painter.setPen(r_color)
    painter.drawText(0, 0, 16, 16, Qt.AlignCenter, "R")
    painter.end()
    
    icon = QIcon(pixmap)
    get_review_icon._cache[review_status] = icon
    return icon

class TagColorProxyModel(QSortFilterProxyModel):
    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.main_model = main_model
        
        # Current filter state for coloring
        self._search_text = ""
        self._age_limit = 0
        self._age_enabled = False
        
        # Sequence settings
        self.detect_sequences = True
        self.version_regex = r"([._]v|v)(\d+)"
        
        # Extra filters
        self.files_only = True
        self.v_stack = False
        
        # Fast lookup: normalized_abs_path -> (is_tagged, age_minutes, label)
        self._path_info = {}
        self._sequence_map = {} # (dir, base, ext, ver) -> item
        self._rebuild_cache()
        
        self.main_model.dataChanged.connect(self._on_model_data_changed)
        self.main_model.modelReset.connect(self._rebuild_cache)

    def set_filters(self, search_text, age_limit, age_enabled):
        self._search_text = search_text.lower()
        self._age_limit = age_limit
        self._age_enabled = age_enabled
        self.invalidateFilter() # Triggers data redraw

    def set_extra_filters(self, files_only=True, v_stack=False, sequences=True):
        self.files_only = files_only
        self.v_stack = v_stack
        self.detect_sequences = sequences
        self._rebuild_cache()

    def _rebuild_cache(self):
        self._path_info = {}
        self._sequence_map = {}
        self._max_version_map = {} # (dir, base, ext) -> max_version
        
        for item in self.main_model.items:
            abs_path = os.path.normpath(os.path.abspath(item.file_path))
            self._path_info[abs_path] = (item.is_tagged, item.age_minutes, item.label, item.review_status, item.filename)
            
            directory = os.path.dirname(abs_path)
            filename = os.path.basename(abs_path)
            version = get_version_from_name(filename, self.version_regex)
            name_no_ver = re.sub(self.version_regex, "", filename)
            ext = os.path.splitext(filename)[1].lower()
            
            # For Version Stack
            if version is not None:
                base_key = (directory, name_no_ver, ext)
                if base_key not in self._max_version_map or version > self._max_version_map[base_key]:
                    self._max_version_map[base_key] = version
            
            if self.detect_sequences and item.is_sequence:
                base_name = strip_sequence_counter(name_no_ver)
                key = (directory, base_name, ext, version)
                self._sequence_map[key] = item
                
        self.invalidateFilter()

    def _get_item_info(self, source_index):
        """Returns (abs_path, is_dir, is_scene) for an index."""
        model = self.sourceModel()
        if hasattr(model, "filePath"):
            return os.path.normpath(os.path.abspath(model.filePath(source_index))), model.isDir(source_index), False
        
        # QStandardItemModel (Flat view)
        is_scene = source_index.data(Qt.UserRole + 1)
        if is_scene:
            return None, False, True
            
        path = source_index.data(Qt.UserRole)
        return (os.path.normpath(os.path.abspath(path)) if path else None), False, False

    def _on_model_data_changed(self, tl, br):
        self._rebuild_cache()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        abs_path, is_dir, is_scene = self._get_item_info(idx)
        
        # When Files Only is OFF, display ONLY non-file scene items (backdrops, text notes)
        if not self.files_only:
            return is_scene
            
        # Files Only is ON: hide all scene items
        if is_scene:
            return False
            
        file_name = source_model.fileName(idx) if hasattr(source_model, "fileName") else source_model.data(idx)
        if file_name and str(file_name).lower().endswith(("_thumbnail.png", "_thumbnail.jpg")):
            return False

        # Files Only logic
        if self.files_only and not is_dir:
            if not abs_path or abs_path not in self._path_info:
                return False
            
        if not is_dir and abs_path:
            directory = os.path.dirname(abs_path)
            filename = os.path.basename(abs_path)
            version = get_version_from_name(filename, self.version_regex)
            name_no_ver = re.sub(self.version_regex, "", filename)
            ext = os.path.splitext(filename)[1].lower()

            # Version Stack logic
            if self.v_stack and version is not None:
                base_key = (directory, name_no_ver, ext)
                if base_key in self._max_version_map:
                    if version < self._max_version_map[base_key]:
                        return False

            # Sequence logic
            if self.detect_sequences:
                base_name = strip_sequence_counter(name_no_ver)
                key = (directory, base_name, ext, version)
                if key in self._sequence_map:
                    item = self._sequence_map[key]
                    item_abs_path = os.path.normpath(os.path.abspath(item.file_path))
                    if abs_path != item_abs_path:
                        return False
                    
        return super().filterAcceptsRow(source_row, source_parent)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and self.detect_sequences:
            source_index = self.mapToSource(index)
            abs_path, is_dir, is_scene = self._get_item_info(source_index)
            
            if not is_dir and abs_path:
                directory = os.path.dirname(abs_path)
                filename = os.path.basename(abs_path)
                
                version = get_version_from_name(filename, self.version_regex)
                name_no_ver = re.sub(self.version_regex, "", filename)
                base_name = strip_sequence_counter(name_no_ver)
                ext = os.path.splitext(filename)[1].lower()
                
                key = (directory, base_name, ext, version)
                if key in self._sequence_map:
                    item = self._sequence_map[key]
                    display_name = strip_sequence_counter(filename)
                    # Nuke notation: filename[first-last].extension
                    return f"{display_name}[{item.frame_start}-{item.frame_end}]{ext}"

        if role == Qt.DecorationRole:
            source_index = self.mapToSource(index)
            abs_path, is_dir, is_scene = self._get_item_info(source_index)
            if abs_path and not is_dir and not is_scene:
                info = self._path_info.get(abs_path)
                if info and len(info) >= 4:
                    review_status = info[3]
                    if review_status and review_status != "do not convert":
                        return get_review_icon(review_status)

        if role == Qt.ForegroundRole:
            source_index = self.mapToSource(index)
            abs_path, is_dir, is_scene = self._get_item_info(source_index)
            
            if is_scene:
                return QColor("#00bcd4") # Cyan for scene items
            
            if abs_path and abs_path in self._path_info:
                info = self._path_info[abs_path]
                is_tagged, age_min, label, review_status, filename = info[0], info[1], info[2], info[3], info[4]
                
                # Check filter match: search label or whole file name (including extension)
                matches_search = (not self._search_text or 
                                  self._search_text in label.lower() or 
                                  self._search_text in filename.lower())
                matches_age = not self._age_enabled or (age_min <= self._age_limit)
                matches_filters = matches_search and matches_age
                
                if matches_filters:
                    if is_tagged:
                        return QColor("#ffffff") # White
                    else:
                        return QColor("#ff4444") # Red
                else:
                    if is_tagged:
                        return QColor("#888888") # Gray
                    else:
                        return QColor("#800000") # Dark Red
            else:
                # Default for folders or items not in model
                return QColor("#aaaaaa")
        
        return super().data(index, role)



class FilterPanel(QWidget):
    search_changed = Signal(str)
    age_changed = Signal(int, str, bool) # value, units, enabled
    folder_selected = Signal(str)
    rename_to_label_requested = Signal(list) # list of paths
    sequences_toggled = Signal(bool)
    toggles_changed = Signal()
    delete_scene_items_requested = Signal(list) # list of UUIDs
    edit_scene_item_requested = Signal(str) # UUID

    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.main_model = main_model
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Search Filter
        search_layout = QHBoxLayout()
        self.chk_search = QCheckBox("Search:")
        self.chk_search.setChecked(True)
        self.chk_search.toggled.connect(self._on_search_change)
        search_layout.addWidget(self.chk_search)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("filter by file name")
        self.search_bar.setMaxLength(20)
        self.search_bar.textChanged.connect(self._on_search_change)
        search_layout.addWidget(self.search_bar)
        self.layout.addLayout(search_layout)

        # Age Filter
        age_layout = QHBoxLayout()
        self.chk_age = QCheckBox("Age:")
        self.chk_age.setChecked(False)
        self.chk_age.toggled.connect(self._on_age_change)
        age_layout.addWidget(self.chk_age)
        
        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 1000)
        self.spin_age.valueChanged.connect(self._on_age_change)
        self.combo_units = QComboBox()
        self.combo_units.addItems(["minutes", "hours", "days"])
        self.combo_units.currentTextChanged.connect(self._on_age_change)
        age_layout.addWidget(self.spin_age)
        age_layout.addWidget(self.combo_units)
        self.layout.addLayout(age_layout)

        # Folder Tree
        self.fs_model = QFileSystemModel()
        self.fs_model.setFilter(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)
        
        # Proxy for coloring
        self.proxy = TagColorProxyModel(self.main_model)
        self.proxy.setSourceModel(self.fs_model)
        
        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        for i in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(i)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.clicked.connect(self._on_folder_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.layout.addWidget(self.tree)

        self._scene_items = [] # List of dicts with {name, label, type, etc}

        # Toggle Buttons Row
        toggles_layout = QHBoxLayout()
        self.btn_files_only = QPushButton("Files")
        self.btn_files_only.setCheckable(True)
        self.btn_files_only.setChecked(True)
        self.btn_files_only.toggled.connect(self._on_toggles_changed)
        
        self.btn_flat = QPushButton("Flat")
        self.btn_flat.setCheckable(True)
        self.btn_flat.setChecked(False)
        self.btn_flat.toggled.connect(self._on_toggles_changed)
        
        self.btn_v_stack = QPushButton("Version Stack")
        self.btn_v_stack.setCheckable(True)
        self.btn_v_stack.setChecked(False)
        self.btn_v_stack.toggled.connect(self._on_toggles_changed)
        
        self.btn_sequences = QPushButton("Sequences")
        self.btn_sequences.setCheckable(True)
        self.btn_sequences.setChecked(True)
        self.btn_sequences.toggled.connect(self._on_toggles_changed)
        
        toggles_layout.addWidget(self.btn_files_only)
        toggles_layout.addWidget(self.btn_flat)
        toggles_layout.addWidget(self.btn_v_stack)
        toggles_layout.addWidget(self.btn_sequences)
        self.layout.addLayout(toggles_layout)

    def _on_toggles_changed(self):
        # Check if sequence toggle changed to trigger global rescan if needed
        new_seq = self.btn_sequences.isChecked()
        if new_seq != self.proxy.detect_sequences:
            self.sequences_toggled.emit(new_seq)
            
        self.proxy.set_extra_filters(
            files_only=self.btn_files_only.isChecked(),
            v_stack=self.btn_v_stack.isChecked(),
            sequences=new_seq
        )
        if self.btn_flat.isChecked():
            self._enable_flat_view()
        elif not self.btn_files_only.isChecked():
            self._enable_hierarchical_scene_view()
        else:
            self._disable_flat_view()
            
        self.toggles_changed.emit()

    def get_toggle_states(self):
        return {
            "files_only": self.btn_files_only.isChecked(),
            "flat": self.btn_flat.isChecked(),
            "v_stack": self.btn_v_stack.isChecked(),
            "sequences": self.btn_sequences.isChecked()
        }

    def set_toggle_states(self, states):
        if not states: return
        self.btn_files_only.blockSignals(True)
        self.btn_flat.blockSignals(True)
        self.btn_v_stack.blockSignals(True)
        self.btn_sequences.blockSignals(True)
        
        self.btn_files_only.setChecked(states.get("files_only", True))
        self.btn_flat.setChecked(states.get("flat", False))
        self.btn_v_stack.setChecked(states.get("v_stack", False))
        self.btn_sequences.setChecked(states.get("sequences", True))
        
        self.btn_files_only.blockSignals(False)
        self.btn_flat.blockSignals(False)
        self.btn_v_stack.blockSignals(False)
        self.btn_sequences.blockSignals(False)
        
        # Trigger one refresh
        self._on_toggles_changed()

    def _enable_flat_view(self):
        """Switch to a flat list of all project items."""
        if not hasattr(self, "flat_model"):
            self.flat_model = QStandardItemModel()
        
        self.flat_model.clear()
        
        # Populate from main_model.items
        for item in self.main_model.items:
            std_item = QStandardItem(item.filename)
            std_item.setData(item.file_path, Qt.UserRole)
            std_item.setData(False, Qt.UserRole + 1)
            self.flat_model.appendRow(std_item)
            
        # Add notes/backdrops if not files_only
        if not self.btn_files_only.isChecked():
            for s_item in self._scene_items:
                name = s_item.get("name", "")
                label = s_item.get("label", "Note")
                display = f"{label} ({name})" if name else label
                std_item = QStandardItem(display)
                std_item.setData(s_item.get("id"), Qt.UserRole)
                std_item.setData(True, Qt.UserRole + 1) # Is scene item flag
                self.flat_model.appendRow(std_item)

        self.proxy.setSourceModel(self.flat_model)
        self._update_column_visibility()

    def _update_column_visibility(self):
        """Ensure only the first column is visible."""
        for i in range(1, self.proxy.columnCount()):
            self.tree.hideColumn(i)

    def _disable_flat_view(self):
        """Switch back to hierarchical folder tree."""
        self.proxy.setSourceModel(self.fs_model)
        root_path = self.fs_model.rootPath()
        if root_path:
            self.set_root_folder(root_path)
        self._update_column_visibility()

    def _enable_hierarchical_scene_view(self):
        """Build a hierarchical model with scene items at the top."""
        if not hasattr(self, "scene_hier_model"):
            self.scene_hier_model = QStandardItemModel()
        
        self.scene_hier_model.clear()
        
        # 1. Add Scene Items at the very top
        for s_item in self._scene_items:
            label = s_item.get("name") or s_item.get("label", "Note")
            std_item = QStandardItem(label)
            std_item.setData(s_item.get("id"), Qt.UserRole)
            std_item.setData(True, Qt.UserRole + 1)
            self.scene_hier_model.appendRow(std_item)
            
        # 2. Add Project Structure
        # To avoid building the entire filesystem, we'll only add items from main_model.items
        # and build the folder tree for them.
        root_path = self.fs_model.rootPath()
        if not root_path:
            self.proxy.setSourceModel(self.scene_hier_model)
            return
            
        root_path = os.path.normpath(root_path)
        folders = {} # path -> QStandardItem
        
        # Helper to get/create folder item
        def get_folder_item(path):
            path = os.path.normpath(path)
            if path == root_path:
                return self.scene_hier_model
            if path in folders:
                return folders[path]
                
            parent_path = os.path.dirname(path)
            parent_item = get_folder_item(parent_path)
            
            folder_item = QStandardItem(os.path.basename(path))
            folder_item.setData(path, Qt.UserRole)
            folder_item.setData(False, Qt.UserRole + 1)
            # Generic folder icon? (Optional)
            
            parent_item.appendRow(folder_item)
            folders[path] = folder_item
            return folder_item

        for item in self.main_model.items:
            path = os.path.normpath(item.file_path)
            if not path.startswith(root_path): continue
            
            dir_path = os.path.dirname(path)
            parent_item = get_folder_item(dir_path)
            
            file_item = QStandardItem(item.filename)
            file_item.setData(path, Qt.UserRole)
            file_item.setData(False, Qt.UserRole + 1)
            parent_item.appendRow(file_item)
            
        self.proxy.setSourceModel(self.scene_hier_model)
        self.tree.expandAll() # Expand virtual tree by default
        self._update_column_visibility()

    def set_scene_items(self, items):
        """Update the list of scene items (notes, backdrops) and refresh if needed."""
        self._scene_items = items
        if self.btn_flat.isChecked() or not self.btn_files_only.isChecked():
            self._on_toggles_changed()

    def set_sequence_detection(self, enabled, regex):
        """Update sequence detection settings and rebuild cache."""
        self.proxy.detect_sequences = enabled
        self.proxy.version_regex = regex
        self.proxy._rebuild_cache()

    def set_root_folder(self, path):
        self.fs_model.setRootPath(path)
        if self.proxy.sourceModel() == self.fs_model:
            source_idx = self.fs_model.index(path)
            proxy_idx = self.proxy.mapFromSource(source_idx)
            self.tree.setRootIndex(proxy_idx)
            # Expand the root folder contents
            self.tree.expand(proxy_idx)
        else:
            # For virtual models, the root is always index(0,0) or similar
            self.tree.setRootIndex(QModelIndex())

    def select_paths(self, paths):
        """Programmatically select multiple files in the tree."""
        selection = self.tree.selectionModel()
        selection.clear()
        
        if not paths: return
        
        # Use QItemSelection for multiple items efficiently
        from PySide6.QtCore import QItemSelection
        tree_selection = QItemSelection()
        
        first_idx = None
        model = self.proxy.sourceModel()
        
        for p in paths:
            is_path = isinstance(p, str) and (os.sep in p or "/" in p or os.path.exists(p))
            norm_p = os.path.normpath(os.path.abspath(p)) if is_path else p
            source_idx = QModelIndex()
            
            if hasattr(model, "rootPath"): # QFileSystemModel
                source_idx = model.index(norm_p)
            else: # QStandardItemModel
                norm_p_lower = norm_p.lower() if isinstance(norm_p, str) else norm_p
                for row in range(model.rowCount()):
                    idx = model.index(row, 0)
                    val = idx.data(Qt.UserRole)
                    if isinstance(val, str):
                        val_norm = os.path.normpath(os.path.abspath(val)).lower()
                        if val_norm == norm_p_lower:
                            source_idx = idx
                            break
                    elif val == norm_p:
                        source_idx = idx
                        break
                        
            if source_idx.isValid():
                proxy_idx = self.proxy.mapFromSource(source_idx)
                tree_selection.select(proxy_idx, proxy_idx)
                if first_idx is None: first_idx = proxy_idx
                
                # Ensure parent is expanded
                p_idx = proxy_idx.parent()
                while p_idx.isValid():
                    self.tree.expand(p_idx)
                    p_idx = p_idx.parent()
        
        if not tree_selection.isEmpty():
            selection.select(tree_selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        
        if first_idx:
            self.tree.scrollTo(first_idx)

    def _on_folder_click(self, index):
        source_index = self.proxy.mapToSource(index)
        model = self.proxy.sourceModel()
        if hasattr(model, "filePath"):
            path = model.filePath(source_index)
            self.folder_selected.emit(path)
        else:
            path = source_index.data(Qt.UserRole)
            is_scene = source_index.data(Qt.UserRole + 1)
            if not is_scene and isinstance(path, str):
                self.folder_selected.emit(path)

    def _on_search_change(self, _=None):
        text = self.search_bar.text() if self.chk_search.isChecked() else ""
        self.search_changed.emit(text)
        self._update_proxy_filters()

    def _on_age_change(self, _=None):
        val = self.spin_age.value()
        units = self.combo_units.currentText()
        enabled = self.chk_age.isChecked()
        self.age_changed.emit(val, units, enabled)
        self._update_proxy_filters()

    def _update_proxy_filters(self):
        search_text = self.search_bar.text() if self.chk_search.isChecked() else ""
        
        # Calculate age limit in minutes
        val = self.spin_age.value()
        units = self.combo_units.currentText()
        enabled = self.chk_age.isChecked()
        
        minutes = (val + 1)
        if units == "hours": minutes *= 60
        elif units == "days": minutes *= 1440
        
        self.proxy.set_filters(search_text, minutes, enabled)

    def _on_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes: return
        
        # Check if the selection consists of scene items (notes/backdrops)
        scene_ids = []
        for idx in indexes:
            if idx.column() == 0:
                source_idx = self.proxy.mapToSource(idx)
                is_scene = source_idx.data(Qt.UserRole + 1)
                if is_scene:
                    scene_id = source_idx.data(Qt.UserRole)
                    if scene_id:
                        scene_ids.append(scene_id)
                        
        if scene_ids:
            menu = QMenu(self.window())
            
            act_edit = QAction("Edit", self)
            act_edit.setEnabled(len(scene_ids) == 1)
            act_edit.triggered.connect(lambda: self.edit_scene_item_requested.emit(scene_ids[0]))
            menu.addAction(act_edit)
            
            act_delete = QAction("Delete", self)
            act_delete.triggered.connect(lambda: self.delete_scene_items_requested.emit(scene_ids))
            menu.addAction(act_delete)
            
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
            
        # Get unique paths
        paths = []
        for idx in indexes:
            if idx.column() == 0:
                source_idx = self.proxy.mapToSource(idx)
                model = self.proxy.sourceModel()
                if hasattr(model, "filePath"):
                    path = model.filePath(source_idx)
                else:
                    is_scene = source_idx.data(Qt.UserRole + 1)
                    path = source_idx.data(Qt.UserRole) if not is_scene else None
                if path and isinstance(path, str):
                    paths.append(path)
        
        if not paths: return
        
        menu = QMenu(self.window())
        
        act_reveal = QAction("Reveal in Filesystem", self)
        act_reveal.triggered.connect(lambda: self._on_action_reveal(paths))
        menu.addAction(act_reveal)
        
        act_open = QAction("OS Open", self)
        act_open.triggered.connect(lambda: self._on_action_open(paths))
        menu.addAction(act_open)
        
        menu.addSeparator()
        
        act_rename = QAction("Rename to Label", self)
        act_rename.triggered.connect(lambda: self.rename_to_label_requested.emit(paths))
        menu.addAction(act_rename)
        
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_action_reveal(self, paths):
        import subprocess
        for path in paths:
            path = os.path.normpath(path)
            if os.path.exists(path):
                # On Windows, explorer /select,path opens folder and selects file
                subprocess.run(['explorer', '/select,', path])
                # Usually we only reveal the first one if multiple selected, but let's allow it?
                # Actually, explorer /select only supports one file.
                break 

    def _on_action_open(self, paths):
        for path in paths:
            if os.path.exists(path):
                os.startfile(path)
