from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeView, 
                             QHBoxLayout, QLabel, QMenu, QLineEdit, QComboBox, QSplitter,
                             QSizePolicy)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon, QColor, QFont, QAction
from PySide6.QtCore import Signal, Qt, QSortFilterProxyModel, QEvent

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
        # 1. Check Assigned Only Filter
        if self._assigned_only:
            if not self._isAssignedOrHasAssignedDescendant(source_row, source_parent):
                return False

        # 2. Check Search Filter
        regex = self.filterRegularExpression()
        if regex.isValid() and regex.pattern():
            # Show if self matches
            if super().filterAcceptsRow(source_row, source_parent):
                return True
            
            # Show if any ancestor matches (so tasks of a matched folder are shown)
            p = source_parent
            while p.isValid():
                if super().filterAcceptsRow(p.row(), p.parent()):
                    return True
                p = p.parent()
            
            return False

        return True

    def _isAssignedOrHasAssignedDescendant(self, source_row, source_parent):
        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        item = model.itemFromIndex(idx)
        if not item: return False
        
        data = item.data(Qt.UserRole)
        if data and "full_ayon_path" in data:
            if data["full_ayon_path"] in self._assigned_paths:
                return True
        
        # Check children
        for r in range(model.rowCount(idx)):
            if self._isAssignedOrHasAssignedDescendant(r, idx):
                return True
        return False
        
class CheckableComboBox(QComboBox):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().viewport().installEventFilter(self)
        self._changed = False

    def eventFilter(self, object, event):
        if object == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                state = self.model().data(index, Qt.CheckStateRole)
                new_state = Qt.Unchecked if state == Qt.Checked else Qt.Checked
                self.model().setData(index, new_state, Qt.CheckStateRole)
                self._changed = True
                return True
        return super().eventFilter(object, event)

    def hidePopup(self):
        if self._changed:
            self._changed = False
            self.selection_changed.emit()
        super().hidePopup()

    def get_checked_items(self):
        checked = []
        for i in range(self.count()):
            index = self.model().index(i, 0)
            state = self.model().data(index, Qt.CheckStateRole)
            if state in (Qt.Checked, Qt.CheckState.Checked, 2):
                text = self.model().data(index, Qt.DisplayRole)
                if text:
                    checked.append(str(text))
        return checked

