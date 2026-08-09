import os
import re
from utils import strip_sequence_counter, app_dir
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QPixmap, QColor

def parse_version_folder(directory, version_regex):
    if not directory:
        return None, None
    base = os.path.basename(directory)
    match = re.match(r"^" + version_regex + r"$", base, re.IGNORECASE)
    if match:
        try:
            ver = int(match.group(2))
            parent = os.path.dirname(directory)
            return parent, ver
        except (IndexError, ValueError):
            pass
    return None, None

class ImageItem:
    def __init__(self, file_path, label=None, version=1, category="Other", 
                 preset_name=None, variant=None, product_type=None, camel_case=True,
                 representation=None, colorspace=None, rep_tags=None, is_sequence=False,
                 preset_data=None, frame_start=None, frame_end=None, metadata=None, comment="", variant_user="", version_user=""):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.label = label or os.path.splitext(self.filename)[0]
        self.version = version
        self.version_user = str(version_user) if version_user is not None else ""
        self.category = category
        self.ayon_path = ""
        self.ayon_task_name = ""
        self.ayon_task_type = ""
        self.ayon_task_assignee = ""
        self.conversion_thumb_path = ""
        self.review_status = "do not convert" # ["do not convert", "waiting", "processing", "done", "failed"]
        self.last_ayon_version = None
        self.is_tagged = True
        self.is_selected = False
        self.thumbnail = None
        self.high_res_thumbnail = None
        self.is_high_res_loading = False
        self.high_res_failed = False
        self.creation_time = 0
        self.modification_time = 0
        self.age_minutes = 0 
        self.position = (0, 0) # (x, y)
        self.size = 150
        self.is_manually_moved = False
        self.is_custom_size = False
        self.preset_name = preset_name
        self.variant = variant
        self.variant_user = variant_user or ""
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
        self.ingest_status = "unknown"
        self.is_review_repre = False
        self.model = None

    @property
    def effective_version(self):
        v_user = str(getattr(self, "version_user", "")).strip()
        if v_user:
            try:
                return int(v_user)
            except ValueError:
                return v_user
        return self.version

    @property
    def effective_variant(self):
        v_user = getattr(self, "variant_user", "") or ""
        if v_user.strip():
            return v_user.strip()

        parsed_v = (self.metadata.get("variant_parsed", "") if self.metadata else "") or ""
        var_template = getattr(self, "variant", "") or ""

        if parsed_v and (not var_template or var_template in ("{variant_parsed}", "{variant}")):
            return parsed_v

        if parsed_v and "{variant_parsed}" in var_template:
            return var_template.replace("{variant_parsed}", parsed_v)

        if var_template:
            return var_template

        return parsed_v

