from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton, QFrame, QLayout,
                             QPlainTextEdit, QGridLayout)
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
        self.content_layout = QGridLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 10, 15, 15)
        self.content_layout.setHorizontalSpacing(10)
        self.content_layout.setVerticalSpacing(6)
        self.content_layout.setColumnStretch(1, 1)
        self.content_layout.setColumnStretch(3, 1)
        self.content_layout.setColumnStretch(5, 1)
        self.grid_layout = self.content_layout

        # Row 0: Name, Filter By, Filter
        self.name = QLineEdit()
        self.name.textChanged.connect(self._update_title)
        self.add_to_grid(0, 0, "Name:", self.name)
        self.filter_by = QComboBox()
        self.filter_by.addItems(["Extension", "Name", "Path", "Label"])
        self.add_to_grid(0, 1, "Filter By:", self.filter_by)
        self.filter_str = QLineEdit()
        self.add_to_grid(0, 2, "Filter:", self.filter_str)

        # Row 1: Product Type, Variant, camelCase
        self.product_type = QComboBox()
        if preset_type == "other":
            self.product_type.addItems(["workfile", "camera", "model"])
        else:
            self.product_type.addItems(["render", "plate", "image", "texture", "review"])
        self.add_to_grid(1, 0, "Product Type:", self.product_type)
        self.variant = QLineEdit()
        self.add_to_grid(1, 1, "Variant:", self.variant)
        self.camel_case = QCheckBox("CamelCase")
        self.camel_case.setChecked(True)
        self.add_to_grid(1, 2, "", self.camel_case)
        
        # Row 2: FPS, from metadata, Slate Exists
        self.fps = QDoubleSpinBox()
        self.fps.setRange(0.0, 120.0)
        self.fps.setDecimals(3)
        self.add_to_grid(2, 0, "FPS:", self.fps)
        self.fps_from_metadata = QCheckBox("from metadata")
        self.fps_from_metadata.setChecked(True)
        self.add_to_grid(2, 1, "", self.fps_from_metadata)
        self.slate_exists = QCheckBox("Slate Exists")
        self.add_to_grid(2, 2, "", self.slate_exists)
        
        # Row 3: Handle Start, Handle End
        self.handle_start = QSpinBox()
        self.handle_start.setRange(-1000, 1000)
        self.add_to_grid(3, 0, "Handle Start:", self.handle_start)
        self.handle_end = QSpinBox()
        self.handle_end.setRange(-1000, 1000)
        self.add_to_grid(3, 1, "Handle End:", self.handle_end)

        # Row 4: Repre, Rep. Tags, Colorspace
        self.representation = QLineEdit()
        self.add_to_grid(4, 0, "Repre:", self.representation)
        self.rep_tags = QLineEdit()
        self.add_to_grid(4, 1, "Rep. Tags:", self.rep_tags)
        self.colorspace = QLineEdit()
        self.add_to_grid(4, 2, "Colorspace:", self.colorspace)

        # Row 5: Divider
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        self.grid_layout.addWidget(line1, 5, 0, 1, 6)

        # Row 6: convert thumbnail, override command
        self.convert_thumb = QCheckBox("Convert Thumbnail")
        self.convert_thumb.setChecked(True)
        self.add_to_grid(6, 0, "", self.convert_thumb)
        self.convert_thumb_override = QCheckBox("Override Command")
        self.convert_thumb_override.setChecked(False)
        self.add_to_grid(6, 1, "", self.convert_thumb_override)

        # Row 7: Thumb Cmd (Full width)
        self.convert_thumb_cmd = QPlainTextEdit()
        self.convert_thumb_cmd.setMaximumHeight(50)
        self.add_to_grid(7, 0, "Thumb Cmd:", self.convert_thumb_cmd, span=3)

        # Row 8: Divider
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        self.grid_layout.addWidget(line2, 8, 0, 1, 6)

        # Row 9: Convert Review, Review Loc., Rev. Path
        self.convert_review = QCheckBox("Convert Review")
        self.convert_review.setChecked(True)
        self.add_to_grid(9, 0, "", self.convert_review)
        self.review_location = QComboBox()
        self.review_location.addItems(["Same as File", "Relative to Source Folder", "Custom"])
        self.review_location.setCurrentText("Relative to Source Folder")
        self.add_to_grid(9, 1, "Review Loc:", self.review_location)
        self.review_path = QLineEdit("_reviews")
        self.add_to_grid(9, 2, "Rev. Path:", self.review_path)

        # Row 10: Rev. Suffix, Rev. Format, Rev. Repre
        self.review_suffix = QLineEdit("_review")
        self.add_to_grid(10, 0, "Rev. Suffix:", self.review_suffix)
        self.review_format = QLineEdit(".mp4")
        self.add_to_grid(10, 1, "Rev. Format:", self.review_format)
        self.review_representation = QLineEdit("h264")
        self.add_to_grid(10, 2, "Rev. Repre:", self.review_representation)

        # Row 11: Rev. Colorspace, Rev. Tags
        self.review_colorspace = QLineEdit("Output - sRGB")
        self.add_to_grid(11, 0, "Rev. Color:", self.review_colorspace)
        self.review_rep_tags = QLineEdit("passing;ftracreview;webreview")
        self.add_to_grid(11, 1, "Rev. Tags:", self.review_rep_tags)

        # Row 12: Review Cmd (Full width)
        self.convert_review_cmd = QPlainTextEdit()
        self.convert_review_cmd.setMaximumHeight(50)
        self.add_to_grid(12, 0, "Review Cmd:", self.convert_review_cmd, span=3)

        self.main_layout.addWidget(self.content_widget)
        self.content_widget.hide()

        # Set defaults based on type
        self.set_defaults(data)

    def add_to_grid(self, row, col, label_text, widget, span=1):
        col_idx = col * 2
        if label_text:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(75)
            self.grid_layout.addWidget(lbl, row, col_idx)
            
        if isinstance(widget, QLayout):
            container = QWidget()
            container.setLayout(widget)
            self.grid_layout.addWidget(container, row, col_idx + (1 if label_text else 0), 1, span * 2 - (1 if label_text else 0))
        else:
            self.grid_layout.addWidget(widget, row, col_idx + (1 if label_text else 0), 1, span * 2 - (1 if label_text else 0))

    def add_row(self, label_text, widget):
        # Kept for compatibility if needed, but not used in current grid layout
        pass

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

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Toggle collapsed state if double-clicked on the header
        if self.header.geometry().contains(event.pos()):
            self.toggle_collapsed()
        super().mouseDoubleClickEvent(event)

    def _update_title(self, text):
        self.lbl_title.setText(text if text else "Untitled Preset")

    def set_defaults(self, data):
        if data:
            self.name.setText(data.get("Name", ""))
            self.filter_by.setCurrentText(data.get("Filter By", "Extension"))
            self.filter_str.setText(data.get("Filter", ""))
            self.product_type.setCurrentText(data.get("Product Type", ""))
            self.variant.setText(data.get("Variant", ""))
            self.camel_case.setChecked(data.get("CamelCase", True))
            self.fps.setValue(data.get("FPS", 24.0))
            self.representation.setText(data.get("Representation", "{extension}"))
            self.colorspace.setText(data.get("Colorspace", "sRGB"))
            self.rep_tags.setText(data.get("Tags", "passing"))
            self.handle_start.setValue(data.get("Handle Start", 0))
            self.handle_end.setValue(data.get("Handle End", 0))
            self.slate_exists.setChecked(data.get("Slate Exists", False))
            
            # New fields
            self.fps_from_metadata.setChecked(data.get("FPS From Metadata", True))
            self.convert_thumb.setChecked(data.get("Convert Thumbnail", True))
            self.convert_thumb_override.setChecked(data.get("Convert Thumbnail Override", False))
            self.convert_thumb_cmd.setPlainText(data.get("Convert Thumbnail Command", ""))
            self.convert_review.setChecked(data.get("Convert Review", True))
            self.review_location.setCurrentText(data.get("Review Location", "Relative to Source Folder"))
            self.review_path.setText(data.get("Review Path", "_reviews"))
            self.review_suffix.setText(data.get("Review Suffix", "_review"))
            self.review_format.setText(data.get("Review Format", ".mp4"))
            self.convert_review_cmd.setPlainText(data.get("Convert Review Command", ""))
            self.review_representation.setText(data.get("Review Representation", "h264"))
            self.review_colorspace.setText(data.get("Review Colorspace", "Output - sRGB"))
            self.review_rep_tags.setText(data.get("Review Tags", "passing;ftracreview;webreview"))
            
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
                "CamelCase": True,
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
                "CamelCase": True,
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
                "CamelCase": True,
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
                "CamelCase": True,
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
        self.camel_case.setChecked(d.get("CamelCase", True))
        self.fps.setValue(d.get("FPS", 24.0))
        self.representation.setText(d.get("Representation", "{extension}"))
        self.colorspace.setText(d.get("Colorspace", "sRGB"))
        self.rep_tags.setText(d.get("Tags", "passing"))
        self.handle_start.setValue(d.get("Handle Start", 0))
        self.handle_end.setValue(d.get("Handle End", 0))
        self.slate_exists.setChecked(d.get("Slate Exists", False))
        
        self.review_representation.setText("h264")
        self.review_colorspace.setText("Output - sRGB")
        self.review_rep_tags.setText("passing;ftracreview;webreview")
        
        self._update_title(self.name.text())

    def get_data(self):
        return {
            "Name": self.name.text(),
            "Filter By": self.filter_by.currentText(),
            "Filter": self.filter_str.text(),
            "Product Type": self.product_type.currentText(),
            "Variant": self.variant.text(),
            "CamelCase": self.camel_case.isChecked(),
            "Representation": self.representation.text(),
            "Colorspace": self.colorspace.text(),
            "Tags": self.rep_tags.text(),
            "FPS": self.fps.value(),
            "FPS From Metadata": self.fps_from_metadata.isChecked(),
            "Handle Start": self.handle_start.value(),
            "Handle End": self.handle_end.value(),
            "Slate Exists": self.slate_exists.isChecked(),
            "Convert Thumbnail": self.convert_thumb.isChecked(),
            "Convert Thumbnail Override": self.convert_thumb_override.isChecked(),
            "Convert Thumbnail Command": self.convert_thumb_cmd.toPlainText(),
            "Convert Review": self.convert_review.isChecked(),
            "Review Location": self.review_location.currentText(),
            "Review Path": self.review_path.text(),
            "Review Suffix": self.review_suffix.text(),
            "Review Format": self.review_format.text(),
            "Convert Review Command": self.convert_review_cmd.toPlainText(),
            "Review Representation": self.review_representation.text(),
            "Review Colorspace": self.review_colorspace.text(),
            "Review Tags": self.review_rep_tags.text()
        }
