from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex

class CSVPreviewModel(QAbstractTableModel):
    def __init__(self, source_model, config, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self.config = config
        self.column_defs = [] # list of (header, value_template)
        self.tagged_items = []
        self.refresh_config(config)
        
        # Connect to source model changes
        self.source_model.dataChanged.connect(self._refresh_data)
        self.source_model.layoutChanged.connect(self._refresh_data)
        self.source_model.modelReset.connect(self._refresh_data)

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
        
        self.tagged_items = [item for item in self.source_model.items if item.is_tagged]
        self.endResetModel()

    def _refresh_data(self):
        self.beginResetModel()
        self.tagged_items = [item for item in self.source_model.items if item.is_tagged]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.tagged_items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.column_defs) + 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        col = index.column()
        row = index.row()
        item = self.tagged_items[row]

        if role == Qt.DecorationRole:
            if col == 0:
                return item.thumbnail
            return None

        if role == Qt.DisplayRole:
            if col == 0:
                return None
            
            csv_col = col - 1
            if csv_col < len(self.column_defs):
                header, template = self.column_defs[csv_col]
                return self.source_model._expand_string(template, item, use_global_camel=True)
        
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return "Thumbnail"
            csv_col = section - 1
            if csv_col < len(self.column_defs):
                return self.column_defs[csv_col][0]
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable # Read only
