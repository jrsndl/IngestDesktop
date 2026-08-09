from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableView, QHeaderView, QLabel, QFrame, QCheckBox)
from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, Signal, QItemSelection, QItemSelectionRange, QItemSelectionModel
from PySide6.QtGui import QColor

class QueueProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_map = [1, 11, 2, 12] # Thumbnail, Review (Status), Label, AYON Path (File)
        self.selected_only = False
        self.selected_items = set()

    def set_selected_only(self, selected_only, selected_items=None):
        self.selected_only = selected_only
        if selected_items is not None:
            self.selected_items = set(selected_items)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        index = source_model.index(source_row, 11, source_parent) # Review column (index 11)
        status = source_model.data(index, Qt.DisplayRole)
        if status == "do not convert":
            return False
        if self.selected_only:
            item = source_model.items[source_row]
            return item in self.selected_items
        return True

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["Thumbnail", "Status", "Label", "File"][section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        source_model = self.sourceModel()
        source_row = self.mapToSource(index).row()
        item = source_model.items[source_row]
        
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if index.column() == 1: return item.review_status
            if index.column() == 2: return item.label
            if index.column() == 3: return item.file_path
            return None
            
        if role == Qt.DecorationRole and index.column() == 0:
            return item.thumbnail

        if role == Qt.BackgroundRole:
            status = str(item.review_status)
            if status == "waiting": return QColor("#444444")
            if status.startswith("processing"): return QColor("#d35400") # Orange
            if status == "done": return QColor("#27ae60") # Green
            if status == "failed": return QColor("#c0392b") # Red
            
        return None

class ConversionQueueDialog(QDialog):
    convertReviewsRequested = Signal()
    convertThumbsRequested = Signal()
    forceConvertReviewsRequested = Signal()
    forceConvertThumbsRequested = Signal()

    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Conversion Queue")
        self.resize(1000, 500)
        self._selected_items = set()
        
        self.layout = QVBoxLayout(self)
        
        # Table
        self.table = QTableView()
        self.proxy = QueueProxyModel()
        self.proxy.setSourceModel(main_model)
        self.table.setModel(self.proxy)
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 60)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(False) # We use custom status colors
        
        self.layout.addWidget(self.table)
        
        # Controls
        self.controls = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_restart = QPushButton("Restart")
        
        self.btn_convert_reviews = QPushButton("Convert Reviews")
        self.btn_convert_reviews.setObjectName("IngestButton") # Green/Primary style
        self.btn_convert_reviews.setMinimumHeight(40)
        self.btn_convert_reviews.clicked.connect(self.convertReviewsRequested.emit)

        self.btn_force_convert_reviews = QPushButton("Force convert Reviews")
        self.btn_force_convert_reviews.setMinimumHeight(40)
        self.btn_force_convert_reviews.clicked.connect(self.forceConvertReviewsRequested.emit)

        self.btn_convert_thumbs = QPushButton("Convert Thumbnails")
        self.btn_convert_thumbs.setMinimumHeight(40)
        self.btn_convert_thumbs.clicked.connect(self.convertThumbsRequested.emit)

        self.btn_force_convert_thumbs = QPushButton("Force convert Thumbnails")
        self.btn_force_convert_thumbs.setMinimumHeight(40)
        self.btn_force_convert_thumbs.clicked.connect(self.forceConvertThumbsRequested.emit)
        
        self.btn_check_existing = QPushButton("Check existing")
        self.btn_check_existing.setMinimumHeight(40)
        self.btn_check_existing.clicked.connect(self.check_existing_reviews)
        
        self.chk_selected_only = QCheckBox("Selected Only")
        self.chk_selected_only.setChecked(False)
        self.chk_selected_only.toggled.connect(self._on_selected_only_toggled)

        self.controls.addWidget(self.btn_convert_reviews)
        self.controls.addWidget(self.btn_force_convert_reviews)
        self.controls.addSpacing(10)
        self.controls.addWidget(self.btn_convert_thumbs)
        self.controls.addWidget(self.btn_force_convert_thumbs)
        self.controls.addSpacing(10)
        self.controls.addWidget(self.btn_check_existing)
        self.controls.addStretch()
        self.controls.addWidget(self.chk_selected_only)
        self.controls.addSpacing(10)
        self.controls.addWidget(self.btn_pause)
        self.controls.addWidget(self.btn_restart)
        self.controls.addWidget(self.btn_cancel)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.layout.addLayout(self.controls)
        
        # Status Label
        self.lbl_status = QLabel("Status: Waiting")
        self.layout.addWidget(self.lbl_status)
 
    def set_selected_items(self, selected_items):
        self._selected_items = set(selected_items) if selected_items else set()
        self.proxy.set_selected_only(self.chk_selected_only.isChecked(), self._selected_items)
        self.update_table_selection()

    def _on_selected_only_toggled(self, checked):
        self.proxy.set_selected_only(checked, self._selected_items)
        self.update_table_selection()

    def update_table_selection(self):
        if not self._selected_items:
            return
        sel_model = self.table.selectionModel()
        if not sel_model:
            return
        sel_model.clearSelection()
        source_model = self.proxy.sourceModel()
        if not source_model:
            return
        
        selection = QItemSelection()
        for proxy_row in range(self.proxy.rowCount()):
            proxy_idx = self.proxy.index(proxy_row, 0)
            source_idx = self.proxy.mapToSource(proxy_idx)
            source_row = source_idx.row()
            if 0 <= source_row < len(source_model.items):
                item = source_model.items[source_row]
                if item in self._selected_items:
                    r_start = self.proxy.index(proxy_row, 0)
                    r_end = self.proxy.index(proxy_row, self.proxy.columnCount() - 1)
                    selection.append(QItemSelectionRange(r_start, r_end))
        sel_model.select(selection, QItemSelectionModel.Select)

    def set_queue_status(self, text):
        self.lbl_status.setText(f"Status: {text}")
        
    def set_pause_text(self, is_paused):
        self.btn_pause.setText("Resume" if is_paused else "Pause")

    def check_existing_reviews(self):
        import os
        source_model = self.proxy.sourceModel()
        if not source_model:
            return
            
        count = 0
        for item in source_model.items:
            if item.review_status != "do not convert":
                review_path = source_model._get_prefs_review_path(item)
                if review_path and os.path.exists(review_path):
                    if item.review_status != "done":
                        item.review_status = "done"
                        count += 1
                        
        if count > 0:
            source_model.layoutChanged.emit()
            
        self.set_queue_status(f"Checked existing. Updated {count} review(s) to 'done'.")
