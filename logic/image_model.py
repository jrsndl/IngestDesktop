import os
import re
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QPixmap, QColor

class ImageItem:
    def __init__(self, file_path, label=None, version=1, category="Other", preset_name=None, variant=None, product_type=None):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.label = label or os.path.splitext(self.filename)[0]
        self.version = version
        self.category = category
        self.ayon_path = ""
        self.last_ayon_version = None
        self.is_tagged = True
        self.is_selected = False
        self.thumbnail = None
        self.high_res_thumbnail = None
        self.is_high_res_loading = False
        self.creation_time = 0
        self.modification_time = 0
        self.age_minutes = 0 
        self.position = (0, 0) # (x, y)
        self.preset_name = preset_name
        self.variant = variant
        self.product_type = product_type

class ImageTableModel(QAbstractTableModel):
    data_changed = Signal()

    COLUMNS = [
        "Tag", "Thumbnail", "Label", "Category", "Preset", "Variant", "Version", 
        "Last AYON Version", "Age", "AYON Path"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.presets = {} # category -> preset_name
        self.age_unit = "minutes" # minutes, hours, days
        self.label_allowed_regex = "^[a-zA-Z0-9_\\-\\.\\s]*$"

    def set_presets(self, presets):
        self.presets = presets
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return None

        item = self.items[index.row()]
        col = index.column()

        if role == Qt.ForegroundRole:
            if not item.is_tagged:
                return QColor("#ff4444")
            return None

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if col == 2: return item.label
            if col == 3: return item.category
            if col == 4: # Preset
                return item.preset_name if item.preset_name else "-"
            if col == 5: # Variant
                return self._expand_variant(item)
            if col == 6: return str(item.version)
            if role == Qt.DisplayRole:
                if col == 7: return str(item.last_ayon_version) if item.last_ayon_version else "-"
                if col == 7: 
                    m = item.age_minutes
                    if self.age_unit == "minutes": return f"{m}m"
                    if self.age_unit == "hours": return f"{m//60}h"
                    if self.age_unit == "days": return f"{m//1440}d"
                    
                    # Default auto-formatting if no specific unit set
                    if m < 60: return f"{m}m"
                    if m < 1440: return f"{m//60}h"
                    return f"{m//1440}d"
                if col == 8: return item.ayon_path
            else:
                # For EditRole in non-label/version columns
                return None
        
        elif role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if item.is_tagged else Qt.Unchecked

        elif role == Qt.DecorationRole and col == 1:
            return item.thumbnail

        elif role == Qt.BackgroundRole:
            if item.is_selected:
                return None # Handled by selection model usually
            if not item.is_tagged:
                return None # Or a dim color?

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return False

        item = self.items[index.row()]
        col = index.column()

        if role == Qt.CheckStateRole and col == 0:
            item.is_tagged = (value == Qt.Checked)
            # Emit for the entire row to refresh ForegroundRole color
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()-1))
            return True
        
        if role == Qt.EditRole:
            if col == 2:
                # Temporarily disabled regex validation per user request
                # if not re.match(self.label_allowed_regex, value):
                #     return False
                item.label = value
            elif col == 5: # Version
                try:
                    item.version = int(value)
                except ValueError:
                    return False
            self.dataChanged.emit(index, index)
            return True

        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.COLUMNS[section]
            else:
                return str(section + 1)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        if index.column() in [2, 5]: # Label, Version
            flags |= Qt.ItemIsEditable
            
        return flags

    def clear(self):
        self.beginResetModel()
        self.items = []
        self.endResetModel()

    def set_age_unit(self, unit):
        if unit in ["minutes", "hours", "days"]:
            self.age_unit = unit
            self.layoutChanged.emit()

    def add_items(self, new_items):
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items) + len(new_items) - 1)
        self.items.extend(new_items)
        self.endInsertRows()

    def toggle_tag_selection(self, selection_model):
        """Toggle ingest tag for all selected rows."""
        rows = set(index.row() for index in selection_model.selectedRows())
        for row in rows:
            item = self.items[row]
            item.is_tagged = not item.is_tagged
        
        # Notify views
        if rows:
            self.dataChanged.emit(self.index(min(rows), 0), self.index(max(rows), 0))

    def modify_labels(self, selection_model, action, data=None):
        """Apply bulk modifications to labels of selected items."""
        rows = set(index.row() for index in selection_model.selectedRows())
        if not rows: return
        
        for row in rows:
            item = self.items[row]
            if action == "reset":
                # Strip extensions, counters, and versions to reset to base name
                name = os.path.splitext(item.filename)[0]
                name = re.sub(r'[\._]\d{3,6}$', '', name)
                name = re.sub(r'(_v\d+)', '', name)
                item.label = name
            elif action == "prefix":
                item.label = f"{data}{item.label}"
            elif action == "suffix":
                item.label = f"{item.label}{data}"
            elif action == "search_replace":
                search_str, replace_str = data
                item.label = item.label.replace(search_str, replace_str)
        
        # Notify views that Label column (2) changed
        self.dataChanged.emit(self.index(min(rows), 2), self.index(max(rows), 2))

    def sort(self, column, order=Qt.AscendingOrder):
        """Sort model by a specific column."""
        if not self.items:
            return

        def get_value(item):
            if column == 0: return item.is_tagged
            if column == 2: return item.label
            if column == 3: return item.category
            if column == 4: 
                return item.preset_name or ""
            if column == 5:
                return self._expand_variant(item)
            if column == 6: return item.version
            if column == 7: return item.last_ayon_version or 0
            if column == 8: return item.age_minutes
            if column == 9: return item.ayon_path
            return ""

        reverse = (order == Qt.DescendingOrder)
        self.items.sort(key=get_value, reverse=reverse)
        self.layoutChanged.emit()

    def _expand_variant(self, item):
        if not item.variant:
            return "-"
            
        variant = item.variant
        
        # Parse AYON path
        # Example: /Project/FolderA/FolderB/Task
        ayon_parts = [p for p in item.ayon_path.split("/") if p]
        
        task_name = ""
        folder_name = ""
        parent_folder = ""
        
        if ayon_parts:
            task_name = ayon_parts[-1]
            if len(ayon_parts) > 1:
                folder_name = ayon_parts[-2]
            if len(ayon_parts) > 2:
                parent_folder = ayon_parts[-3]
        
        # Replacement mapping
        replacements = {
            "{product_type}": item.product_type or "",
            "{task_name}": task_name,
            "{folder_name}": folder_name,
            "{parent_folder}": parent_folder,
            "{label}": item.label or "",
            "{file_name}": os.path.splitext(os.path.basename(item.file_path))[0]
        }
        
        res = variant
        for key, val in replacements.items():
            res = res.replace(key, val)
            
        return res
