from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog, QLineEdit
from PySide6.QtCore import Signal

class TopBar(QWidget):
    folder_selected = Signal(str)
    prefs_requested = Signal()
    rescan_requested = Signal()
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
        
        self.layout.addWidget(self.btn_folder)
        self.layout.addWidget(self.path_display)
        
        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.clicked.connect(self.rescan_requested.emit)
        self.layout.addWidget(self.btn_rescan)
        
        self.layout.addStretch()
        
        # Preset Selection
        self.lbl_preset = QLabel("Preset:")
        self.combo_preset = QComboBox()
        self.combo_preset.setMinimumWidth(150)
        
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
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.folder_selected.emit(folder)

    def _on_load_preset_clicked(self):
        preset = self.combo_preset.currentText()
        self.load_preset_requested.emit(preset)
