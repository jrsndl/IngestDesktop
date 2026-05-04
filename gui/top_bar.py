from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog, QLineEdit
from PySide6.QtCore import Signal

class TopBar(QWidget):
    folder_selected = Signal(str)
    project_changed = Signal(str)
    prefs_requested = Signal()
    rescan_requested = Signal()
    help_requested = Signal()

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
        
        # Project Selection
        self.lbl_project = QLabel("Project:")
        self.combo_project = QComboBox()
        self.combo_project.setMinimumWidth(200) # 3x wider than default roughly
        self.combo_project.currentTextChanged.connect(self.project_changed.emit)

        self.layout.addWidget(self.lbl_project)
        self.layout.addWidget(self.combo_project)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.btn_folder)
        self.layout.addWidget(self.path_display)
        
        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.clicked.connect(self.rescan_requested.emit)
        self.layout.addWidget(self.btn_rescan)
        self.layout.addStretch()
        
        # Preferences Button
        self.btn_prefs = QPushButton("Preferences")
        self.btn_prefs.clicked.connect(self.prefs_requested.emit)
        self.layout.addWidget(self.btn_prefs)

        self.btn_help = QPushButton("?")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setToolTip("Keyboard Shortcuts (Help)")
        self.btn_help.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                color: white;
                font-weight: bold;
                border: 1px solid #666666;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)
        self.btn_help.clicked.connect(self.help_requested.emit)
        self.layout.addWidget(self.btn_help)

    def set_path(self, path):
        self.path_display.setText(path)

    def set_projects(self, projects):
        self.combo_project.clear()
        self.combo_project.addItems(projects)

    def _on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.folder_selected.emit(folder)
