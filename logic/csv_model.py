import os
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex

class CSVPreviewModel(QAbstractTableModel):
    def __init__(self, source_model, config, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self.config = config
        self.column_defs = [] # list of (header, value_template)
        self.tagged_items = []
        self.is_review_row = [] # list of bools corresponding to tagged_items
        self.refresh_config(config)
        
        # Connect to source model changes
        self.source_model.dataChanged.connect(self._refresh_data)
        self.source_model.layoutChanged.connect(self._refresh_data)
        self.source_model.modelReset.connect(self._refresh_data)
        self.source_model.rowsInserted.connect(self._refresh_data)
        self.source_model.rowsRemoved.connect(self._refresh_data)

    def refresh_config(self, config):
        self.config = config
        conf_str = self.config.get("csv_columns", "")
        self.beginResetModel()
        self.column_defs = []
        for line in conf_str.splitlines():
            if "=" in line:
                header, val = line.split("=", 1)
                self.column_defs.append((header.strip(), val.strip()))
            elif line.strip():
                self.column_defs.append((line.strip(), ""))
        
        self.tagged_items = [item for item in self.source_model.items if item.is_tagged and not getattr(item, "is_ayon_item", False)]
        self.is_review_row = [False] * len(self.tagged_items)
        self.endResetModel()

    def _refresh_data(self):
        self.beginResetModel()
        self.tagged_items = [item for item in self.source_model.items if item.is_tagged and not getattr(item, "is_ayon_item", False)]
        self.is_review_row = [False] * len(self.tagged_items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.tagged_items)

    def columnCount(self, parent=QModelIndex()):
        # Checks (0), Thumbnail (1), + CSV Columns
        return len(self.column_defs) + 2

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        col = index.column()
        row = index.row()
        if row >= len(self.tagged_items): return None
        
        item = self.tagged_items[row]
        is_review = self.is_review_row[row]

        is_colliding = getattr(item, "version_collision", False)
        is_duplicate = getattr(item, "is_duplicate", False)

        if role == Qt.ForegroundRole:
            if is_review:
                from PySide6.QtGui import QColor
                return QColor("#aaaaaa") # dim review row slightly for visual clarity
            if is_colliding:
                csv_col = col - 2 # Offset by 2 for Checks and Thumbnail
                if csv_col >= 0 and csv_col < len(self.column_defs):
                    header, template = self.column_defs[csv_col]
                    if "{version}" in template.lower():
                        from PySide6.QtGui import QColor
                        return QColor("#ff8c00")
            return None

        if role == Qt.BackgroundRole:
            if col == 0 and (is_colliding or is_duplicate) and not is_review:
                from PySide6.QtGui import QColor
                return QColor("#ff8c00")
            if getattr(item, "group_error", False):
                from PySide6.QtGui import QColor
                return QColor("#3e1f1f")
            if getattr(self.source_model, "show_grouped", False):
                g_idx = getattr(item, "group_index", 0)
                if not hasattr(self, "GROUP_DIM_COLORS"):
                    from PySide6.QtGui import QColor
                    self.GROUP_DIM_COLORS = [
                        QColor("#1b2430"),  # Dim Steel Blue
                        QColor("#251c30"),  # Dim Soft Purple
                        QColor("#18292e"),  # Dim Dark Cyan / Teal
                        QColor("#1c213d"),  # Dim Indigo
                        QColor("#241e3d"),  # Dim Blue-Violet
                        QColor("#2b1e2c"),  # Dim Dark Violet
                    ]
                return self.GROUP_DIM_COLORS[g_idx % len(self.GROUP_DIM_COLORS)]
            return None

        if role == Qt.DecorationRole:
            if col == 1:
                if getattr(self.source_model, "show_thumbs", False):
                    ayon_thumb = getattr(item, "ayon_thumbnail", None)
                    if ayon_thumb:
                        return ayon_thumb
                return item.thumbnail
            return None

        if role == Qt.DisplayRole:
            if col == 0:
                if is_review:
                    return "review"
                msgs = []
                if is_colliding: msgs.append("version_collision")
                if is_duplicate: msgs.append("duplicate")
                return " & ".join(msgs)
            
            if col == 1:
                return None
            
            csv_col = col - 2
            if csv_col < len(self.column_defs):
                header, template = self.column_defs[csv_col]
                
                if is_review:
                    header_lower = header.lower()
                    if header_lower == "file path":
                        review_path = self.source_model.expand_tokens("{prefs_review_path}", item)
                        return os.path.abspath(review_path).replace("\\", "/")
                    elif header_lower == "representation":
                        p_data = item.preset_data or {}
                        return p_data.get("Review Representation", "h264")
                    elif header_lower == "representation colorspace":
                        p_data = item.preset_data or {}
                        return p_data.get("Review Colorspace", "Output - sRGB")
                    elif header_lower == "representation tags":
                        p_data = item.preset_data or {}
                        return p_data.get("Review Tags", "passing;ftracreview;webreview")
                
                return self.source_model._expand_string(template, item, use_global_camel=True)
        
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return "Checks"
            if section == 1:
                return "Thumbnail"
            csv_col = section - 2
            if csv_col < len(self.column_defs):
                return self.column_defs[csv_col][0]
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable # Read only
