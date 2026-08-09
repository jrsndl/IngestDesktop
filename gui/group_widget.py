from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QCheckBox, QPushButton, QFrame, QGridLayout)
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Signal, Qt

class GroupWidget(QFrame):
    clicked = Signal(object)
    move_up = Signal(object)
    move_down = Signal(object)

    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("GroupWidget")
        self.is_collapsed = False
        self.is_selected = False
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setObjectName("PresetHeader")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_toggle = QPushButton("▼")
        self.btn_toggle.setFixedSize(20, 20)
        self.btn_toggle.clicked.connect(self.toggle_collapsed)

        self.enabled = QCheckBox("Enable")
        self.enabled.setChecked(True)
        
        self.lbl_title = QLabel("Group Definition")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.btn_up = QPushButton("▲")
        self.btn_up.setFixedSize(20, 20)
        self.btn_up.setToolTip("Move Up (Increase Priority)")
        self.btn_up.setStyleSheet("QPushButton { min-height: 0px; padding: 0px; font-size: 10px; }")
        self.btn_up.clicked.connect(lambda: self.move_up.emit(self))
        
        self.btn_down = QPushButton("▼")
        self.btn_down.setFixedSize(20, 20)
        self.btn_down.setToolTip("Move Down (Decrease Priority)")
        self.btn_down.setStyleSheet("QPushButton { min-height: 0px; padding: 0px; font-size: 10px; }")
        self.btn_down.clicked.connect(lambda: self.move_down.emit(self))

        self.header_layout.addWidget(self.btn_toggle)
        self.header_layout.addWidget(self.enabled)
        self.header_layout.addWidget(self.lbl_title)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.btn_up)
        self.header_layout.addWidget(self.btn_down)
        
        self.main_layout.addWidget(self.header)

        # Content Container
        self.content_widget = QWidget()
        self.grid_layout = QGridLayout(self.content_widget)
        self.grid_layout.setContentsMargins(15, 10, 15, 15)
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(6)

        # Row 0: Group Name
        self.name = QLineEdit()
        self.name.textChanged.connect(self._update_title)
        self.add_to_grid(0, 0, "Group Name:", self.name, span=2)

        # Row 1: Task Type(s), Task Name(s)
        self.task_types = QLineEdit()
        self.add_to_grid(1, 0, "Task Type(s):", self.task_types)
        self.task_names = QLineEdit()
        self.add_to_grid(1, 1, "Task Name(s):", self.task_names)

        # Row 2: Always Repres, Always or Convert Repres
        self.always_repres = QLineEdit()
        self.add_to_grid(2, 0, "Always Repres:", self.always_repres)
        self.always_or_convert_repres = QLineEdit()
        self.add_to_grid(2, 1, "Always/Convert Repres:", self.always_or_convert_repres)

        # Row 3: Optional Repres, Inheritance Priority
        self.optional_repres = QLineEdit()
        self.add_to_grid(3, 0, "Optional Repres:", self.optional_repres)
        self.inheritance_priority = QLineEdit()
        self.add_to_grid(3, 1, "Inheritance Repre Priority:", self.inheritance_priority)

        # Row 4: Review Repre, Thumbnail Source Repre
        self.review_repre = QLineEdit()
        self.add_to_grid(4, 0, "Review Repre:", self.review_repre)
        self.thumb_source_repre = QLineEdit()
        self.add_to_grid(4, 1, "Thumbnail Source Repre:", self.thumb_source_repre)

        # Row 5: Inherit Columns
        self.inherit_columns = QLineEdit()
        self.add_to_grid(5, 0, "Inherit Columns:", self.inherit_columns, span=2)

        self.main_layout.addWidget(self.content_widget)

        self.set_defaults(data)

    def add_to_grid(self, row, col, label_text, widget, span=1):
        col_idx = col * 2
        lbl = QLabel(label_text)
        lbl.setFixedWidth(160)
        self.grid_layout.addWidget(lbl, row, col_idx)
        self.grid_layout.addWidget(widget, row, col_idx + 1, 1, span * 2 - 1)

    def toggle_collapsed(self):
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.btn_toggle.setText("▶" if self.is_collapsed else "▼")

    def set_selected(self, selected):
        self.is_selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.header.setProperty("selected", selected)
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)

    def mousePressEvent(self, event: QMouseEvent):
        self.clicked.emit(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.header.geometry().contains(event.pos()):
            self.toggle_collapsed()
        super().mouseDoubleClickEvent(event)

    def _update_title(self, text):
        self.lbl_title.setText(text if text else "Untitled Group")

    def set_defaults(self, data):
        if data:
            self.name.setText(data.get("name", ""))
            self.enabled.setChecked(data.get("enabled", True))
            self.task_types.setText(data.get("task_types", ""))
            self.task_names.setText(data.get("task_names", ""))
            self.always_repres.setText(data.get("always_repres", ""))
            self.always_or_convert_repres.setText(data.get("always_or_convert_repres", ""))
            self.optional_repres.setText(data.get("optional_repres", ""))
            self.inheritance_priority.setText(data.get("inheritance_repre_priority", data.get("inheritance_priority", "")))
            self.review_repre.setText(data.get("review_repre", ""))
            self.thumb_source_repre.setText(data.get("thumb_source_repre", ""))
            self.inherit_columns.setText(data.get("inherit_columns", ""))
            self._update_title(self.name.text())
        else:
            self.name.setText("Group 1")
            self.enabled.setChecked(True)
            self._update_title("Group 1")

    def get_data(self):
        return {
            "name": self.name.text().strip(),
            "enabled": self.enabled.isChecked(),
            "task_types": self.task_types.text().strip(),
            "task_names": self.task_names.text().strip(),
            "always_repres": self.always_repres.text().strip(),
            "always_or_convert_repres": self.always_or_convert_repres.text().strip(),
            "optional_repres": self.optional_repres.text().strip(),
            "inheritance_repre_priority": self.inheritance_priority.text().strip(),
            "review_repre": self.review_repre.text().strip(),
            "thumb_source_repre": self.thumb_source_repre.text().strip(),
            "inherit_columns": self.inherit_columns.text().strip()
        }
