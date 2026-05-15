import os
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, 
                             QHBoxLayout, QLabel, QSpinBox, QTreeView, QFileSystemModel, 
                             QButtonGroup, QComboBox, QAbstractItemView, QCheckBox)
from PySide6.QtCore import Signal, Qt, QDir, QSortFilterProxyModel, QItemSelectionModel
from PySide6.QtGui import QColor
from utils import strip_sequence_counter, get_version_from_name

class TagColorProxyModel(QSortFilterProxyModel):
    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.main_model = main_model
        
        # Current filter state for coloring
        self._search_text = ""
        self._age_limit = 0
        self._age_enabled = False
        
        # Sequence settings
        self.detect_sequences = False
        self.version_regex = r"([._]v|v)(\d+)"
        
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

    def _rebuild_cache(self):
        self._path_info = {}
        self._sequence_map = {}
        
        for item in self.main_model.items:
            abs_path = os.path.normpath(os.path.abspath(item.file_path))
            self._path_info[abs_path] = (item.is_tagged, item.age_minutes, item.label)
            
            if self.detect_sequences and item.is_sequence:
                directory = os.path.dirname(abs_path)
                filename = os.path.basename(abs_path)
                
                # Logic from ImageScanner to get the same key
                version = get_version_from_name(filename, self.version_regex)
                name_no_ver = re.sub(self.version_regex, "", filename)
                base_name = strip_sequence_counter(name_no_ver)
                ext = os.path.splitext(filename)[1].lower()
                
                key = (directory, base_name, ext, version)
                self._sequence_map[key] = item
                
        self.invalidateFilter()

    def _on_model_data_changed(self, tl, br):
        self._rebuild_cache()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        file_name = source_model.fileName(idx)
        
        if file_name.lower().endswith("_thumbnail.png"):
            return False
            
        if self.detect_sequences and not source_model.isDir(idx):
            file_path = source_model.filePath(idx)
            abs_path = os.path.normpath(os.path.abspath(file_path))
            directory = os.path.dirname(abs_path)
            filename = os.path.basename(abs_path)
            
            # Check if this file is part of a known sequence
            version = get_version_from_name(filename, self.version_regex)
            name_no_ver = re.sub(self.version_regex, "", filename)
            base_name = strip_sequence_counter(name_no_ver)
            ext = os.path.splitext(filename)[1].lower()
            
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
            if not self.sourceModel().isDir(source_index):
                file_path = self.sourceModel().filePath(source_index)
                abs_path = os.path.normpath(os.path.abspath(file_path))
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

        if role == Qt.ForegroundRole:
            source_index = self.mapToSource(index)
            file_path = self.sourceModel().filePath(source_index)
            abs_path = os.path.normpath(os.path.abspath(file_path))
            
            if abs_path in self._path_info:
                is_tagged, age_min, label = self._path_info[abs_path]
                
                # Check filter match
                matches_search = not self._search_text or self._search_text in label.lower()
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
        self.layout.addWidget(self.tree)

    def set_sequence_detection(self, enabled, regex):
        """Update sequence detection settings and rebuild cache."""
        self.proxy.detect_sequences = enabled
        self.proxy.version_regex = regex
        self.proxy._rebuild_cache()

    def set_root_folder(self, path):
        self.fs_model.setRootPath(path)
        source_idx = self.fs_model.index(path)
        proxy_idx = self.proxy.mapFromSource(source_idx)
        self.tree.setRootIndex(proxy_idx)
        
        # Expand the root folder contents
        self.tree.expand(proxy_idx)

    def select_paths(self, paths):
        """Programmatically select multiple files in the tree."""
        if not paths: return
        
        selection = self.tree.selectionModel()
        selection.clear()
        
        # Use QItemSelection for multiple items efficiently
        from PySide6.QtCore import QItemSelection
        tree_selection = QItemSelection()
        
        first_idx = None
        for p in paths:
            norm_p = os.path.normpath(os.path.abspath(p))
            source_idx = self.fs_model.index(norm_p)
            if source_idx.isValid():
                proxy_idx = self.proxy.mapFromSource(source_idx)
                tree_selection.select(proxy_idx, proxy_idx)
                if first_idx is None: first_idx = proxy_idx
                
                # Ensure parent is expanded so item is "loaded" in view
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
        path = self.fs_model.filePath(source_index)
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
