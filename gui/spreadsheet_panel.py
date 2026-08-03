from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QCheckBox, 
                             QPushButton, QHeaderView, QStyledItemDelegate, QMenu, QLabel, 
                             QSpinBox, QSlider, QAbstractItemView, QLineEdit)
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, Qt, QSize, QEvent, QModelIndex, QItemSelection, QItemSelectionModel

class ScalingDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        pixmap = index.data(Qt.DecorationRole)
        if pixmap:
            # Scale to row height minus some padding
            margin = 2
            rect = option.rect.adjusted(margin, margin, -margin, -margin)
            size = rect.size()
            scaled_pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Center in rect
            x = rect.x() + (rect.width() - scaled_pixmap.width()) // 2
            y = rect.y() + (rect.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        pixmap = index.data(Qt.DecorationRole)
        if pixmap:
            # We want the width to be proportional to the current row height
            from PySide6.QtWidgets import QTableView
            h = 40 # Default
            if isinstance(option.widget, QTableView):
                h = option.widget.rowHeight(index.row())
            
            if h > 0 and pixmap.height() > 0:
                aspect = pixmap.width() / pixmap.height()
                return QSize(int(h * aspect) + 4, h) # +4 for margin padding
            return pixmap.size()
        return super().sizeHint(option, index)

class SpreadsheetPanel(QWidget):
    check_duplicates_clicked = Signal()
    version_check_clicked = Signal()
    version_collision_check_clicked = Signal()
    maximize_toggle_requested = Signal()
    label_action_requested = Signal(str, object)
    csv_mode_changed = Signal(bool)
    selectionChanged = Signal()
    add_comment_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Controls
        self.controls = QWidget()
        self.controls.setObjectName("SpreadsheetControls")
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(5, 5, 5, 5)
        self.btn_selected_only = QPushButton("Selected only")
        self.btn_selected_only.setCheckable(True)
        self.btn_selected_only.toggled.connect(lambda: self.update_filtering())
        
        self.btn_tagged_only = QPushButton("Enabled Only")
        self.btn_tagged_only.setCheckable(True)
        self.btn_tagged_only.toggled.connect(lambda: self.update_filtering())
        
        self.btn_assigned_only = QPushButton("Assigned Only")
        self.btn_assigned_only.setCheckable(True)
        self.btn_assigned_only.toggled.connect(lambda: self.update_filtering())
        
        self.btn_check_ver_only = QPushButton("Version Check")
        self.btn_check_ver = QPushButton("Version Check Fix")
        self.btn_check_dup = QPushButton("Check Duplicities")
        self.btn_tag_sel = QPushButton("Enable/Disable Selected")
        
        self.btn_csv = QPushButton("CSV")
        self.btn_csv.setCheckable(True)
        self.btn_csv.toggled.connect(self._on_csv_toggled)
        
        self.btn_check_ver_only.clicked.connect(self.version_check_clicked.emit)
        self.btn_check_ver.clicked.connect(self.version_collision_check_clicked.emit)
        self.btn_check_dup.clicked.connect(self.check_duplicates_clicked.emit)
        
        self.lbl_row_height = QLabel("Row Height:")
        self.slider_row_height = QSlider(Qt.Horizontal)
        self.slider_row_height.setRange(0, 100)
        self.slider_row_height.setValue(20) # Corresponds to ~40px with quadratic mapping
        self.slider_row_height.setFixedWidth(150)
        self.slider_row_height.valueChanged.connect(self._on_row_height_change)
        
        self.comment_field = QLineEdit()
        self.comment_field.setPlaceholderText("Comment...")
        self.comment_field.setFixedWidth(150)
        self.btn_add_comment = QPushButton("Add Comment")
        self.btn_add_comment.clicked.connect(lambda: self.add_comment_requested.emit(self.comment_field.text()))

        controls_layout.addWidget(self.btn_selected_only)
        controls_layout.addWidget(self.btn_tagged_only)
        controls_layout.addWidget(self.btn_assigned_only)
        controls_layout.addWidget(self.btn_check_ver_only)
        controls_layout.addWidget(self.btn_check_ver)
        controls_layout.addWidget(self.btn_check_dup)
        controls_layout.addWidget(self.btn_tag_sel)
        controls_layout.addWidget(self.btn_csv)
        controls_layout.addWidget(self.lbl_row_height)
        controls_layout.addWidget(self.slider_row_height)
        controls_layout.addWidget(self.comment_field)
        controls_layout.addWidget(self.btn_add_comment)
        controls_layout.addStretch()

        self.layout.addWidget(self.controls)

        # Table View
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        # Install event filter to grab focus on hover and handle key press
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        
        # Header context menu for column visibility
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)

        self.layout.addWidget(self.table)

        self.standard_model = None
        self.csv_model = None
        self._is_csv_mode = False
        
        # Filters state
        self._last_age_filter = (False, 0)
        self._last_search_text = ""

    def setModel(self, standard_model, csv_model):
        self.standard_model = standard_model
        self.csv_model = csv_model
        if self._is_csv_mode:
            self._setup_csv_view()
        else:
            self._setup_standard_view()

    def set_model(self, model):
        self.standard_model = model
        if not self._is_csv_mode:
            self._setup_standard_view()

    def set_csv_model(self, model):
        self.csv_model = model
        if self._is_csv_mode:
            self._setup_csv_view()

    def _setup_standard_view(self):
        if not self.standard_model: return
        self.table.setModel(self.standard_model)
        # Selection model might have changed
        self.table.selectionModel().selectionChanged.connect(lambda s, d: self.update_filtering())
        self.table.selectionModel().selectionChanged.connect(lambda s, d: self.selectionChanged.emit())
        # Set row height for thumbnails
        self.table.verticalHeader().setDefaultSectionSize(40)
        
        # Clear delegate from CSV mode (index 0)
        self.table.setItemDelegateForColumn(0, QStyledItemDelegate(self.table))
        # Set delegate for thumbnail column (index 1)
        self.table.setItemDelegateForColumn(1, ScalingDelegate(self.table))
        
        # Set columns to Interactive to allow user adjustment
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Fixed) # Enable
        header.setSectionResizeMode(2, QHeaderView.Interactive) # Label
        header.setSectionResizeMode(3, QHeaderView.Interactive) # Variant
        header.setSectionResizeMode(4, QHeaderView.Interactive) # Variant User
        header.setSectionResizeMode(5, QHeaderView.Interactive) # Product Name
        header.setSectionResizeMode(6, QHeaderView.Interactive) # Category
        header.setSectionResizeMode(7, QHeaderView.Interactive) # Preset
        header.setSectionResizeMode(8, QHeaderView.Interactive) # Version
        header.setSectionResizeMode(9, QHeaderView.Interactive) # Version User
        
        # Initial fit
        self.table.setColumnWidth(0, 40)
        self.table.resizeColumnToContents(1) # Thumbnail
        self.table.resizeColumnToContents(2) # Label
        self.table.resizeColumnToContents(3) # Variant
        self.table.resizeColumnToContents(4) # Variant User
        self.table.resizeColumnToContents(5) # Product Name
        self.table.resizeColumnToContents(6) # Category
        self.table.resizeColumnToContents(7) # Preset
        self.table.resizeColumnToContents(8) # Version
        self.table.resizeColumnToContents(9) # Version User
        
        # Connect model data change to auto-resize columns
        self.table.model().dataChanged.connect(self._on_model_data_changed)

    def _setup_csv_view(self):
        if not self.csv_model: return
        self.table.setModel(self.csv_model)
        self.table.verticalHeader().setDefaultSectionSize(40)
        # Set delegate for thumbnail column (index 1 in CSV mode)
        self.table.setItemDelegateForColumn(1, ScalingDelegate(self.table))
        # Clear delegate for index 0
        self.table.setItemDelegateForColumn(0, QStyledItemDelegate(self.table))
        
        self.table.selectionModel().selectionChanged.connect(lambda s, d: self.selectionChanged.emit())
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # Initial fit
        self.table.resizeColumnToContents(1)
        # Auto resize all CSV columns
        for col in range(1, self.csv_model.columnCount()):
            self.table.resizeColumnToContents(col)

    def _on_csv_toggled(self, checked):
        self._is_csv_mode = checked
        if checked:
            self._setup_csv_view()
        else:
            self._setup_standard_view()
        
        # Hide/Show other controls
        self.btn_check_ver_only.setEnabled(True)
        self.btn_check_ver.setEnabled(True)
        self.btn_check_dup.setEnabled(True)
        self.btn_tag_sel.setEnabled(not checked)
        self.btn_selected_only.setEnabled(not checked)
        self.btn_tagged_only.setEnabled(not checked)
        self.btn_assigned_only.setEnabled(not checked)
        
        # Ensure row hidden states are refreshed
        self.update_filtering()
        
        self.csv_mode_changed.emit(checked)

    def _on_model_data_changed(self, top_left, bottom_right):
        # Skip auto-resizing during bulk updates (e.g. metadata scanner updates) to prevent GUI lag
        if bottom_right.column() - top_left.column() > 5:
            return
            
        # If Label, Variant/User Variant or Version/User Version column was changed, auto-resize them
        if top_left.column() <= 9 <= bottom_right.column() or top_left.column() <= 4 <= bottom_right.column():
            self.table.resizeColumnToContents(2)
            self.table.resizeColumnToContents(3) # Variant
            self.table.resizeColumnToContents(4) # Variant User
            self.table.resizeColumnToContents(5) # Product Name
            self.table.resizeColumnToContents(8) # Version
            self.table.resizeColumnToContents(9) # Version User

    def _on_row_height_change(self, value):
        # Non-linear mapping (quadratic)
        # min 20, max 400
        v = value / 100.0
        h = int(20 + (v * v) * (400 - 20))
        self.table.verticalHeader().setDefaultSectionSize(h)
        # Also adjust thumbnail column width (index 1)
        self.table.resizeColumnToContents(1)

    def update_filtering(self, age_filter=None, search_text=None):
        """Update row visibility based on active filters."""
        if age_filter is not None:
            self._last_age_filter = age_filter
        if search_text is not None:
            self._last_search_text = search_text
            
        if self._is_csv_mode: 
            for row in range(self.table.model().rowCount()):
                self.table.setRowHidden(row, False)
            return
        selected_only = self.btn_selected_only.isChecked()
        tagged_only = self.btn_tagged_only.isChecked()
        assigned_only = self.btn_assigned_only.isChecked()
        
        age_enabled, age_val = self._last_age_filter
        search_term = self._last_search_text
        
        v_stack_enabled = getattr(self.table.model(), "v_stack_enabled", False)
        
        if not selected_only and not tagged_only and not assigned_only and not age_enabled and not search_term and not v_stack_enabled:
            for row in range(self.table.model().rowCount()):
                self.table.setRowHidden(row, False)
            return

        selection_model = self.table.selectionModel()
        for row in range(self.table.model().rowCount()):
            item = self.table.model().items[row]
            is_selected = selection_model.isRowSelected(row, QModelIndex())
            is_tagged = item.is_tagged
            is_assigned = bool(item.ayon_path)
            is_young_enough = not age_enabled or (item.age_minutes <= age_val)
            matches_search = (not search_term or 
                              search_term in item.label.lower() or 
                              search_term in item.filename.lower())
            
            hidden = False
            if selected_only and not is_selected:
                hidden = True
            if tagged_only and not is_tagged:
                hidden = True
            if assigned_only and not is_assigned:
                hidden = True
            if age_enabled and not is_young_enough:
                hidden = True
            if search_term and not matches_search:
                hidden = True
            
            if v_stack_enabled and not self.table.model().is_item_visible_by_v_stack(item, True):
                hidden = True
                
            self.table.setRowHidden(row, hidden)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Enter:
            if source in (self.table, self.table.viewport()):
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
                # If editing, let the space go to the editor
                if self.table.state() != QAbstractItemView.NoState:
                    return False
                    
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
        menu = QMenu(self.window())
        
        # Check Version Stack Select
        model = self.table.model()
        if model and not self.btn_csv.isChecked():
            v_stack_enabled = getattr(model, "v_stack_enabled", False)
            selected_rows = self.table.selectionModel().selectedRows()
            if not v_stack_enabled and len(selected_rows) == 1:
                row = selected_rows[0].row()
                if row < len(model.items):
                    item = model.items[row]
                    key = model.get_version_stack_key(item)
                    stack = model.version_stacks.get(key)
                    if stack and len(stack["items"]) > 1:
                        select_action = QAction("Version Stack Select", self)
                        select_action.triggered.connect(lambda checked=False, it_obj=item: self._select_all_items_in_stack(it_obj))
                        menu.addAction(select_action)
                        menu.addSeparator()
        
        tag_action = QAction("Enable/Disable Selected", self)
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
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _select_all_items_in_stack(self, item):
        model = self.table.model()
        if not model: return
        key = model.get_version_stack_key(item)
        stack = model.version_stacks.get(key)
        if not stack: return
        
        selection_model = self.table.selectionModel()
        selection = QItemSelection()
        for r in range(model.rowCount()):
            row_item = model.items[r]
            if row_item in stack["items"]:
                index_first = model.index(r, 0)
                index_last = model.index(r, model.columnCount() - 1)
                selection.select(index_first, index_last)
                
        selection_model.select(selection, QItemSelectionModel.ClearAndSelect)

    def _on_header_context_menu(self, pos):
        menu = QMenu(self.window())
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
