import os
import re
from utils import strip_sequence_counter, app_dir
from logic import tokens
from logic import paths as item_paths
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QPixmap, QColor

def parse_version_folder(directory, version_regex):
    if not directory:
        return None, None
    base = os.path.basename(directory)
    try:
        match = re.match(r"^(?:" + version_regex + r")$", base, re.IGNORECASE)
    except re.error:
        return None, None
    if match:
        from logic.seqparse import version_from_match
        ver = version_from_match(match)
        if ver is not None:
            return os.path.dirname(directory), ver
    return None, None

# Fields a paired review takes from its main file (logic/pairing.py). While the
# review is paired they are read live from the main file, so any change there -
# cell edit, Replace, AYON assignment, version check, project load - shows on the
# review at once. Writes to a paired review are ignored (the fields are read-only
# on the review); on unpair the review shows its own values again.
INHERITED_FIELDS = ("ayon_path", "variant", "variant_user", "version", "version_user",
                    "last_ayon_version", "comment", "is_tagged")
# Inherited fields whose writes on a paired review go to the main file instead of
# being ignored: enabling/disabling a review enables/disables the whole pair.
FORWARDED_FIELDS = ("is_tagged",)


def _inherited_field(name):
    own = "_own_" + name
    forward = name in FORWARDED_FIELDS

    def fget(self):
        main = self.__dict__.get("pair_main")
        if main is not None:
            return getattr(main, name)
        return self.__dict__.get(own)

    def fset(self, value):
        main = self.__dict__.get("pair_main")
        if main is not None:
            if forward:
                setattr(main, name, value)
            return  # read-only while paired: edit the main file instead
        self.__dict__[own] = value

    return property(fget, fset, doc=f"{name} (inherited from the main file while paired)")


class ImageItem:
    def __init__(self, file_path, label=None, version=1, category="Other", 
                 preset_name=None, variant=None, product_type=None, camel_case=True,
                 representation=None, colorspace=None, rep_tags=None, is_sequence=False,
                 preset_data=None, frame_start=None, frame_end=None, metadata=None, comment="", variant_user="", version_user="", is_ayon_item=False):
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
        self.has_placed_position = False
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
        self.is_ayon_item = is_ayon_item
        self.model = None
        # Values copied from the AYON folder/task the item is assigned to
        # (wins over parsed values while assigned), and the values parsed from
        # the file name (restored when the assignment is cleared).
        self.ayon_context = {}
        self.parsed_tags = {}

    # -- pairing (review movie <-> main file) ------------------------------
    pair_main = None  # main ImageItem this review is paired to

    @property
    def paired_reviews(self):
        """Review items paired to this main file."""
        return self.__dict__.setdefault("_paired_reviews", [])

    def pair_review(self, review):
        """Pair `review` to this item: it inherits INHERITED_FIELDS live."""
        if review is self or review is None:
            return
        if review.pair_main is not None:
            review.pair_main.unpair_review(review)
        review.pair_main = self
        review.is_review_repre = True
        md = review.metadata
        md["paired_review_of"] = (self.file_path or "").replace("\\", "/")
        md["is_paired_review"] = True
        if review not in self.paired_reviews:
            self.paired_reviews.append(review)
        rp = (review.file_path or "").replace("\\", "/")
        self.metadata["paired_reviews"] = [(r.file_path or "").replace("\\", "/") for r in self.paired_reviews]
        if len(self.paired_reviews) == 1:
            self.review_file_path = rp
            self.metadata["paired_review"] = rp

    def unpair_review(self, review):
        """Undo pair_review: the review shows its own values again."""
        if review in self.paired_reviews:
            self.paired_reviews.remove(review)
        if review.pair_main is self:
            review.pair_main = None
            review.metadata.pop("paired_review_of", None)
            review.metadata.pop("is_paired_review", None)
        rp = (review.file_path or "").replace("\\", "/")
        self.metadata["paired_reviews"] = [(r.file_path or "").replace("\\", "/") for r in self.paired_reviews]
        if not self.metadata["paired_reviews"]:
            self.metadata.pop("paired_reviews", None)
        if (getattr(self, "review_file_path", "") or "").replace("\\", "/") == rp:
            nxt = self.paired_reviews[0].file_path.replace("\\", "/") if self.paired_reviews else ""
            self.review_file_path = nxt
            if nxt:
                self.metadata["paired_review"] = nxt
            else:
                self.metadata.pop("paired_review", None)

    def pair_members(self):
        """The main file and all its paired reviews (just [self] when not paired)."""
        main = self.pair_main if self.pair_main is not None else self
        return [main] + list(main.paired_reviews)

    def own_fields(self):
        """The item's own values of INHERITED_FIELDS (what it shows when not paired)."""
        return {n: self.__dict__.get("_own_" + n) for n in INHERITED_FIELDS}

    def unpair_all(self):
        """Unpair every review of this item, or this review from its main file."""
        if self.pair_main is not None:
            self.pair_main.unpair_review(self)
        for r in list(self.paired_reviews):
            self.unpair_review(r)

    @property
    def is_review(self):
        """A review movie: marked as a review representation, or paired with footage by name."""
        return bool(getattr(self, "is_review_repre", False) or (self.metadata or {}).get("is_paired_review")
                    or (self.metadata or {}).get("paired_review_of"))

    @property
    def is_hidden_paired_review(self):
        """A review movie that was paired by name with footage (logic/pairing.py).
        It stays in the model so it is published with the footage (CSV), but it is
        not shown as its own item in the canvas or the right panel."""
        return bool((self.metadata or {}).get("paired_review_of"))

    AYON_CONTEXT_KEYS = ("folder_path", "folder_name", "folder_type", "folder_status",
                         "folder_description", "task_name", "task_type",
                         "task_description", "task_status")

    def remember_ayon_context(self):
        """Snapshot the AYON values currently written into metadata by an assignment."""
        self.ayon_context = {k: self.metadata.get(k, "") for k in self.AYON_CONTEXT_KEYS
                             if self.metadata.get(k)}

    def clear_ayon_assignment(self):
        """Remove the AYON assignment and fall back to values parsed from the file name."""
        self.ayon_path = ""
        self.ayon_task_name = ""
        self.ayon_task_type = ""
        self.ayon_task_assignee = ""
        self.ayon_context = {}
        if not self.parsed_tags:
            return  # unknown origin (e.g. old project file): leave metadata as it is
        for k in self.AYON_CONTEXT_KEYS:
            if k in self.parsed_tags:
                self.metadata[k] = self.parsed_tags[k]
            else:
                self.metadata.pop(k, None)

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
        if self.pair_main is not None:
            return self.pair_main.effective_variant
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

