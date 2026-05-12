import os
import re
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QPixmap, QColor

class ImageItem:
    def __init__(self, file_path, label=None, version=1, category="Other", 
                 preset_name=None, variant=None, product_type=None, camel_case=True,
                 representation=None, colorspace=None, rep_tags=None, is_sequence=False,
                 preset_data=None, frame_start=None, frame_end=None, metadata=None, comment=""):
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
        self.camel_case = camel_case
        self.representation = representation
        self.is_sequence = is_sequence
        self.colorspace = colorspace
        self.rep_tags = rep_tags
        self.preset_data = preset_data or {}
        self.frame_start = frame_start
        self.frame_end = frame_end
        self.metadata = metadata or {}
        self.is_duplicate = False
        self.version_collision = None
        self.comment = comment

class ImageTableModel(QAbstractTableModel):
    data_changed = Signal()

    COLUMNS = [
        "Tag", "Thumbnail", "Label", "Variant", "Product Name", "Category", "Preset", "Version", 
        "Last Version", "Age", "AYON Path", "Key Value Pairs"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.presets = {} # category -> preset_name
        self.age_unit = "minutes" # minutes, hours, days
        self.label_allowed_regex = "^[a-zA-Z0-9_\\-\\.\\s]*$"
        self.product_name_template = "{label}"
        self.product_name_camel = True
        self.stills_thumb_same = True

    def set_presets(self, presets):
        self.presets = presets
        self.layoutChanged.emit()

    def update_item(self, item):
        """Notify the model that an item has been updated (e.g. metadata fetched)."""
        try:
            row = self.items.index(item)
            # Notify that all data columns for this row might have changed
            self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
        except ValueError:
            pass

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
            
            # Version conflict: if server version >= current version
            if item.last_ayon_version is not None and item.last_ayon_version >= item.version:
                if col in [7, 8]: # Version, Last Version
                    return QColor("#ff8c00")
                    
            # Dim non-editable text columns: Variant(3), Product Name(4), Category(5), Preset(6), Last Version(8), Age(9), Path(10)
            if col in [3, 4, 5, 6, 8, 9, 10]:
                return QColor("#888888")
            return None

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if col == 2: return item.label
            if col == 3: # Variant
                return self._expand_string(item.variant, item)
            if col == 4: # Product Name
                return self._expand_string(self.product_name_template, item, use_global_camel=True)
            if col == 5: return item.category
            if col == 6: # Preset
                return item.preset_name if item.preset_name else "-"
            if col == 7: return str(item.version)
            if role == Qt.DisplayRole:
                if col == 8: return str(item.last_ayon_version) if item.last_ayon_version else "-"
                if col == 9: 
                    m = item.age_minutes
                    if self.age_unit == "minutes": return f"{m}m"
                    if self.age_unit == "hours": return f"{m//60}h"
                    if self.age_unit == "days": return f"{m//1440}d"
                    
                    # Default auto-formatting if no specific unit set
                    if m < 60: return f"{m}m"
                    if m < 1440: return f"{m//60}h"
                    return f"{m//1440}d"
                if col == 10: return item.ayon_path
                if col == 11: # Key Value Pairs
                    return self._get_all_tokens_string(item)
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
            
            if col == 0 and (getattr(item, "version_collision", False) or getattr(item, "is_duplicate", False)):
                return QColor("#ff8c00")
                
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
            elif col == 7: # Version
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
        if index.column() in [2, 7]: # Label, Version
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
            if column == 3: return self._expand_string(item.variant, item)
            if column == 4: return self._expand_string(self.product_name_template, item, use_global_camel=True)
            if column == 5: return item.category
            if column == 6: 
                return item.preset_name or ""
            if column == 7: return item.version
            if column == 8: return item.last_ayon_version or 0
            if column == 9: return item.age_minutes
            if column == 10: return item.ayon_path
            return ""

        reverse = (order == Qt.DescendingOrder)
        self.items.sort(key=get_value, reverse=reverse)
        self.layoutChanged.emit()

    def _get_replacements(self, item, text="", use_global_camel=False):
        """Build the dictionary of token replacements for an item."""
        ayon_parts = [p for p in item.ayon_path.split("/") if p]
        task_name = ""
        folder_name = ""
        if ayon_parts:
            task_name = ayon_parts[-1]
            if len(ayon_parts) > 1:
                folder_name = ayon_parts[-2]
        
        parent_folder = os.path.basename(os.path.dirname(item.file_path))
        ayon_folder_path = "/".join(item.ayon_path.split("/")[:-1])
        
        # Filename with hashes for sequences
        filename_val = item.file_path.replace("\\", "/")
        if item.is_sequence:
            import re
            base, ext = os.path.splitext(filename_val)
            # Find the last number in the basename
            match = re.search(r"(\d+)$", base)
            if match:
                digits = match.group(1)
                hashes = "#" * len(digits)
                filename_val = base[:match.start()] + hashes + ext
        
        p_data = item.preset_data or {}
        
        # Replacement mapping
        replacements = {
            "{product_type}": item.product_type or "",
            "{task_name}": task_name,
            "{folder_name}": folder_name,
            "{parent_folder}": parent_folder,
            "{ayon_folder_path}": ayon_folder_path,
            "{label}": item.label or "",
            "{variant}": self._expand_string(item.variant, item) if text != item.variant else (item.variant or ""),
            "{filename}": filename_val,
            "{file_name}": os.path.splitext(os.path.basename(item.file_path))[0],
            "{extension}": os.path.splitext(item.file_path)[1].replace(".", "").lower(),
            "{repre}": p_data.get("Representation", ""),
            "{REPRE}": p_data.get("Representation", ""),
            "{head}": str(p_data.get("Handle Start", "0")),
            "{HEAD}": str(p_data.get("Handle Start", "0")),
            "{tail}": str(p_data.get("Handle End", "0")),
            "{TAIL}": str(p_data.get("Handle End", "0")),
            "{slate_exists}": "True" if p_data.get("Slate Exists") else "False",
            "{SLATE_EXISTS}": "True" if p_data.get("Slate Exists") else "False",
            "{fps}": str(p_data.get("FPS", "")),
            "{FPS}": str(p_data.get("FPS", "")),
            "{repre_color}": p_data.get("Colorspace", ""),
            "{REPRE_COLOR}": p_data.get("Colorspace", ""),
            "{repre_tags}": p_data.get("Tags", ""),
            "{REPRE_TAGS}": p_data.get("Tags", ""),
            "{version}": str(item.version),
            "{VERSION}": str(item.version),
            "{frame_start}": str(item.frame_start) if item.frame_start is not None else "",
            "{FRAME_START}": str(item.frame_start) if item.frame_start is not None else "",
            "{frame_end}": str(item.frame_end) if item.frame_end is not None else "",
            "{FRAME_END}": str(item.frame_end) if item.frame_end is not None else "",
            "{comment}": item.comment or "",
            "{COMMENT}": item.comment or "",
            "{is_duplicate}": "True" if getattr(item, "is_duplicate", False) else "False",
            "{IS_DUPLICATE}": "True" if getattr(item, "is_duplicate", False) else "False",
            "{version_collision}": str(getattr(item, "version_collision", "None")),
            "{VERSION_COLLISION}": str(getattr(item, "version_collision", "None")),
            "{thumb_path}": filename_val if (item.category == "Still" and getattr(self, "stills_thumb_same", True)) else "",
            "{THUMB_PATH}": filename_val if (item.category == "Still" and getattr(self, "stills_thumb_same", True)) else "",
        }
        return replacements

    def _get_all_tokens_string(self, item):
        """Returns a string listing all key=value pairs for the item."""
        replacements = self._get_replacements(item)
        # Sort keys to be consistent
        sorted_keys = sorted([k for k in replacements.keys() if k.islower()])
        pairs = []
        for k in sorted_keys:
            val = replacements[k]
            pairs.append(f"{k}={val}")
        
        # Add metadata tokens too
        for mk, mv in item.metadata.items():
            pairs.append(f"{{metadata.{mk}}}={mv}")
            
        return "  ".join(pairs)

    def _expand_string(self, text, item, use_global_camel=False):
        if not text:
            return ""
            
        replacements = self._get_replacements(item, text, use_global_camel)
        
        import re
        # Sort keys by length (descending) to avoid partial matches (e.g., {repre} matching inside {repre_color})
        sorted_keys = sorted(replacements.keys(), key=len, reverse=True)
        pattern = "|".join(re.escape(k) for k in sorted_keys)
        
        def replacer(match):
            key = match.group(0)
            val = replacements.get(key)
            if val is None:
                # Try case-insensitive lookup
                val = replacements.get(key.lower(), replacements.get(key.upper(), key))
            # CamelCase logic
            camel = self.product_name_camel if use_global_camel else item.camel_case
            
            if camel and match.start() > 0 and val:
                val = val[0].upper() + val[1:]
            return val

        res = re.sub(pattern, replacer, text, flags=re.IGNORECASE)
        
        # Meta data tokens (e.g. {metadata.width})
        def metadata_replacer(match):
            key = match.group(1).lower()
            val = item.metadata.get(key)
            if val is not None:
                return str(val)
            return match.group(0) # Keep token if not found
            
        res = re.sub(r"\{metadata\.([^}]+)\}", metadata_replacer, res)
            
        return res
