from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeView, 
                             QHBoxLayout, QLabel, QMenu, QLineEdit, QComboBox)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont, QAction
from PySide6.QtCore import Signal, Qt, QSortFilterProxyModel

class AyonFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._assigned_only = False
        self._assigned_paths = set()

    def setAssignedOnly(self, enabled):
        self._assigned_only = enabled
        self.invalidateFilter()

    def setAssignedPaths(self, paths):
        self._assigned_paths = set(paths)
        if self._assigned_only:
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        # 1. Base search filter
        search_ok = super().filterAcceptsRow(source_row, source_parent)
        
        # 2. Assigned only filter
        if not self._assigned_only:
            return search_ok

        # Check if this row is assigned
        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        item = model.itemFromIndex(idx)
        data = item.data(Qt.UserRole)
        
        if data and "full_ayon_path" in data:
            if data["full_ayon_path"] in self._assigned_paths:
                return search_ok # If assigned and search matches, show it
        
        # If it's a folder, show it only if it contains assigned tasks that match search
        for r in range(model.rowCount(idx)):
            if self.filterAcceptsRow(r, idx):
                return True # Parent must be shown if child is shown
                
        return False

class AyonPanel(QWidget):
    # Signal emitted when a task is double-clicked: (folder_path, task_name, task_type)
    task_selected = Signal(str, str, str) 
    # Context menu signals
    unassign_requested = Signal(str) # full_ayon_path
    select_assigned_requested = Signal(str) # full_ayon_path
    clear_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_mode = QPushButton("Assign Mode")
        self.btn_mode.setCheckable(True)
        self.btn_mode.setChecked(True) # Assign mode is default
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_mode)
        self.layout.addLayout(btn_layout)

        # Search Controls
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        
        self.search_combo = QComboBox()
        self.search_combo.addItems(["Name", "Type", "Status", "Assignee"])
        self.search_combo.currentIndexChanged.connect(self._on_search_changed)
        
        search_layout.addWidget(self.search_edit, 2)
        search_layout.addWidget(self.search_combo, 1)
        self.layout.addLayout(search_layout)

        # Assigned/Clear Controls
        extra_btn_layout = QHBoxLayout()
        self.btn_assigned_only = QPushButton("Assigned Only")
        self.btn_assigned_only.setCheckable(True)
        self.btn_assigned_only.toggled.connect(self._on_assigned_only_toggled)
        
        self.btn_clear_all = QPushButton("Clear All Assignments")
        self.btn_clear_all.clicked.connect(self.clear_all_requested.emit)
        
        extra_btn_layout.addWidget(self.btn_assigned_only)
        extra_btn_layout.addWidget(self.btn_clear_all)
        self.layout.addLayout(extra_btn_layout)

        # Tree View
        self.tree = QTreeView()
        self.tree.setHeaderHidden(False)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name", "Type", "Status", "Assignee"])
        
        # Proxy for searching and sorting
        self.proxy = AyonFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        
        self.tree.setModel(self.proxy)
        self.tree.setSortingEnabled(True)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        
        # Header setup for hideable columns
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)
        header.setSectionsClickable(True)
        
        self.layout.addWidget(self.tree)
        
        self.assigned_paths = set()

        # Unreachable Warning Label
        self.lbl_unreachable = QLabel("AYON Unreachable")
        self.lbl_unreachable.setObjectName("AyonWarning")
        self.lbl_unreachable.setAlignment(Qt.AlignCenter)
        self.lbl_unreachable.setWordWrap(True)
        self.lbl_unreachable.hide()
        self.layout.addWidget(self.lbl_unreachable)

    def set_hierarchy(self, root_folders):
        self.model.removeRows(0, self.model.rowCount())
        
        for folder in root_folders:
            self._add_folder_to_tree(folder, self.model.invisibleRootItem())
        
        self.tree.expandToDepth(2)
        self.tree.resizeColumnToContents(0)

    def set_connection_status(self, is_connected, server_url=""):
        if is_connected:
            self.lbl_unreachable.hide()
            self.tree.show()
            self.btn_refresh.setEnabled(True)
        else:
            self.lbl_unreachable.setText(f"AYON is unreachable\n\n({server_url})")
            self.lbl_unreachable.show()
            self.tree.hide()
            self.btn_refresh.setEnabled(True) # Keep enabled so user can retry after fixing config

    def _add_folder_to_tree(self, folder, parent_item):
        name = folder.get('label') or folder.get('name', 'Unknown')
        f_type = folder.get('type', 'Folder')
        status = folder.get('status', '')
        
        name_item = QStandardItem(name)
        name_item.setData(folder, Qt.UserRole)
        name_item.setEditable(False)
        
        type_item = QStandardItem(f_type)
        type_item.setEditable(False)
        
        status_item = QStandardItem(status)
        status_item.setEditable(False)
        
        assignee_item = QStandardItem("") # Folders don't have assignees
        assignee_item.setEditable(False)
        
        parent_item.appendRow([name_item, type_item, status_item, assignee_item])
        
        # Add tasks
        for task in folder.get('tasks', []):
            t_name = task.get('label') or task.get('name', 'Unknown')
            t_type = task.get('type', 'Task')
            t_status = task.get('status', '')
            
            # Add a prefix or icon to distinguish tasks
            t_name_item = QStandardItem(f" {t_name}")
            t_name_item.setData(task, Qt.UserRole)
            # Add a small icon hint for tasks (using a simple circle or bullet)
            t_name_item.setText(f"• {t_name}")
            
            # Store task data and reference to parent folder path
            full_path = f"{folder.get('path')}/{task.get('name')}"
            task_data = {**task, "folder_path": folder.get('path'), "full_ayon_path": full_path}
            t_name_item.setData(task_data, Qt.UserRole)
            t_name_item.setEditable(False)
            
            # Use a bright, visible color for tasks (e.g., lime green or bright yellow)
            t_name_item.setForeground(QColor("#a6e22e")) # Monokai-style lime green
            
            t_type_item = QStandardItem(t_type)
            t_type_item.setEditable(False)
            
            t_status_item = QStandardItem(t_status)
            t_status_item.setEditable(False)
            
            t_assignees = ", ".join(task.get('assignees', []))
            t_assignee_item = QStandardItem(t_assignees)
            t_assignee_item.setEditable(False)
            
            name_item.appendRow([t_name_item, t_type_item, t_status_item, t_assignee_item])
            
        # Add subfolders
        for child in folder.get('children', []):
            self._add_folder_to_tree(child, name_item)

    def _on_double_click(self, index):
        if not self.btn_mode.isChecked(): # Select mode
            return
            
        # Map from proxy to source
        source_index = self.proxy.mapToSource(index)
        
        # Always use the data from the first column's item
        row_index = source_index.row()
        parent = source_index.parent()
        first_col_index = self.model.index(row_index, 0, parent)
        
        item = self.model.itemFromIndex(first_col_index)
        data = item.data(Qt.UserRole)
        
        # Check if it's a task (has folder_path in data)
        if 'folderId' in data and 'folder_path' in data:
            folder_path = data.get('folder_path')
            task_name = data.get('name')
            task_type = data.get('type')
            self.task_selected.emit(folder_path, task_name, task_type)
        else:
            # It's a folder, maybe emit folder path if needed?
            # For now we focus on tasks as ingestion targets
            pass

    def update_assigned_status(self, assigned_paths):
        """Iterate through the tree and bold tasks that are assigned to items."""
        self.assigned_paths = set(assigned_paths)
        self.proxy.setAssignedPaths(self.assigned_paths)
        
        def _recurse_items(parent_item):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item: continue
                
                data = item.data(Qt.UserRole)
                if data and "full_ayon_path" in data:
                    is_assigned = data["full_ayon_path"] in assigned_paths
                    font = item.font()
                    font.setBold(is_assigned)
                    item.setFont(font)
                    
                    # Keep the original lime green for tasks, only change weight
                    item.setForeground(QColor("#a6e22e"))
                
                # Always recurse for subfolders
                _recurse_items(item)
                
        _recurse_items(self.model.invisibleRootItem())

    def _on_header_context_menu(self, pos):
        """Context menu to toggle column visibility."""
        header = self.tree.header()
        menu = QMenu(self)
        
        # We start from index 1 because index 0 (Name) should always be visible
        for i in range(1, self.model.columnCount()):
            label = self.model.horizontalHeaderItem(i).text()
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(not self.tree.isColumnHidden(i))
            action.triggered.connect(lambda checked, col=i: self.tree.setColumnHidden(col, not checked))
            menu.addAction(action)
            
        menu.exec(header.viewport().mapToGlobal(pos))

    def _on_search_changed(self):
        """Update proxy filter based on UI controls."""
        text = self.search_edit.text()
        col = self.search_combo.currentIndex()
        self.proxy.setFilterKeyColumn(col)
        self.proxy.setFilterFixedString(text)
        
        if text or self.btn_assigned_only.isChecked():
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
            self.tree.expandToDepth(1)

    def _on_assigned_only_toggled(self, checked):
        self.proxy.setAssignedOnly(checked)
        self._on_search_changed() # Trigger expansion logic

    def _on_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return

        # Map from proxy to source
        source_index = self.proxy.mapToSource(index)
        
        # Always use the data from the first column's item
        first_col_index = self.model.index(source_index.row(), 0, source_index.parent())
        item = self.model.itemFromIndex(first_col_index)
        data = item.data(Qt.UserRole)
        
        if not data or 'full_ayon_path' not in data:
            return

        menu = QMenu(self)
        ayon_path = data['full_ayon_path']
        is_assigned = ayon_path in self.assigned_paths
        
        if not is_assigned:
            assign_action = QAction(f"Assign path to selection", self)
            assign_action.triggered.connect(lambda: self.task_selected.emit(
                data.get('folder_path'), data.get('name'), data.get('type')
            ))
            menu.addAction(assign_action)
        else:
            unassign_action = QAction(f"Unassign path", self)
            unassign_action.triggered.connect(lambda: self.unassign_requested.emit(ayon_path))
            menu.addAction(unassign_action)
            
            select_action = QAction(f"Select assigned items", self)
            select_action.triggered.connect(lambda: self.select_assigned_requested.emit(ayon_path))
            menu.addAction(select_action)
            
        menu.exec(self.tree.viewport().mapToGlobal(pos))
