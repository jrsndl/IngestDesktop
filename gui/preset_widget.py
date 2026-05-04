from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton, QFrame, QLayout)
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Signal, Qt

class PresetWidget(QFrame):
    clicked = Signal(object)
    move_up = Signal(object)
    move_down = Signal(object)

    def __init__(self, preset_type, data=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("PresetWidget")
        self.preset_type = preset_type
        self.is_collapsed = True
        self.is_selected = False
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setObjectName("PresetHeader")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_toggle = QPushButton("▶")
        self.btn_toggle.setFixedSize(20, 20)
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(True)
        self.btn_toggle.clicked.connect(self.toggle_collapsed)
        
        self.lbl_title = QLabel("Preset")
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
        self.header_layout.addWidget(self.lbl_title)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.btn_up)
        self.header_layout.addWidget(self.btn_down)
        
        self.main_layout.addWidget(self.header)

        # Content Container
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 10, 15, 15)
        self.content_layout.setSpacing(8)
        
        # 1. Name
        self.name = QLineEdit()
        self.name.textChanged.connect(self._update_title)
        self.add_row("Name:", self.name)
        
        # 2. Filter By
        self.filter_by = QComboBox()
        self.filter_by.addItems(["Extension", "Name", "Path", "Label"])
        self.add_row("Filter By:", self.filter_by)
        
        # 3. Filter
        self.filter_str = QLineEdit()
        self.add_row("Filter:", self.filter_str)
        
        # 4. Product Type
        self.product_type = QComboBox()
        if preset_type == "other":
            self.product_type.addItems(["workfile", "camera", "model"])
        else:
            self.product_type.addItems(["render", "plate", "image", "texture", "review"])
        self.add_row("Product Type:", self.product_type)
        
        # 5. Variant
        self.variant = QLineEdit()
        self.add_row("Variant:", self.variant)
        
        # 6. FPS
        self.fps = QDoubleSpinBox()
        self.fps.setRange(0.0, 120.0)
        self.fps.setDecimals(3)
        self.add_row("FPS:", self.fps)
        
        # 7. Handles
        handles_layout = QHBoxLayout()
        self.handle_start = QSpinBox()
        self.handle_start.setRange(-1000, 1000)
        self.handle_end = QSpinBox()
        self.handle_end.setRange(-1000, 1000)
        handles_layout.addWidget(QLabel("Start:"))
        handles_layout.addWidget(self.handle_start)
        handles_layout.addWidget(QLabel("End:"))
        handles_layout.addWidget(self.handle_end)
        self.add_row("Handles:", handles_layout)
        
        # 8. Slate
        self.slate_exists = QCheckBox("Slate Exists")
        self.add_row("", self.slate_exists)

        self.main_layout.addWidget(self.content_widget)
        self.content_widget.hide()

        # Set defaults based on type
        self.set_defaults(data)

    def add_row(self, label_text, widget):
        row_layout = QHBoxLayout()
        if label_text:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(100)
            row_layout.addWidget(lbl)
            
        if isinstance(widget, QLayout):
            row_layout.addLayout(widget)
        else:
            row_layout.addWidget(widget)
            
        self.content_layout.addLayout(row_layout)

    def toggle_collapsed(self):
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.btn_toggle.setText("▶" if self.is_collapsed else "▼")

    def set_selected(self, selected):
        self.is_selected = selected
        self.setProperty("selected", selected)
        # Update style
        self.style().unpolish(self)
        self.style().polish(self)
        self.header.setProperty("selected", selected)
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)

    def mousePressEvent(self, event: QMouseEvent):
        self.clicked.emit(self)
        super().mousePressEvent(event)

    def _update_title(self, text):
        self.lbl_title.setText(text if text else "Untitled Preset")

    def set_defaults(self, data):
        if data:
            self.name.setText(data.get("Name", ""))
            self.filter_by.setCurrentText(data.get("Filter By", "Extension"))
            self.filter_str.setText(data.get("Filter", ""))
            self.product_type.setCurrentText(data.get("Product Type", ""))
            self.variant.setText(data.get("Variant", ""))
            self.fps.setValue(data.get("FPS", 24.0))
            self.handle_start.setValue(data.get("Handle Start", 0))
            self.handle_end.setValue(data.get("Handle End", 0))
            self.slate_exists.setChecked(data.get("Slate Exists", False))
            self._update_title(self.name.text())
            return

        # Hardcoded defaults from user request
        defaults = {
            "stills": {
                "Name": "Image", 
                "Filter By": "Extension",
                "Filter": "png", 
                "Product Type": "image", 
                "Variant": "{label}",
                "FPS": 24.0,
                "Handle Start": 0,
                "Handle End": 0,
                "Slate Exists": False
            },
            "sequences": {
                "Name": "EXRs", 
                "Filter By": "Extension",
                "Filter": "exr", 
                "Product Type": "render", 
                "Variant": "{product_type}{task_name}{label}",
                "FPS": 24.0,
                "Handle Start": 0,
                "Handle End": 0,
                "Slate Exists": False
            },
            "videos": {
                "Name": "Movs", 
                "Filter By": "Extension",
                "Filter": "mov", 
                "Product Type": "render", 
                "Variant": "{label}",
                "FPS": 24.0,
                "Handle Start": 0,
                "Handle End": 0,
                "Slate Exists": False
            },
            "other": {
                "Name": "Nuke Workfiles", 
                "Filter By": "Extension",
                "Filter": "nk", 
                "Product Type": "workfile", 
                "Variant": "{label}",
                "FPS": 24.0,
                "Handle Start": 0,
                "Handle End": 0,
                "Slate Exists": False
            }
        }
        d = defaults.get(self.preset_type, {})
        self.name.setText(d.get("Name", ""))
        self.filter_by.setCurrentText(d.get("Filter By", "Extension"))
        self.filter_str.setText(d.get("Filter", ""))
        self.product_type.setCurrentText(d.get("Product Type", ""))
        self.variant.setText(d.get("Variant", ""))
        self.fps.setValue(d.get("FPS", 24.0))
        self.handle_start.setValue(d.get("Handle Start", 0))
        self.handle_end.setValue(d.get("Handle End", 0))
        self.slate_exists.setChecked(d.get("Slate Exists", False))
        self._update_title(self.name.text())

    def get_data(self):
        return {
            "Name": self.name.text(),
            "Filter By": self.filter_by.currentText(),
            "Filter": self.filter_str.text(),
            "Product Type": self.product_type.currentText(),
            "Variant": self.variant.text(),
            "FPS": self.fps.value(),
            "Handle Start": self.handle_start.value(),
            "Handle End": self.handle_end.value(),
            "Slate Exists": self.slate_exists.isChecked()
        }
