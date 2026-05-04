from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableView, QCheckBox, QPushButton, QHeaderView, QStyledItemDelegate, QMenu, QLabel, QSpinBox, QSlider
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, Qt, QSize, QEvent, QModelIndex

class ScalingDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        pixmap = index.data(Qt.DecorationRole)
        if pixmap:
            # Scale to row height minus some padding
            size = option.rect.size()
            scaled_pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Center in rect
            x = option.rect.x() + (option.rect.width() - scaled_pixmap.width()) // 2
            y = option.rect.y() + (option.rect.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            super().paint(painter, option, index)

class SpreadsheetPanel(QWidget):
    check_duplicates_clicked = Signal()
    version_check_clicked = Signal()
    maximize_toggle_requested = Signal()
    label_action_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Controls
        controls_layout = QHBoxLayout()
        self.btn_selected_only = QPushButton("Selected only")
        self.btn_selected_only.setCheckable(True)
        self.btn_selected_only.toggled.connect(self.update_filtering)
        
        self.btn_tagged_only = QPushButton("Tagged only")
        self.btn_tagged_only.setCheckable(True)
        self.btn_tagged_only.toggled.connect(self.update_filtering)
        self.btn_check_ver = QPushButton("Version check")
        self.btn_check_dup = QPushButton("Check duplicates")
        self.btn_tag_sel = QPushButton("Tag/Untag Selected")
        
        self.lbl_row_height = QLabel("Row Height:")
        self.slider_row_height = QSlider(Qt.Horizontal)
        self.slider_row_height.setRange(0, 100)
        self.slider_row_height.setValue(20) # Corresponds to ~40px with quadratic mapping
        self.slider_row_height.setFixedWidth(150)
        self.slider_row_height.valueChanged.connect(self._on_row_height_change)

        controls_layout.addWidget(self.btn_selected_only)
        controls_layout.addWidget(self.btn_tagged_only)
        controls_layout.addWidget(self.btn_check_ver)
        controls_layout.addWidget(self.btn_check_dup)
        controls_layout.addWidget(self.btn_tag_sel)
        controls_layout.addStretch()
        controls_layout.addWidget(self.lbl_row_height)
        controls_layout.addWidget(self.slider_row_height)
        self.layout.addLayout(controls_layout)

        # Table View
        self.table = QTableView()
        from PySide6.QtWidgets import QAbstractItemView
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.verticalHeader().setStyleSheet("font-size: 9px; color: #888888;")
        self.table.verticalHeader().setFixedWidth(25)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table)
        
        # Header Context Menu
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)
        
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

    def set_model(self, model):
        self.table.setModel(model)
        self.table.selectionModel().selectionChanged.connect(self.update_filtering)
        # Set row height for thumbnails
        self.table.verticalHeader().setDefaultSectionSize(40)
        # Set delegate for thumbnail column (index 1)
        self.table.setItemDelegateForColumn(1, ScalingDelegate(self.table))
        # Set columns to Interactive to allow user adjustment
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Fixed) # Tag
        header.setSectionResizeMode(2, QHeaderView.Interactive) # Label
        header.setSectionResizeMode(3, QHeaderView.Interactive) # Category
        header.setSectionResizeMode(4, QHeaderView.Interactive) # Version
        
        # Initial fit
        self.table.setColumnWidth(0, 40)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)
        self.table.resizeColumnToContents(4)
        
        # Connect model data change to auto-resize Label column
        self.table.model().dataChanged.connect(self._on_model_data_changed)
        
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)

    def _on_model_data_changed(self, top_left, bottom_right):
        # If Label column (2) was changed, auto-resize it
        if top_left.column() <= 2 <= bottom_right.column():
            self.table.resizeColumnToContents(2)

    def _on_row_height_change(self, value):
        # Non-linear mapping (quadratic)
        # min 20, max 400
        v = value / 100.0
        h = int(20 + (v * v) * (400 - 20))
        self.table.verticalHeader().setDefaultSectionSize(h)
        # Also adjust thumbnail column width (index 1)
        # Use a slightly wider factor if images are wide, but 1.5x height is safe
        self.table.setColumnWidth(1, int(h * 1.5))

    def update_filtering(self):
        """Update row visibility based on active filters."""
        selected_only = self.btn_selected_only.isChecked()
        tagged_only = self.btn_tagged_only.isChecked()
        
        if not selected_only and not tagged_only:
            for row in range(self.table.model().rowCount()):
                self.table.setRowHidden(row, False)
            return

        selection_model = self.table.selectionModel()
        for row in range(self.table.model().rowCount()):
            is_selected = selection_model.isRowSelected(row, QModelIndex())
            is_tagged = self.table.model().items[row].is_tagged
            
            hidden = False
            if selected_only and not is_selected:
                hidden = True
            if tagged_only and not is_tagged:
                hidden = True
                
            self.table.setRowHidden(row, hidden)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Enter:
            self.table.setFocus()
            
        if event.type() == QEvent.KeyPress:
            # Handle Ctrl+V Paste
            if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
                from PySide6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                text = clipboard.text()
                if text:
                    self._perform_paste(text)
                return True
                
            if event.key() == Qt.Key_Space:
                if self.table.underMouse():
                    self.maximize_toggle_requested.emit()
                    return True
        return super().eventFilter(source, event)

    def _perform_paste(self, text):
        selection_model = self.table.selectionModel()
        if not selection_model.hasSelection():
            return
            
        # Get selected indexes
        indexes = selection_model.selectedIndexes()
        model = self.table.model()
        
        # Track if any data actually changed to log it
        changed_count = 0
        for idx in indexes:
            # Only paste if column is editable
            if model.flags(idx) & Qt.ItemIsEditable:
                if model.setData(idx, text, Qt.EditRole):
                    changed_count += 1
        
        if changed_count > 0:
            # We could emit a signal for logging if needed, but the model handles dataChanged
            pass

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        
        tag_action = QAction("Tag/Untag Selected", self)
        tag_action.triggered.connect(lambda: self.label_action_requested.emit("tag", None))
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
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_header_context_menu(self, pos):
        menu = QMenu(self)
        model = self.table.model()
        if not model: return
        
        # Add "Show All" action
        show_all = QAction("Show All Columns", self)
        show_all.triggered.connect(self._show_all_columns)
        menu.addAction(show_all)
        menu.addSeparator()
        
        for col in range(model.columnCount()):
            header_text = model.headerData(col, Qt.Horizontal)
            if not header_text: continue
            
            action = QAction(header_text, self)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(col))
            action.toggled.connect(lambda checked, c=col: self.table.setColumnHidden(c, not checked))
            menu.addAction(action)
            
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _show_all_columns(self):
        model = self.table.model()
        if not model: return
        for col in range(model.columnCount()):
            self.table.setColumnHidden(col, False)
