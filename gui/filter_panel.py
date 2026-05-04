import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, 
                             QHBoxLayout, QLabel, QSpinBox, QTreeView, QFileSystemModel, QButtonGroup, QComboBox)
from PySide6.QtCore import Signal, Qt, QDir, QSortFilterProxyModel, QItemSelectionModel
from PySide6.QtGui import QColor

class TagColorProxyModel(QSortFilterProxyModel):
    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.main_model = main_model
        # Fast lookup set: normalized_abs_path for UNTAGGED items
        self._untagged_paths = set()
        self._rebuild_cache()
        self.main_model.dataChanged.connect(self._on_model_data_changed)
        self.main_model.modelReset.connect(self._rebuild_cache)

    def _rebuild_cache(self):
        self._untagged_paths = set()
        for item in self.main_model.items:
            if not item.is_tagged:
                abs_path = os.path.normpath(os.path.abspath(item.file_path))
                self._untagged_paths.add(abs_path)
        self.invalidateFilter()

    def _on_model_data_changed(self, tl, br):
        self._rebuild_cache()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        idx = source_model.index(source_row, 0, source_parent)
        file_name = source_model.fileName(idx)
        
        # Completely hide generated thumbnails
        if file_name.lower().endswith("_thumbnail.png"):
            return False
            
        return super().filterAcceptsRow(source_row, source_parent)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.ForegroundRole:
            source_index = self.mapToSource(index)
            file_path = self.sourceModel().filePath(source_index)
            abs_path = os.path.normpath(os.path.abspath(file_path))
            
            if abs_path in self._untagged_paths:
                return QColor("#ff4444")
        
        return super().data(index, role)

class FilterPanel(QWidget):
    search_changed = Signal(str)
    age_changed = Signal(int, str) # value, units
    folder_selected = Signal(str)

    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.main_model = main_model
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Mode Buttons
        btn_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        
        self.btn_select = QPushButton("Select")
        self.btn_select.setCheckable(True)
        self.btn_select.setChecked(True)
        
        self.btn_show = QPushButton("Show")
        self.btn_show.setCheckable(True)
        
        self.mode_group.addButton(self.btn_select)
        self.mode_group.addButton(self.btn_show)
        
        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_show)
        self.layout.addLayout(btn_layout)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search images (*)...")
        self.search_bar.setMaxLength(20)
        self.search_bar.textChanged.connect(self.search_changed.emit)
        self.layout.addWidget(self.search_bar)

        # Age Filter
        age_layout = QHBoxLayout()
        age_layout.addWidget(QLabel("Age:"))
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
        self.tree.clicked.connect(self._on_folder_click)
        self.layout.addWidget(self.tree)

    def set_root_folder(self, path):
        self.fs_model.setRootPath(path)
        # Set root index to parent of path to show the root folder itself
        parent_path = os.path.dirname(path)
        source_idx = self.fs_model.index(parent_path)
        proxy_idx = self.proxy.mapFromSource(source_idx)
        self.tree.setRootIndex(proxy_idx)
        
        # Expand to showing the root path
        self.tree.expand(proxy_idx)
        path_idx = self.fs_model.index(path)
        self.tree.expand(self.proxy.mapFromSource(path_idx))

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
            source_idx = self.fs_model.index(p)
            if source_idx.isValid():
                proxy_idx = self.proxy.mapFromSource(source_idx)
                tree_selection.select(proxy_idx, proxy_idx)
                if first_idx is None: first_idx = proxy_idx
        
        selection.select(tree_selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        
        if first_idx:
            self.tree.scrollTo(first_idx)

    def _on_folder_click(self, index):
        source_index = self.proxy.mapToSource(index)
        path = self.fs_model.filePath(source_index)
        self.folder_selected.emit(path)

    def _on_age_change(self, _=None):
        val = self.spin_age.value()
        units = self.combo_units.currentText()
        self.age_changed.emit(val, units)