class AyonPanel(QWidget):
    # Signal emitted when a task is double-clicked: (folder_path, task_name, task_type, assignee)
    task_selected = Signal(str, str, str, str) 
    # Context menu signals
    unassign_requested = Signal(str) # full_ayon_path
    select_assigned_requested = Signal(str) # full_ayon_path
    clear_all_requested = Signal()
    info_requested = Signal(str) # folder_id
    product_double_clicked = Signal(str, str, str, str) # (folder_path, task_name, task_type, variant)
    auto_assign_requested = Signal()
    project_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Project Selection
        project_layout = QHBoxLayout()
        self.lbl_project = QLabel("Project:")
        self.combo_project = QComboBox()
        self.combo_project.setMinimumWidth(200)
        self.combo_project.currentTextChanged.connect(self.project_changed.emit)
        project_layout.addWidget(self.lbl_project)
        project_layout.addWidget(self.combo_project, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_auto = QPushButton("Auto-Assign")
        self.btn_auto.setObjectName("IngestButton")
        self.btn_auto.clicked.connect(self.auto_assign_requested.emit)
        
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_auto)

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

        # Assigned/Clear Controls
        extra_btn_layout = QHBoxLayout()
        self.btn_assigned_only = QPushButton("Assigned Only")
        self.btn_assigned_only.setCheckable(True)
        self.btn_assigned_only.toggled.connect(self._on_assigned_only_toggled)
        
        self.btn_clear_all = QPushButton("Clear All Assignments")
        self.btn_clear_all.clicked.connect(self.clear_all_requested.emit)
        
        extra_btn_layout.addWidget(self.btn_assigned_only)
        extra_btn_layout.addWidget(self.btn_clear_all)

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
        self.proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # Header setup for hideable columns
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)
        header.setSectionsClickable(True)
        
        # 5. Splitter for Task Tree and Product Info
        self.splitter = QSplitter(Qt.Vertical)
        
        # Container for the top part (Buttons + Search + Tree)
        self.top_container = QWidget()
        top_layout = QVBoxLayout(self.top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(project_layout)
        top_layout.addLayout(btn_layout)
        top_layout.addLayout(search_layout)
        top_layout.addLayout(extra_btn_layout)
        top_layout.addWidget(self.tree)
        
        self.spacer_widget = QWidget()
        spacer_layout = QVBoxLayout(self.spacer_widget)
        spacer_layout.setContentsMargins(0, 0, 0, 0)
        spacer_layout.addStretch(1)
        self.spacer_widget.hide()
        top_layout.addWidget(self.spacer_widget)
        
        self.splitter.addWidget(self.top_container)
        
        # Container for Product Info
        self.product_container = QWidget()
        self.product_layout = QVBoxLayout(self.product_container)
        self.product_layout.setContentsMargins(0, 5, 0, 0)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Task Products:</b>"))
        header_layout.addStretch()
        
        self.btn_hide_products = QPushButton("Hide")
        self.btn_hide_products.setCheckable(True)
        self.btn_hide_products.setFixedWidth(50)
        self.btn_hide_products.setStyleSheet("font-size: 10px; padding: 2px;")
        self.btn_hide_products.toggled.connect(self._on_hide_products_toggled)
        header_layout.addWidget(self.btn_hide_products)
        
        self.product_layout.addLayout(header_layout)
        
        self.combo_product_types = CheckableComboBox()
        self.combo_product_types.setPlaceholderText("Filter types...")
        self.combo_product_types.selection_changed.connect(self._refresh_product_list)
        self.product_layout.addWidget(self.combo_product_types)
        
        self.product_view = QTreeView()
        self.product_model = QStandardItemModel()
        self.product_model.setHorizontalHeaderLabels(["Product Name", "Type", "Last Version"])
        self.product_view.setModel(self.product_model)
        self.product_view.setHeaderHidden(False)
        self.product_view.setEditTriggers(QTreeView.NoEditTriggers)
        self.product_view.doubleClicked.connect(self._on_product_double_click)
        self.product_layout.addWidget(self.product_view)
        
        self.splitter.addWidget(self.product_container)
        self.layout.addWidget(self.splitter)
        
        # Initial splitter sizes
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([700, 300])

        # Unreachable Warning Label
        self.lbl_unreachable = QLabel("AYON Unreachable")
        self.lbl_unreachable.setObjectName("AyonWarning")
        self.lbl_unreachable.setAlignment(Qt.AlignCenter)
        self.lbl_unreachable.setWordWrap(True)
        self.lbl_unreachable.hide()
        self.layout.addWidget(self.lbl_unreachable)
        
        self.all_products = [] # Cache for current selected task

    def get_path_to_id_map(self):
        """Build a map of ayon_path -> folder_id from the current tree."""
        mapping = {}
        def _recurse(parent_item):
            for r in range(parent_item.rowCount()):
                item = parent_item.child(r, 0)
                if not item: continue
                data = item.data(Qt.UserRole)
                if data:
                    # For folders
                    if "path" in data and "id" in data:
                        mapping[data["path"]] = str(data["id"])
                    # For tasks, path is in folder_path
                    elif "folder_path" in data and "folderId" in data:
                        mapping[data["folder_path"]] = str(data["folderId"])
                
                _recurse(item)
        _recurse(self.model.invisibleRootItem())
        return mapping

    def set_projects(self, projects):
        self.combo_project.blockSignals(True)
        self.combo_project.clear()
        self.combo_project.addItems(projects)
        self.combo_project.blockSignals(False)

    def set_current_project(self, project):
        self.combo_project.blockSignals(True)
        self.combo_project.setCurrentText(project)
        self.combo_project.blockSignals(False)

    def set_hierarchy(self, root_folders):
        self.model.removeRows(0, self.model.rowCount())
        
        for folder in root_folders:
            self._add_folder_to_tree(folder, self.model.invisibleRootItem())
        
        self.tree.expandToDepth(2)
        self.tree.resizeColumnToContents(0)
        self.tree.sortByColumn(0, Qt.AscendingOrder)

    def set_connection_status(self, is_connected, server_url=""):
        if is_connected:
            self.lbl_unreachable.hide()
            self.tree.show()
            self.product_container.show()
            self.spacer_widget.hide()
            self.btn_refresh.setEnabled(True)
        else:
            self.lbl_unreachable.setText(f"AYON is unreachable\n\n({server_url})")
            self.lbl_unreachable.show()
            self.tree.hide()
            self.product_container.hide()
            self.spacer_widget.show()
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

    def find_best_match(self, folder_name, task_name=None, multi_match=False, fallback_task=False):
        """
        Search the tree for a matching folder/task.
        folder_name: The leaf folder name to match.
        task_name: Optional task name to match within the folder.
        """
        matches = []
        
        def _recurse(parent_item):
            for r in range(parent_item.rowCount()):
                item = parent_item.child(r, 0)
                if not item: continue
                data = item.data(Qt.UserRole)
                if data and "type" in data and data["type"] != "Task":
                    # Check if leaf name matches exactly
                    name = (data.get("name") or "").lower()
                    label = (data.get("label") or "").lower()
                    search_key = (folder_name or "").lower()
                    
                    if search_key == name or search_key == label:
                        matches.append(item)
                _recurse(item)
        
        _recurse(self.model.invisibleRootItem())
        
        if not matches:
            return None
            
        if len(matches) > 1 and not multi_match:
            return None # Ambiguous
            
        # Use first match
        folder_item = matches[0]
        folder_data = folder_item.data(Qt.UserRole)
        folder_path = folder_data.get("path")
        
        # Look for task
        tasks = folder_data.get("tasks", [])
        if not tasks:
            return None
            
        target_task = None
        if task_name:
            for t in tasks:
                if t.get("name", "").lower() == task_name.lower():
                    target_task = t
                    break
                    
        if not target_task and fallback_task and tasks:
            target_task = tasks[0]
            
        if target_task:
            return {
                "folder_path": folder_path,
                "task_name": target_task.get("name"),
                "task_type": target_task.get("type"),
                "assignee": ", ".join(target_task.get("assignees", []))
            }
            
        return None

    def _on_double_click(self, index):
        # We always assign on double click now
        data = index.data(Qt.UserRole)
        # Map from proxy to source
        source_index = self.proxy.mapToSource(index)
        
        # Always use the data from the first column's item
        row_index = source_index.row()
        parent = source_index.parent()
        first_col_index = self.model.index(row_index, 0, parent)
        
        item = self.model.itemFromIndex(first_col_index)
        data = item.data(Qt.UserRole)
        
        # Check if it's a task (has folderId in data)
        if data and 'folderId' in data and 'folder_path' in data:
            folder_path = data.get('folder_path')
            task_name = data.get('name')
            task_type = data.get('type')
            assignee = ", ".join(data.get('assignees', []))
            self.task_selected.emit(folder_path, task_name, task_type, assignee)

    def _on_product_double_click(self, index):
        """Calculate variant and emit product_double_clicked signal."""
        # Map if we ever add proxy to product view, but currently it's direct
        row = index.row()
        name_item = self.product_model.item(row, 0)
        type_item = self.product_model.item(row, 1)
        if not name_item or not type_item:
            return
            
        name = name_item.text()
        product_type = type_item.text()
        
        # Calculate variant: left-strip product type from name
        variant = name
        if name.startswith(product_type):
            variant = name[len(product_type):]
            
        # Get currently selected task from the tree
        tree_selection = self.tree.selectionModel().selectedIndexes()
        if not tree_selection:
            return
            
        source_idx = self.proxy.mapToSource(tree_selection[0])
        first_col_index = self.model.index(source_idx.row(), 0, source_idx.parent())
        item = self.model.itemFromIndex(first_col_index)
        data = item.data(Qt.UserRole)
        
        # Ensure it's a task
        if data and 'folderId' in data and 'folder_path' in data:
            folder_path = data.get('folder_path')
            task_name = data.get('name')
            task_type = data.get('type')
            self.product_double_clicked.emit(folder_path, task_name, task_type, variant)

    def _on_selection_changed(self, selected, deselected):
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes: return
        
        source_idx = self.proxy.mapToSource(indexes[0])
        first_col_index = self.model.index(source_idx.row(), 0, source_idx.parent())
        item = self.model.itemFromIndex(first_col_index)
        if not item: return
        data = item.data(Qt.UserRole)
        
        if data:
            if 'folderId' in data:
                f_id = data.get('folderId')
            elif 'id' in data:
                f_id = data.get('id')
            else:
                f_id = None
                
            if f_id:
                self.info_requested.emit(f_id)

    def set_products(self, products):
        """Populate the product info list and types dropdown."""
        self.all_products = products
        
        # Update types dropdown
        types = sorted(list(set(p['type'] for p in products)))
        self.combo_product_types.clear()
        for t in types:
            self.combo_product_types.addItem(t)
            # Make the item checked
            index = self.combo_product_types.model().index(self.combo_product_types.count() - 1, 0)
            self.combo_product_types.model().setData(index, Qt.Checked, Qt.CheckStateRole)
            
        self._refresh_product_list()

    def _refresh_product_list(self):
        self.product_model.removeRows(0, self.product_model.rowCount())
        checked_types = self.combo_product_types.get_checked_items()
        
        for p in self.all_products:
            if p['type'] in checked_types:
                name_item = QStandardItem(p['name'])
                type_item = QStandardItem(p['type'])
                ver_item = QStandardItem(f"v{p['version']:03d}")
                ver_item.setTextAlignment(Qt.AlignCenter)
                self.product_model.appendRow([name_item, type_item, ver_item])
                
        self.product_view.resizeColumnToContents(0)
        self.product_view.resizeColumnToContents(1)

    def _on_hide_products_toggled(self, checked):
        if checked:
            self.combo_product_types.hide()
            self.product_view.hide()
            self.btn_hide_products.setText("Show")
            # Shrink the product container in the splitter
            self.splitter.setSizes([1000, 30])
        else:
            self.combo_product_types.show()
            self.product_view.show()
            self.btn_hide_products.setText("Hide")
            # Restore some size
            self.splitter.setSizes([700, 300])

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
                data.get('folder_path'), data.get('name'), data.get('type'), ", ".join(data.get('assignees', []))
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

    def select_path(self, folder_path, task_name=None):
        """Programmatically select and scroll to a folder or task in the tree view."""
        def _recurse(parent_item):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item: continue
                
                data = item.data(Qt.UserRole)
                if data:
                    is_task = "folderId" in data
                    if is_task:
                        if task_name and data.get("folder_path") == folder_path and data.get("name") == task_name:
                            return item
                    else:
                        if not task_name and data.get("path") == folder_path:
                            return item
                
                # Recurse children
                res = _recurse(item)
                if res:
                    return res
            return None

        matched_item = _recurse(self.model.invisibleRootItem())
        if matched_item:
            src_idx = self.model.indexFromItem(matched_item)
            proxy_idx = self.proxy.mapFromSource(src_idx)
            if proxy_idx.isValid():
                # Ensure parents are expanded all the way to the item
                parent_idx = proxy_idx.parent()
                while parent_idx.isValid():
                    self.tree.expand(parent_idx)
                    parent_idx = parent_idx.parent()
                
                self.tree.setCurrentIndex(proxy_idx)
                self.tree.scrollTo(proxy_idx)
                return True
        return False

