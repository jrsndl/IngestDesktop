import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog, QLineEdit, QCheckBox
from PySide6.QtCore import Signal

class TopBar(QWidget):
    folder_selected = Signal(str)
    prefs_requested = Signal()
    rescan_requested = Signal()
    reveal_requested = Signal()
    show_reviews_toggled = Signal(bool)
    load_preset_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(50)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)

        # Source Folder Button
        self.btn_folder = QPushButton("Select Source Folder")
        self.btn_folder.clicked.connect(self._on_select_folder)
        
        # Path Display
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setPlaceholderText("No source folder selected")
        self.path_display.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        
        # Recursive Checkbox
        self.chk_recursive = QCheckBox("Recursive")
        self.chk_recursive.setChecked(True)
        
        self.layout.addWidget(self.btn_folder)
        self.layout.addWidget(self.path_display)
        self.layout.addWidget(self.chk_recursive)
        
        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.clicked.connect(self.rescan_requested.emit)
        self.layout.addWidget(self.btn_rescan)
        
        self.btn_reveal = QPushButton("Reveal in Filesystem")
        self.btn_reveal.clicked.connect(self.reveal_requested.emit)
        self.layout.addWidget(self.btn_reveal)

        self.btn_show_reviews = QPushButton("Show Reviews")
        self.btn_show_reviews.setCheckable(True)
        self.btn_show_reviews.setChecked(True)
        self.btn_show_reviews.toggled.connect(self.show_reviews_toggled.emit)
        self.layout.addWidget(self.btn_show_reviews)
        
        self.layout.addStretch()
        
        # Preset Selection
        self.lbl_preset = QLabel("Preset:")
        self.combo_preset = QComboBox()
        self.combo_preset.setMinimumWidth(150)
        self.combo_preset.textActivated.connect(self.load_preset_requested.emit)
        
        self.btn_load_preset = QPushButton("Load Preset")
        self.btn_load_preset.clicked.connect(self._on_load_preset_clicked)
        
        self.layout.addWidget(self.lbl_preset)
        self.layout.addWidget(self.combo_preset)
        self.layout.addWidget(self.btn_load_preset)
        self.layout.addSpacing(10)
        
        # Preferences Button
        self.btn_prefs = QPushButton("Preferences")
        self.btn_prefs.clicked.connect(self.prefs_requested.emit)
        self.layout.addWidget(self.btn_prefs)


    def set_path(self, path):
        self.path_display.setText(path)

    def _on_select_folder(self):
        current_path = self.path_display.text().strip()
        dir_to_open = ""
        if current_path and os.path.exists(current_path):
            dir_to_open = current_path if os.path.isdir(current_path) else os.path.dirname(current_path)
            
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder", dir_to_open)
        if folder:
            self.folder_selected.emit(folder)

    def _on_load_preset_clicked(self):
        preset = self.combo_preset.currentText()
        self.load_preset_requested.emit(preset)