for _name in INHERITED_FIELDS:
    setattr(ImageItem, _name, _inherited_field(_name))
del _name


def _norm_fp(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p))) if p else ""


def link_pairs_from_metadata(items):
    """Re-link reviews to their main files from metadata["paired_review_of"]
    (after loading a project or adding rescanned items). Returns the number linked."""
    by_path = {}
    ids = {id(it) for it in items}
    for it in items:
        by_path.setdefault(_norm_fp(getattr(it, "file_path", "")), it)
    n = 0
    for it in items:
        md = getattr(it, "metadata", None) or {}
        target = md.get("paired_review_of")
        if not target or (it.pair_main is not None and id(it.pair_main) in ids):
            continue  # not a review, or already linked to an item of this list
        main = by_path.get(_norm_fp(target))
        if main is None or main is it or main.pair_main is not None:
            continue
        main.pair_review(it)
        n += 1
    return n


class ImageTableModel(QAbstractTableModel):
    data_changed = Signal()

    COLUMNS = [
        "Enable", "Thumbnail", "Label", "Variant", "Variant User", "Product Name", "Group By", "Category", "Preset", "Version", 
        "Version User", "Last Version", "Age", "Review", "AYON Path", "Key Value Pairs", "Ingest Status"
    ]

    # Columns a paired review inherits: Variant, Variant User, Version, Version User,
    # Last Version, AYON Path (comment has no column)
    INHERITED_COLUMNS = (3, 4, 9, 10, 11, 14)

    @property
    def all_items(self):
        return self._items

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
        # A paired review shows its main file's values: repaint it when the main row changes
        self.dataChanged.connect(self._refresh_paired_reviews)
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
        self.show_grouped = True
        self.default_fps = 25.0
        self.use_fps_from_metadata = True

    def set_presets(self, presets):
        self.presets = presets
        self.layoutChanged.emit()

    def expand_tokens(self, text, item):
        """Public wrapper for token expansion."""
        return self._expand_string(text, item)

    def _refresh_paired_reviews(self, top_left, bottom_right, roles=None):
        if not self._items:
            return
        last_col = self.columnCount() - 1
        for row in range(max(0, top_left.row()), min(bottom_right.row(), len(self._items) - 1) + 1):
            for review in getattr(self._items[row], "paired_reviews", ()) or ():
                try:
                    r = self._items.index(review)
                except ValueError:
                    continue
                self.dataChanged.emit(self.index(r, 0), self.index(r, last_col))

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
            if col == 2 and item.pair_main is not None:
                return QColor("#ff00ff")  # paired review: magenta label
            
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
                    
            # Ingest status colours must win over the generic dimming below
            if col == 16:
                if item.ingest_status == "OK":
                    return QColor("#4caf50")
                elif item.ingest_status == "Failed":
                    return QColor("#f44336")

            # Dim non-editable text columns (a paired review takes these from its main file)
            if item.pair_main is not None and col in self.INHERITED_COLUMNS:
                return QColor("#888888")
            if col in [3, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16]:
                return QColor("#888888")
            return None

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if col == 2: return item.label
            if col == 3: # Variant (Effective Variant, tokens filled in)
                return self.variant_value(item)
            if col == 4: # Variant User
                return getattr(item, "variant_user", "")
            if col == 5: # Product Name
                return self.product_name(item)
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
                
        elif role == Qt.ToolTipRole:
            template = getattr(self, "tooltip_template", "")
            if template:
                return self.expand_tokens(template, item)
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
            item.is_tagged = (value == Qt.Checked)  # on a paired review: the whole pair
            # Emit for every row of the pair to refresh ForegroundRole color
            for member in item.pair_members():
                try:
                    r = self._items.index(member)
                except ValueError:
                    continue
                self.dataChanged.emit(self.index(r, 0), self.index(r, self.columnCount()-1))
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
            item = self.items[index.row()] if 0 <= index.row() < len(self.items) else None
            if not (item is not None and item.pair_main is not None and index.column() in self.INHERITED_COLUMNS):
                flags |= Qt.ItemIsEditable  # paired review: edit the main file instead
            
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
        if not new_items:
            return  # beginInsertRows(n, n-1) would be an invalid range
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
        self.order_pairs()

    def order_pairs(self):
        """Keep every paired review row directly below its main file (whatever the sort)."""
        ids = {id(it) for it in self._items}
        new, placed = [], set()
        for it in self._items:
            if id(it) in placed:
                continue
            main = getattr(it, "pair_main", None)
            if main is not None and id(main) in ids:
                continue  # placed right after its main file
            new.append(it)
            placed.add(id(it))
            for r in getattr(it, "paired_reviews", None) or []:
                if id(r) in ids and id(r) not in placed:
                    new.append(r)
                    placed.add(id(r))
        for it in self._items:  # safety: never lose a row
            if id(it) not in placed:
                new.append(it)
                placed.add(id(it))
        if all(a is b for a, b in zip(new, self._items)):
            return
        self.layoutAboutToBeChanged.emit()
        old_items = list(self._items)
        persistent = self.persistentIndexList()
        self._items[:] = new
        new_row = {id(it): r for r, it in enumerate(self._items)}
        for idx in persistent:
            if 0 <= idx.row() < len(old_items):
                r = new_row.get(id(old_items[idx.row()]))
                if r is not None:
                    self.changePersistentIndex(idx, self.index(r, idx.column()))
        self.layoutChanged.emit()

    def remove_items(self, items_to_remove):
        if not items_to_remove:
            return
        items_set = set(items_to_remove)
        indices_to_remove = sorted(
            [i for i, item in enumerate(self._items) if item in items_set],
            reverse=True
        )
        if not indices_to_remove:
            return
        # A removed main file releases its reviews; a removed review leaves its main file
        for item in items_to_remove:
            if hasattr(item, "unpair_all"):
                item.unpair_all()

        for idx in indices_to_remove:
            self.beginRemoveRows(QModelIndex(), idx, idx)
            self._items.pop(idx)
            self.endRemoveRows()

        self.rebuild_version_stacks()

    def get_version_stack_key(self, item):
        import os
        import re
        
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
            return (self._stack_dir(item, version_regex), clean_name.lower(), True)
        else:
            # Still / video / other category:
            # 1. remove the version by the regex (entire match)
            clean_name = re.sub(version_regex, "", filename, flags=re.IGNORECASE)
            return (self._stack_dir(item, version_regex), clean_name.lower(), False)

    @staticmethod
    def _stack_dir(item, version_regex):
        """Folder part of a version-stack key: same name in different shot folders must
        not stack, but shot/v001/x.exr and shot/v002/x.exr (version folders) should."""
        d = os.path.dirname(item.file_path or "")
        parent, ver = parse_version_folder(d, version_regex)
        if ver is not None:
            d = parent
        return os.path.normcase(os.path.normpath(d)) if d else ""

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
        done = set()
        for row in rows:
            item = self.items[row]
            root = item.pair_main if item.pair_main is not None else item
            if id(root) in done:
                continue  # a main file and its reviews are toggled together, once
            done.add(id(root))
            root.is_tagged = not root.is_tagged
        
        # Notify views
        if rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.items) - 1, self.columnCount() - 1))

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
                return self.variant_value(item)
            if column == 4: return getattr(item, "variant_user", "") or ""
            if column == 5: return self.product_name(item)
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

        def safe_key(item):
            v = get_value(item)
            if v is None:
                return (2, "")
            if isinstance(v, bool):
                return (0, int(v))
            if isinstance(v, (int, float)):
                return (0, v)
            sv = str(v)
            return (0, int(sv)) if sv.strip().isdigit() else (1, sv.lower())

        reverse = (order == Qt.DescendingOrder)
        # Proper layout change so selections/editors follow their rows
        self.layoutAboutToBeChanged.emit()
        old_items = list(self._items)
        persistent = self.persistentIndexList()
        self._items.sort(key=safe_key, reverse=reverse)
        new_row = {id(it): r for r, it in enumerate(self._items)}
        for idx in persistent:
            if 0 <= idx.row() < len(old_items):
                r = new_row.get(id(old_items[idx.row()]))
                if r is not None:
                    self.changePersistentIndex(idx, self.index(r, idx.column()))
        self.layoutChanged.emit()
        self.order_pairs()  # paired reviews stay right below their main file

    # ------------------------------------------------------------------
    # Token expansion: all logic lives in logic/tokens.py (pure Python).
    # The model only supplies settings (product name template, fps, tool
    # paths, thumbnail/review path rules) through the attributes below.
    # ------------------------------------------------------------------
    @property
    def app_dir(self):
        return app_dir

    def prefs_thumb_path(self, item):
        return self._get_prefs_thumb_path(item)

    def prefs_review_path(self, item):
        return self._get_prefs_review_path(item)

    def product_name(self, item):
        """Final product name (template + CamelCase from Preferences)."""
        return tokens.expand("{product_name}", item, self)

    def variant_value(self, item):
        """Variant with tokens such as {label} or {variant_parsed} filled in."""
        return tokens.expand("{variant}", item, self)

    def _get_replacements(self, item, text="", use_global_camel=False):
        """{"{token}": value} for every known token (kept for older callers/tests)."""
        vals = tokens.all_values(item, self)
        for alias, canonical in tokens.ALIASES.items():
            key = "{" + canonical + "}"
            if key in vals:
                vals["{" + alias + "}"] = vals[key]
        return vals

    def _get_all_tokens_string(self, item):
        """Returns a string listing all key=value pairs for the item."""
        vals = tokens.all_values(item, self)
        pairs = [f"{k}={v}" for k, v in vals.items() if v]
        primary_names = ["folder_name", "task_name", "variant_parsed", "sequence", "episode"]
        for mk, mv in (item.metadata or {}).items():
            if mk not in primary_names:
                pairs.append(f"{{metadata.{mk}}}={mv}")
        return "  ".join(pairs)

    def _expand_string(self, text, item, use_global_camel=False):
        """Expand tokens. use_global_camel=True applies the product-name CamelCase rule;
        otherwise no CamelCase is applied (commands, paths, CSV cells, tooltips)."""
        if not text:
            return ""
        if text == self.product_name_template:
            return self.product_name(item)
        camel = bool(self.product_name_camel) if use_global_camel else False
        return tokens.expand(text, item, self, camel=camel)

    def _get_prefs_thumb_path(self, item):
        """Thumbnail path: an existing thumbnail paired during the scan, else the
        path from preferences (rules shared with the scanner: logic/paths.py)."""
        paired = (item.metadata or {}).get("paired_thumbnail")
        if paired and os.path.isfile(paired):
            return paired
        return item_paths.thumb_path(item.file_path, item.is_sequence, self.source_folder,
                                     self.thumb_location, self.thumb_location_path,
                                     self.thumb_suffix, self.thumb_format)

    def _get_prefs_review_path(self, item):
        """Review path: the paired/found review if it exists, else the preset's target path."""
        rev_fp = getattr(item, "review_file_path", None)
        if rev_fp and os.path.exists(rev_fp):
            return rev_fp
        return item_paths.review_path(item.file_path, item.is_sequence, self.source_folder,
                                      item.preset_data)

    def perform_rename_to_label(self, selected_paths, version_regex):
        """
        Renames files on disk based on their model label.
        Handles sequences and avoids collisions.
        Returns the number of items (files or sequences) renamed.
        """
        import os
        import re
        
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


AGE_UNIT_MINUTES = {"minutes": 1, "hours": 60, "days": 1440}


def age_limit_minutes(value, units):
    """Age filter limit: a file passes when its age (whole minutes) is below this.

    "2 hours" = younger than 120 minutes. (It used to add one unit, so "1 day" let
    through files up to 2 days old.)"""
    return max(0, int(value)) * AGE_UNIT_MINUTES.get(units, 1)