class ImageTableModel(QAbstractTableModel):
    data_changed = Signal()

    COLUMNS = [
        "Enable", "Thumbnail", "Label", "Variant", "Variant User", "Product Name", "Group By", "Category", "Preset", "Version", 
        "Version User", "Last Version", "Age", "Review", "AYON Path", "Key Value Pairs", "Ingest Status"
    ]

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, value):
        self._items = value
        self.rebuild_version_stacks()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.v_stack_enabled = False
        self.version_regex = r"([._]v|v)(\d+)"
        self.version_stacks = {}
        self.presets = {} # category -> preset_name
        self.age_unit = "minutes" # minutes, hours, days
        self.label_allowed_regex = "^[a-zA-Z0-9_\\-\\.\\s]*$"
        self.product_name_template = "{label}"
        self.product_name_camel = True
        self.stills_thumb_same = True
        self.source_folder = ""
        self.thumb_location = "Relative to Source Folder"
        self.thumb_location_path = "_thumbs"
        self.thumb_suffix = "_thumbnail"
        self.thumb_format = ".jpg"
        self.ffmpeg_path = "ffmpeg.exe"
        self.ffprobe_path = "ffprobe.exe"
        self.oiiotool_path = "oiiotool.exe"
        self.vfxtranscode = ""
        self.ocio_config = ""
        self.show_thumbs = False
        self.show_grouped = False
        self.default_fps = 25.0
        self.use_fps_from_metadata = True

    def set_presets(self, presets):
        self.presets = presets
        self.layoutChanged.emit()

    def expand_tokens(self, text, item):
        """Public wrapper for token expansion."""
        return self._expand_string(text, item)

    def update_item(self, item):
        """Notify the model that an item has been updated (e.g. metadata fetched)."""
        if hasattr(item, "thumbnail_image") and item.thumbnail_image:
            item.thumbnail = QPixmap.fromImage(item.thumbnail_image)
            try:
                delattr(item, "thumbnail_image")
            except AttributeError:
                pass
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
            
            # Version conflict handling:
            last_v = item.last_ayon_version
            if last_v is not None:
                eff_ver = item.effective_version
                base_colliding = (last_v >= item.version) or getattr(item, "version_collision", False)
                
                try:
                    eff_v_int = int(eff_ver)
                    eff_colliding = (last_v >= eff_v_int)
                except (ValueError, TypeError):
                    eff_colliding = True

                # Column 9 (Version): marked red if base version collided with last_v
                if col == 9 and base_colliding:
                    return QColor("#f44336")
                    
                # Column 10 (Version User): marked red if user version override still collides with last_v
                if col == 10 and eff_colliding and str(getattr(item, "version_user", "")).strip():
                    return QColor("#f44336")
                    
                # Column 11 (Last Version): marked orange if there is a version collision
                if col == 11 and (base_colliding or eff_colliding):
                    return QColor("#ff8c00")
                    
            # Dim non-editable text columns
            if col in [3, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16]:
                return QColor("#888888")
            
            if col == 16:
                if item.ingest_status == "OK":
                    return QColor("#4caf50")
                elif item.ingest_status == "Failed":
                    return QColor("#f44336")
            return None

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if col == 2: return item.label
            if col == 3: # Variant (Effective Variant)
                return item.effective_variant
            if col == 4: # Variant User
                return getattr(item, "variant_user", "")
            if col == 5: # Product Name
                return self._expand_string(self.product_name_template, item, use_global_camel=True)
            if col == 6: # Group By
                key = getattr(item, "group_key", "") or "-"
                if getattr(item, "group_error", False):
                    missing_str = ", ".join(getattr(item, "group_missing_repres", []))
                    return f"{key} [Missing: {missing_str}]"
                return key
            if col == 7: return item.category
            if col == 8: # Preset
                return item.preset_name if item.preset_name else "-"
            if col == 9: return str(item.version)
            if col == 10: return str(getattr(item, "version_user", ""))
            if role == Qt.DisplayRole:
                if col == 11: return str(item.last_ayon_version) if item.last_ayon_version is not None else "-"
                if col == 12: 
                    m = item.age_minutes
                    if self.age_unit == "minutes": return f"{m}m"
                    if self.age_unit == "hours": return f"{m//60}h"
                    if self.age_unit == "days": return f"{m//1440}d"
                    
                    # Default auto-formatting if no specific unit set
                    if m < 60: return f"{m}m"
                    if m < 1440: return f"{m//60}h"
                    return f"{m//1440}d"
                if col == 13: return item.review_status
                if col == 14: return item.ayon_path
                if col == 15: # Key Value Pairs
                    return self._get_all_tokens_string(item)
                if col == 16: return item.ingest_status
            else:
                # For EditRole in non-editable columns
                return None
        
        elif role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if item.is_tagged else Qt.Unchecked

        elif role == Qt.DecorationRole and col == 1:
            if getattr(self, "show_thumbs", False):
                ayon_thumb = getattr(item, "ayon_thumbnail", None)
                if ayon_thumb:
                    return ayon_thumb
            return item.thumbnail

        elif role == Qt.BackgroundRole:
            if item.is_selected:
                return None # Handled by selection model usually
            
            if col == 0 and (getattr(item, "version_collision", False) or getattr(item, "is_duplicate", False)):
                return QColor("#ff8c00")
                
            if getattr(item, "group_error", False):
                return QColor("#3e1f1f")

            if getattr(self, "show_grouped", False):
                g_idx = getattr(item, "group_index", 0)
                if not hasattr(self, "GROUP_DIM_COLORS"):
                    self.GROUP_DIM_COLORS = [
                        QColor("#1b2430"),  # Dim Steel Blue
                        QColor("#251c30"),  # Dim Soft Purple
                        QColor("#18292e"),  # Dim Dark Cyan / Teal
                        QColor("#1c213d"),  # Dim Indigo
                        QColor("#241e3d"),  # Dim Blue-Violet
                        QColor("#2b1e2c"),  # Dim Dark Violet
                    ]
                return self.GROUP_DIM_COLORS[g_idx % len(self.GROUP_DIM_COLORS)]

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
                item.label = value
            elif col == 4: # Variant User
                item.variant_user = value
                # Emit for the entire row to update Variant, Product Name, and tokens
                self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()-1))
                return True
            elif col == 9: # Version
                try:
                    item.version = int(value)
                except ValueError:
                    return False
            elif col == 10: # Version User
                item.version_user = str(value).strip()
                self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()-1))
                return True
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
        if index.column() in [2, 4, 9, 10]: # Label, Variant User, Version, Version User
            flags |= Qt.ItemIsEditable
            
        return flags

    def clear(self):
        self.beginResetModel()
        self._items = []
        self.version_stacks = {}
        self.endResetModel()

    def set_age_unit(self, unit):
        if unit in ["minutes", "hours", "days"]:
            self.age_unit = unit
            self.layoutChanged.emit()

    def add_items(self, new_items):
        for item in new_items:
            item.model = self
            if hasattr(item, "thumbnail_image") and item.thumbnail_image:
                item.thumbnail = QPixmap.fromImage(item.thumbnail_image)
                try:
                    delattr(item, "thumbnail_image")
                except AttributeError:
                    pass
        self.beginInsertRows(QModelIndex(), len(self._items), len(self._items) + len(new_items) - 1)
        self._items.extend(new_items)
        self.rebuild_version_stacks()
        self.endInsertRows()

    def get_version_stack_key(self, item):
        import os
        import re
        from utils import strip_sequence_counter
        
        filename = os.path.basename(item.file_path)
        version_regex = getattr(self, "version_regex", r"([._]v|v)(\d+)")
        
        if item.is_sequence:
            # 1. remove file counter
            base_no_counter = strip_sequence_counter(filename)
            
            # Get extension
            ext = os.path.splitext(filename)[1].lower()
            if ext and re.match(r"^\.\d+$", ext):
                ext = ""
            name_no_counter = f"{base_no_counter}{ext}"
            
            # 2. remove the version by the regex (entire match)
            clean_name = re.sub(version_regex, "", name_no_counter, flags=re.IGNORECASE)
            return (clean_name.lower(), True)
        else:
            # Still / video / other category:
            # 1. remove the version by the regex (entire match)
            clean_name = re.sub(version_regex, "", filename, flags=re.IGNORECASE)
            return (clean_name.lower(), False)

    def rebuild_version_stacks(self):
        old_picked = {key: stack["picked"] for key, stack in getattr(self, "version_stacks", {}).items() if stack["picked"] is not None}
        self.version_stacks = {}
        for item in self._items:
            item.model = self
            key = self.get_version_stack_key(item)
            if key not in self.version_stacks:
                self.version_stacks[key] = {
                    "items": [],
                    "picked": None,
                    "min": None,
                    "max": None
                }
            self.version_stacks[key]["items"].append(item)
        
        for key, stack in self.version_stacks.items():
            versions = [item.version for item in stack["items"]]
            stack["min"] = min(versions) if versions else 1
            stack["max"] = max(versions) if versions else 1
            
            if key in old_picked and old_picked[key] in versions:
                stack["picked"] = old_picked[key]
            else:
                stack["picked"] = stack["max"]

    def is_item_visible_by_v_stack(self, item, v_stack_enabled):
        if not v_stack_enabled:
            return True
        key = self.get_version_stack_key(item)
        if key in self.version_stacks:
            stack = self.version_stacks[key]
            return item.version == stack["picked"]
        return True

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
                if search_str in ["", "*"]:
                    item.label = replace_str
                else:
                    item.label = item.label.replace(search_str, replace_str)
            elif action == "trim_length":
                # Only keep first N characters
                try:
                    n = int(data)
                    item.label = item.label[:n]
                except (ValueError, TypeError):
                    pass
            elif action == "trim_right":
                # Remove N characters from right
                try:
                    n = int(data)
                    if n > 0:
                        item.label = item.label[:-n] if n < len(item.label) else ""
                except (ValueError, TypeError):
                    pass
            elif action == "trim_left":
                # Remove N characters from left
                try:
                    n = int(data)
                    if n > 0:
                        item.label = item.label[n:] if n < len(item.label) else ""
                except (ValueError, TypeError):
                    pass
        
        # Notify views that Label column (2) changed
        self.dataChanged.emit(self.index(min(rows), 2), self.index(max(rows), 2))

    def sort(self, column, order=Qt.AscendingOrder):
        """Sort model by a specific column."""
        if not self.items:
            return

        def get_value(item):
            if column == 0: return item.is_tagged
            if column == 2: return item.label
            if column == 3:
                if getattr(item, "variant_user", "") and item.variant_user.strip():
                    return item.variant_user.strip()
                return self._expand_string(item.variant, item)
            if column == 4: return getattr(item, "variant_user", "") or ""
            if column == 5: return self._expand_string(self.product_name_template, item, use_global_camel=True)
            if column == 6: return getattr(item, "group_key", "") or ""
            if column == 7: return item.category
            if column == 8: return item.preset_name or ""
            if column == 9: return item.version
            if column == 10: return getattr(item, "version_user", "") or ""
            if column == 11: return item.last_ayon_version or 0
            if column == 12: return item.age_minutes
            if column == 13: return item.review_status
            if column == 14: return item.ayon_path
            return ""

        reverse = (order == Qt.DescendingOrder)
        self.items.sort(key=get_value, reverse=reverse)
        self.layoutChanged.emit()

    def _get_replacements(self, item, text="", use_global_camel=False):
        """Build the dictionary of token replacements for an item."""
        ayon_parts = [p for p in item.ayon_path.split("/") if p]
        task_name = item.metadata.get("task_name", "")
        folder_name = item.metadata.get("folder_name", "")
        
        if ayon_parts:
            # If assigned, prefer the AYON names unless metadata explicitly overrides?
            # Actually, usually AYON is the source of truth for these tokens once assigned.
            # But let's allow metadata to provide them if AYON is empty.
            if not task_name:
                task_name = ayon_parts[-1]
            if not folder_name and len(ayon_parts) > 1:
                folder_name = ayon_parts[-2]
        
        parent_folder = os.path.basename(os.path.dirname(item.file_path))
        ayon_folder_path = "/".join(item.ayon_path.split("/")[:-1])
        
        # Filename with hashes for sequences
        filename_val = item.file_path.replace("\\", "/")
        filename_printf_val = filename_val
        if item.is_sequence:
            import re
            base, ext = os.path.splitext(filename_val)
            # Find the last number in the basename
            match = re.search(r"(\d+)$", base)
            if match:
                digits = match.group(1)
                hashes = "#" * len(digits)
                filename_val = base[:match.start()] + hashes + ext
                printf = f"%0{len(digits)}d"
                filename_printf_val = base[:match.start()] + printf + ext
        
        p_data = item.preset_data or {}
        
        # Precompute expanded representation only if "{repre}" is actually in the text to avoid eager recursive loops
        repre_template = item.representation or p_data.get("Representation") or "{extension}"
        repre_expanded = self._expand_string(repre_template, item) if (text and "{repre}" in text.lower() and text != repre_template) else repre_template
        
        # Resolve FPS
        fps_val = None
        if p_data.get("FPS Override", False):
            fps_preset = p_data.get("FPS")
            if fps_preset is not None:
                try:
                    fps_val = float(fps_preset)
                except (ValueError, TypeError):
                    pass
        else:
            use_meta = getattr(self, "use_fps_from_metadata", True)
            if use_meta and p_data.get("FPS From Metadata", True):
                fps_meta = item.metadata.get("framerate")
                if fps_meta is not None:
                    try:
                        fps_val = float(fps_meta)
                    except (ValueError, TypeError):
                        pass
        if fps_val is None:
            fps_val = getattr(self, "default_fps", 25.0)

        fps_str = str(fps_val) if fps_val is not None else ""
        fps_int_str = str(int(round(fps_val))) if fps_val is not None else ""

        variant_user_val = getattr(item, "variant_user", "")
        variant_val = item.effective_variant

        prod_name_val = self._expand_string(self.product_name_template, item, use_global_camel=True) if (text and ("{product_name}" in text.lower() or "{prod_name}" in text.lower()) and text != self.product_name_template) else ""
        if not prod_name_val and (not text or "{product_name}" in text.lower() or "{prod_name}" in text.lower()):
            prod_name_val = self._expand_string(self.product_name_template, item, use_global_camel=True)

        # Replacement mapping
        replacements = {
            "{product_type}": item.product_type or "",
            "{task_name}": task_name,
            "{folder_name}": folder_name,
            "{variant_parsed}": item.metadata.get("variant_parsed", ""),
            "{sequence}": item.metadata.get("sequence", ""),
            "{episode}": item.metadata.get("episode", ""),
            "{parent_folder}": parent_folder,
            "{ayon_path}": item.ayon_path or "",
            "{AYON_PATH}": item.ayon_path or "",
            "{ayon_path_val}": item.ayon_path or "",
            "{ayon_folder_path}": ayon_folder_path,
            "{product_name}": prod_name_val,
            "{PRODUCT_NAME}": prod_name_val,
            "{prod_name}": prod_name_val,
            "{PROD_NAME}": prod_name_val,
            "{item.version}": str(item.effective_version),
            "{ayon_task_name}": item.ayon_task_name or "",
            "{ayon_task_type}": item.ayon_task_type or "",
            "{ayon_task_assignee}": item.ayon_task_assignee or "",
            "{label}": item.label or "",
            "{variant}": variant_val,
            "{variant_user}": variant_user_val or "",
            "{filename}": filename_val,
            "{filename_printf}": filename_printf_val,
            "{file_name}": os.path.splitext(os.path.basename(item.file_path))[0],
            "{extension}": os.path.splitext(item.file_path)[1].replace(".", "").lower(),
            "{repre}": repre_expanded,
            "{REPRE}": repre_expanded,
            "{head}": str(p_data.get("Handle Start", "0")),
            "{HEAD}": str(p_data.get("Handle Start", "0")),
            "{tail}": str(p_data.get("Handle End", "0")),
            "{TAIL}": str(p_data.get("Handle End", "0")),
            "{slate_exists}": "True" if p_data.get("Slate Exists") else "False",
            "{SLATE_EXISTS}": "True" if p_data.get("Slate Exists") else "False",
            "{fps}": fps_str,
            "{FPS}": fps_str,
            "{fps_int}": fps_int_str,
            "{FPS_INT}": fps_int_str,
            "{repre_color}": p_data.get("Colorspace", ""),
            "{REPRE_COLOR}": p_data.get("Colorspace", ""),
            "{repre_tags}": p_data.get("Tags", ""),
            "{REPRE_TAGS}": p_data.get("Tags", ""),
            "{version}": str(item.effective_version),
            "{VERSION}": str(item.effective_version),
            "{version_user}": str(getattr(item, "version_user", "")),
            "{VERSION_USER}": str(getattr(item, "version_user", "")),
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
            "{prefs_highres_thumb_size}": str(getattr(self, "high_res_size", 512)),
            "{prefs_thumb_path}": self._get_prefs_thumb_path(item),
            "{prefs_review_path}": self._get_prefs_review_path(item),
            "{review_repre}": p_data.get("Review Representation", "h264"),
            "{REVIEW_REPRE}": p_data.get("Review Representation", "h264"),
            "{review_colorspace}": p_data.get("Review Colorspace", "Output - sRGB"),
            "{REVIEW_COLORSPACE}": p_data.get("Review Colorspace", "Output - sRGB"),
            "{review_tags}": p_data.get("Review Tags", "passing;ftracreview;webreview"),
            "{REVIEW_TAGS}": p_data.get("Review Tags", "passing;ftracreview;webreview"),
            "{ffmpeg}": self.ffmpeg_path,
            "{ffprobe}": self.ffprobe_path,
            "{oiiotool}": self.oiiotool_path,
            "{vfxtranscode}": os.path.abspath(self.vfxtranscode).replace("\\", "/") if self.vfxtranscode else "",
            "{VFXTRANSCODE}": os.path.abspath(self.vfxtranscode).replace("\\", "/") if self.vfxtranscode else "",
            "{ocio}": os.path.abspath(self.ocio_config).replace("\\", "/") if self.ocio_config else "",
            "{OCIO}": os.path.abspath(self.ocio_config).replace("\\", "/") if self.ocio_config else "",
            "{IngestDesktop}": app_dir.replace("\\", "/"),
            "{INGESTDESKTOP}": app_dir.replace("\\", "/"),
            "{ingest_status}": getattr(item, "ingest_status", "unknown"),
            "{INGEST_STATUS}": getattr(item, "ingest_status", "unknown"),
        }
        return replacements

    def _get_all_tokens_string(self, item):
        """Returns a string listing all key=value pairs for the item."""
        replacements = self._get_replacements(item)
        # Sort keys to be consistent, show only lowercase/primary tokens to avoid cluttering with CAPS duplicates
        sorted_keys = sorted([k for k in replacements.keys() if k.islower()])
        pairs = []
        for k in sorted_keys:
            val = replacements[k]
            if val:
                pairs.append(f"{k}={val}")
        
        # Add metadata tokens EXCEPT the ones we already show as primary tokens
        primary_names = ["folder_name", "task_name", "variant_parsed", "sequence", "episode"]
        for mk, mv in item.metadata.items():
            if mk not in primary_names:
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

    def _get_prefs_thumb_path(self, item):
        """Calculate the thumbnail path based on preferences."""
        source_file = item.file_path.replace("\\", "/")
        base_dir = os.path.dirname(source_file)
        filename = os.path.basename(source_file)
        name_no_ext, _ = os.path.splitext(filename)
        
        if item.is_sequence:
            name_no_ext = strip_sequence_counter(name_no_ext)
        
        # Determine target directory
        target_dir = base_dir
        if self.thumb_location == "Relative to Source Folder":
            if self.source_folder:
                target_dir = os.path.join(self.source_folder, self.thumb_location_path).replace("\\", "/")
        elif self.thumb_location == "Custom":
            target_dir = self.thumb_location_path.replace("\\", "/")
            
        # Basename with suffix
        target_filename = f"{name_no_ext}{self.thumb_suffix}{self.thumb_format}"
        
        return os.path.join(target_dir, target_filename).replace("\\", "/")

    def _get_prefs_review_path(self, item):
        """Calculate the review path based on preset preferences."""
        rev_fp = getattr(item, "review_file_path", None)
        if rev_fp and os.path.exists(rev_fp):
            return rev_fp

        source_file = item.file_path.replace("\\", "/")
        base_dir = os.path.dirname(source_file)
        filename = os.path.basename(source_file)
        name_no_ext, _ = os.path.splitext(filename)
        
        if item.is_sequence:
            name_no_ext = strip_sequence_counter(name_no_ext)
            
        p_data = item.preset_data or {}
        rev_loc = p_data.get("Review Location", "Relative to Source Folder")
        rev_path = p_data.get("Review Path", "_reviews")
        rev_suffix = p_data.get("Review Suffix", "_review")
        rev_format = p_data.get("Review Format", ".mp4")
        
        # Determine target directory
        target_dir = base_dir
        if rev_loc == "Relative to Source Folder":
            if self.source_folder:
                target_dir = os.path.join(self.source_folder, rev_path).replace("\\", "/")
            else:
                target_dir = os.path.join(base_dir, rev_path).replace("\\", "/")
        elif rev_loc == "Custom":
            target_dir = rev_path.replace("\\", "/")
            
        # Basename with suffix and format
        target_filename = f"{name_no_ext}{rev_suffix}{rev_format}"
        
        # Ensure the path is absolute
        full_path = os.path.join(target_dir, target_filename)
        return os.path.abspath(full_path).replace("\\", "/")
    def perform_rename_to_label(self, selected_paths, version_regex):
        """
        Renames files on disk based on their model label.
        Handles sequences and avoids collisions.
        Returns the number of items (files or sequences) renamed.
        """
        import os
        import re
        from utils import strip_sequence_counter
        
        # 1. Map selected paths to items in our model
        abs_selected = {os.path.normpath(os.path.abspath(p)) for p in selected_paths}
        items_to_rename = []
        seen_items = set()
        
        for item in self.items:
            item_abs = os.path.normpath(os.path.abspath(item.file_path))
            if item_abs in abs_selected and item not in seen_items:
                items_to_rename.append(item)
                seen_items.add(item)
                
        if not items_to_rename:
            return 0

        renamed_count = 0
        
        for item in items_to_rename:
            directory = os.path.dirname(item.file_path)
            orig_filename = os.path.basename(item.file_path)
            base, ext = os.path.splitext(orig_filename)
            
            # Extract version string if present (e.g. _v001)
            ver_match = re.search(version_regex, orig_filename, re.IGNORECASE)
            ver_str = ver_match.group(0) if ver_match else ""
            
            # New base name (label + version)
            new_base_no_counter = item.label + ver_str
            
            # Collect all files belonging to this item
            files_to_move = [] # (old_full, new_full)
            collision = False
            
            if item.is_sequence:
                # Pattern: strip counter and version from original filename
                name_no_ver = re.sub(version_regex, "", orig_filename, flags=re.IGNORECASE)
                pattern_base = strip_sequence_counter(name_no_ver)
                
                # Get all files in directory
                try:
                    all_dir_files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
                except Exception:
                    continue
                
                for f in all_dir_files:
                    f_no_ver = re.sub(version_regex, "", f, flags=re.IGNORECASE)
                    f_pattern_base = strip_sequence_counter(f_no_ver)
                    f_ver_match = re.search(version_regex, f, re.IGNORECASE)
                    f_ver_str = f_ver_match.group(0) if f_ver_match else ""
                    
                    if f_pattern_base == pattern_base and f_ver_str == ver_str and f.lower().endswith(ext.lower()):
                        # It's part of the sequence.
                        f_base, f_ext = os.path.splitext(f)
                        counter_match = re.search(r"([._]?)(\d+)$", f_base)
                        sep = ""
                        counter = ""
                        if counter_match:
                            sep = counter_match.group(1)
                            counter = counter_match.group(2)
                        
                        new_name = new_base_no_counter + sep + counter + f_ext
                        old_full = os.path.join(directory, f)
                        new_full = os.path.join(directory, new_name)
                        
                        if os.path.exists(new_full) and old_full != new_full:
                            collision = True
                            break
                        files_to_move.append((old_full, new_full))
            else:
                # Single file
                new_name = new_base_no_counter + ext
                old_full = os.path.normpath(os.path.abspath(item.file_path))
                new_full = os.path.join(directory, new_name)
                
                if os.path.exists(new_full) and old_full != new_full:
                    collision = True
                else:
                    files_to_move.append((old_full, new_full))
                    
            if not collision and files_to_move:
                success = True
                for old_p, new_p in files_to_move:
                    try:
                        if old_p == new_p: continue
                        os.rename(old_p, new_p)
                        # If this was the representative file_path, update it
                        if old_p == os.path.normpath(os.path.abspath(item.file_path)):
                            item.file_path = new_p
                            item.filename = os.path.basename(new_p)
                    except Exception as e:
                        print(f"Failed to rename {old_p} -> {new_p}: {e}")
                        success = False
                
                if success:
                    renamed_count += 1

        if renamed_count > 0:
            self.layoutChanged.emit()
            
        return renamed_count
