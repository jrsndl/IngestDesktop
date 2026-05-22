from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableView, QHeaderView, QLabel, QFrame)
from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, Signal
from PySide6.QtGui import QColor

class QueueProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_map = [1, 10, 2, 11] # Thumbnail, Review (Status), Label, AYON Path (File)
        # Wait, the user said "File". item.file_path is not in the columns list.
        # I should probably add "File Path" to the COLUMNS if I want to show it easily,
        # or handle it in the proxy.
        # Actually, let's map to existing columns and handle the "File" separately.
        # Let's check logic/image_model.py columns again.
        # COLUMNS = ["Tag", "Thumbnail", "Label", "Variant", "Product Name", "Category", "Preset", "Version", "Last Version", "Age", "Review", "AYON Path", "Key Value Pairs"]
        # Index 1 is Thumbnail, 10 is Review, 2 is Label, 11 is AYON Path.
        # The user said "File". Maybe they mean the actual file path.
        # I'll just use AYON Path or Label for now, or add File Path to the model.
        
    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        index = source_model.index(source_row, 10, source_parent) # Review column
        status = source_model.data(index, Qt.DisplayRole)
        return status != "do not convert"

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

    def __init__(self, main_model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Conversion Queue")
        self.resize(800, 500)
        
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

        self.btn_convert_thumbs = QPushButton("Convert Thumbnails")
        self.btn_convert_thumbs.setMinimumHeight(40)
        self.btn_convert_thumbs.clicked.connect(self.convertThumbsRequested.emit)
        
        self.btn_check_existing = QPushButton("Check existing")
        self.btn_check_existing.setMinimumHeight(40)
        self.btn_check_existing.clicked.connect(self.check_existing_reviews)
        
        self.controls.addWidget(self.btn_convert_reviews)
        self.controls.addSpacing(10)
        self.controls.addWidget(self.btn_convert_thumbs)
        self.controls.addSpacing(10)
        self.controls.addWidget(self.btn_check_existing)
        self.controls.addStretch()
        self.controls.addWidget(self.btn_pause)
        self.controls.addWidget(self.btn_restart)
        self.controls.addWidget(self.btn_cancel)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.layout.addLayout(self.controls)
        
        # Status Label
        self.lbl_status = QLabel("Status: Waiting")
        self.layout.addWidget(self.lbl_status)
 
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
