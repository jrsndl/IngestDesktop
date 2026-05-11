from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QFormLayout, QSpinBox, QComboBox, QFileDialog, 
                             QTabWidget, QScrollArea, QWidget, QCheckBox, QPlainTextEdit)
from PySide6.QtCore import Qt, Signal
from gui.preset_widget import PresetWidget

class PreferencesDialog(QDialog):
    applied = Signal(dict)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(600, 600)
        self.config = config
        
        self.layout = QVBoxLayout(self)
        
        # Tab Widget
        self.tabs = QTabWidget()
        
        # 1. General Tab (Core backend settings)
        self.general_tab = QWidget()
        self.general_layout = QVBoxLayout(self.general_tab)
        self.form = QFormLayout()
        
        # AYON Settings
        self.server_url = QLineEdit(self.config.get("ayon_server_url", ""))
        self.api_key = QLineEdit(self.config.get("ayon_api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        
        # Scanner Settings
        self.version_regex = QLineEdit(self.config.get("version_regex", r"([._]v|v)(\d+)"))
        self.product_name = QLineEdit(self.config.get("product_name", "{label}"))
        self.product_name_camel = QCheckBox("camelCase")
        self.product_name_camel.setChecked(self.config.get("product_name_camel", True))
        
        self.age_source = QComboBox()
        self.age_source.addItems(["Modification Date", "Creation Date"])
        current_source = self.config.get("age_source", "Modification Date")
        self.age_source.setCurrentText(current_source)
        
        self.detect_sequences = QCheckBox("Detect Image Sequences")
        self.detect_sequences.setChecked(self.config.get("detect_sequences", True))
        
        self.traypublisher_path = QLineEdit(self.config.get("traypublisher_path", "ayon_console.exe"))
        self.btn_browse_console = QPushButton("Browse...")
        self.btn_browse_console.clicked.connect(self._on_browse_console)
        
        self.console_layout = QHBoxLayout()
        self.console_layout.addWidget(self.traypublisher_path)
        self.console_layout.addWidget(self.btn_browse_console)
        
        self.default_scan_folder = QLineEdit(self.config.get("default_scan_folder", ""))
        self.btn_browse_scan = QPushButton("Browse...")
        self.btn_browse_scan.clicked.connect(self._on_browse_scan_folder)
        
        self.scan_folder_layout = QHBoxLayout()
        self.scan_folder_layout.addWidget(self.default_scan_folder)
        self.scan_folder_layout.addWidget(self.btn_browse_scan)

        self.form.addRow("AYON Server URL:", self.server_url)
        self.form.addRow("AYON API Key:", self.api_key)
        self.form.addRow("Default Scan Folder:", self.scan_folder_layout)
        self.form.addRow("Version Regex:", self.version_regex)
        self.form.addRow("Product Name Template:", self.product_name)
        self.form.addRow("Product Name camelCase:", self.product_name_camel)
        self.form.addRow("Age Calculation Source:", self.age_source)
        self.form.addRow("Sequence Detection:", self.detect_sequences)
        self.form.addRow("AYON Console Path:", self.console_layout)
        
        # Tool Paths
        self.ffmpeg_path = QLineEdit(self.config.get("ffmpeg_path", "ffmpeg.exe"))
        self.btn_browse_ffmpeg = QPushButton("Browse...")
        self.btn_browse_ffmpeg.clicked.connect(lambda: self._on_browse_file(self.ffmpeg_path, "FFmpeg Executable", "Executable Files (*.exe);;All Files (*)"))
        ffmpeg_lay = QHBoxLayout()
        ffmpeg_lay.addWidget(self.ffmpeg_path)
        ffmpeg_lay.addWidget(self.btn_browse_ffmpeg)
        self.form.addRow("FFmpeg Path:", ffmpeg_lay)

        self.ffprobe_path = QLineEdit(self.config.get("ffprobe_path", "ffprobe.exe"))
        self.btn_browse_ffprobe = QPushButton("Browse...")
        self.btn_browse_ffprobe.clicked.connect(lambda: self._on_browse_file(self.ffprobe_path, "FFprobe Executable", "Executable Files (*.exe);;All Files (*)"))
        ffprobe_lay = QHBoxLayout()
        ffprobe_lay.addWidget(self.ffprobe_path)
        ffprobe_lay.addWidget(self.btn_browse_ffprobe)
        self.form.addRow("FFprobe Path:", ffprobe_lay)

        self.oiiotool_path = QLineEdit(self.config.get("oiiotool_path", "oiiotool.exe"))
        self.btn_browse_oiio = QPushButton("Browse...")
        self.btn_browse_oiio.clicked.connect(lambda: self._on_browse_file(self.oiiotool_path, "OIIOTool Executable", "Executable Files (*.exe);;All Files (*)"))
        oiio_lay = QHBoxLayout()
        oiio_lay.addWidget(self.oiiotool_path)
        oiio_lay.addWidget(self.btn_browse_oiio)
        self.form.addRow("OIIOTool Path:", oiio_lay)

        self.ocio_config = QLineEdit(self.config.get("ocio_config", ""))
        self.btn_browse_ocio = QPushButton("Browse...")
        self.btn_browse_ocio.clicked.connect(lambda: self._on_browse_file(self.ocio_config, "OCIO Config", "OCIO Config (*.ocio);;All Files (*)"))
        ocio_lay = QHBoxLayout()
        ocio_lay.addWidget(self.ocio_config)
        ocio_lay.addWidget(self.btn_browse_ocio)
        self.form.addRow("OCIO Config:", ocio_lay)
        
        self.general_layout.addLayout(self.form)
        self.general_layout.addStretch()
        self.tabs.addTab(self.general_tab, "General")

        # 1.5 CSV Tab (Metadata output settings)
        self.csv_tab = QWidget()
        self.csv_layout = QVBoxLayout(self.csv_tab)
        self.csv_form = QFormLayout()
        
        self.csv_delimiter = QLineEdit(self.config.get("csv_delimiter", ","))
        self.csv_quotechar = QLineEdit(self.config.get("csv_quotechar", '"'))
        
        self.csv_form.addRow("CSV Delimiter:", self.csv_delimiter)
        self.csv_form.addRow("CSV Quote Character:", self.csv_quotechar)
        
        self.csv_layout.addLayout(self.csv_form)
        self.csv_layout.addSpacing(10)
        self.csv_layout.addWidget(QLabel("<b>CSV Columns (Header=Value):</b>"))
        
        self.csv_columns = QPlainTextEdit()
        # Default columns if not set
        default_cols = [
            "File Path={file_path}",
            "AYON Path={ayon_path}",
            "Product Name={product_name}",
            "Variant={variant}",
            "Version={version}"
        ]
        conf_cols = self.config.get("csv_columns", "\n".join(default_cols))
        self.csv_columns.setPlainText(conf_cols)
        self.csv_layout.addWidget(self.csv_columns)
        
        self.csv_layout.addStretch()
        self.tabs.addTab(self.csv_tab, "CSV")

        # 2. GUI Tab (UI and Preview settings)
        self.gui_tab = QWidget()
        self.gui_layout = QVBoxLayout(self.gui_tab)
        self.gui_form = QFormLayout()

        self.default_cols = QSpinBox()
        self.default_cols.setRange(5, 50)
        self.default_cols.setValue(self.config.get("default_columns", 12))

        self.label_regex = QLineEdit(self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$"))
        
        self.seq_thumb_frame = QComboBox()
        self.seq_thumb_frame.addItems(["First", "Second", "Middle"])
        self.seq_thumb_frame.setCurrentText(self.config.get("seq_thumb_frame", "Middle"))

        self.low_res_size = QSpinBox()
        self.low_res_size.setRange(64, 512)
        self.low_res_size.setSuffix(" px")
        self.low_res_size.setValue(self.config.get("low_res_size", 150))

        self.high_res_size = QSpinBox()
        self.high_res_size.setRange(128, 2048)
        self.high_res_size.setSuffix(" px")
        self.high_res_size.setValue(self.config.get("high_res_size", 512))

        self.gui_form.addRow("Default Columns:", self.default_cols)
        self.gui_form.addRow("Allowed Label Characters:", self.label_regex)
        self.gui_form.addRow("Sequence Thumbnail Frame:", self.seq_thumb_frame)
        self.gui_form.addRow("Low-Res Thumbnail Size:", self.low_res_size)
        self.gui_form.addRow("High-Res Thumbnail Size:", self.high_res_size)

        self.gui_layout.addLayout(self.gui_form)
        self.gui_layout.addStretch()
        self.tabs.addTab(self.gui_tab, "GUI")

        # Preset Tabs
        self.preset_containers = {} # type -> (layout, list_of_widgets)
        
        for p_type, label in [("stills", "Stills"), 
                              ("sequences", "File Sequences"), 
                              ("videos", "Video Containers"), 
                              ("other", "Other")]:
            tab = QWidget()
            layout = QVBoxLayout(tab)
            
            # Extensions field
            ext_layout = QHBoxLayout()
            ext_label = QLabel("File Extensions (space separated):")
            ext_field = QLineEdit()
            
            # Default extensions if not in config
            default_exts = {
                "stills": ".jpg .jpeg .png .tga .exr .dpx .psd",
                "sequences": ".jpg .jpeg .png .tga .exr .dpx .psd",
                "videos": ".mov .mp4 .mxf",
                "other": ""
            }
            conf_exts = self.config.get("extensions", {}).get(p_type, default_exts.get(p_type, ""))
            ext_field.setText(conf_exts)
            
            ext_layout.addWidget(ext_label)
            ext_layout.addWidget(ext_field)
            layout.addLayout(ext_layout)

            stills_thumb_cb = None
            if p_type == "stills":
                stills_thumb_cb = QCheckBox("Thumbnail same as the file")
                stills_thumb_cb.setChecked(self.config.get("stills_thumb_same", True))
                layout.addWidget(stills_thumb_cb)

            # Default frames for stills/videos
            start_f = None
            end_f = None
            video_tc_cb = None
            if p_type == "stills":
                frame_layout = QHBoxLayout()
                frame_layout.addWidget(QLabel("Default Start Frame:"))
                start_f = QSpinBox()
                start_f.setRange(0, 999999)
                start_f.setValue(self.config.get("stills_start_frame", 1001))
                frame_layout.addWidget(start_f)
                
                frame_layout.addWidget(QLabel("Default End Frame:"))
                end_f = QSpinBox()
                end_f.setRange(0, 999999)
                end_f.setValue(self.config.get("stills_end_frame", 1001))
                frame_layout.addWidget(end_f)
                
                layout.addLayout(frame_layout)
            elif p_type == "videos":
                frame_layout = QHBoxLayout()
                video_tc_cb = QCheckBox("Start Frame from TC")
                video_tc_cb.setChecked(self.config.get("video_start_from_tc", False))
                frame_layout.addWidget(video_tc_cb)
                
                frame_layout.addWidget(QLabel("Default Start Frame:"))
                start_f = QSpinBox()
                start_f.setRange(0, 999999)
                start_f.setValue(self.config.get("video_start_frame", 1001))
                frame_layout.addWidget(start_f)
                
                layout.addLayout(frame_layout)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_content = QWidget()
            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setAlignment(Qt.AlignTop)
            scroll.setWidget(scroll_content)
            
            btn_add = QPushButton(f"Add {label} Preset")
            btn_add.clicked.connect(lambda checked, t=p_type: self.add_preset(t))
            
            btn_delete = QPushButton(f"Delete Selected")
            btn_delete.clicked.connect(lambda checked, t=p_type: self.delete_selected_preset(t))
            
            btn_row = QHBoxLayout()
            btn_row.addWidget(btn_add)
            btn_row.addWidget(btn_delete)
            
            layout.addWidget(scroll)
            layout.addLayout(btn_row)
            
            self.tabs.addTab(tab, label)
            self.preset_containers[p_type] = (scroll_layout, [], None, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb) # (layout, widgets, selected_widget, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb)
            
            # Load existing presets
            existing = self.config.get("presets", {}).get(p_type, [])
            if not existing:
                self.add_preset(p_type) # Add one default if empty
            else:
                for data in existing:
                    self.add_preset(p_type, data)

        self.layout.addWidget(self.tabs)
        
        # Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("IngestButton") # Styled
        self.btn_save.clicked.connect(self.accept)
        
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self._on_apply)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_apply)
        self.btn_layout.addWidget(self.btn_save)
        self.btn_layout.addWidget(self.btn_cancel)
        self.layout.addLayout(self.btn_layout)

    def add_preset(self, p_type, data=None):
        scroll_layout, widgets, _, _, _, _, _, _ = self.preset_containers[p_type]
        pw = PresetWidget(p_type, data)
        pw.clicked.connect(self.select_preset)
        pw.move_up.connect(self.move_preset_up)
        pw.move_down.connect(self.move_preset_down)
        scroll_layout.addWidget(pw)
        widgets.append(pw)
        
        # Select the newly added preset
        self.select_preset(pw)

    def select_preset(self, pw):
        p_type = pw.preset_type
        scroll_layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb = self.preset_containers[p_type]
        
        # Deselect previous
        if selected:
            selected.set_selected(False)
            
        # Select new
        pw.set_selected(True)
        self.preset_containers[p_type] = (scroll_layout, widgets, pw, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb)

    def move_preset_up(self, pw):
        p_type = pw.preset_type
        scroll_layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb = self.preset_containers[p_type]
        idx = widgets.index(pw)
        if idx > 0:
            widgets.pop(idx)
            widgets.insert(idx - 1, pw)
            self._rebuild_preset_layout(p_type)

    def move_preset_down(self, pw):
        p_type = pw.preset_type
        scroll_layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb = self.preset_containers[p_type]
        idx = widgets.index(pw)
        if idx < len(widgets) - 1:
            widgets.pop(idx)
            widgets.insert(idx + 1, pw)
            self._rebuild_preset_layout(p_type)

    def _rebuild_preset_layout(self, p_type):
        scroll_layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb = self.preset_containers[p_type]
        # Remove widgets from layout (without deleting them)
        for i in reversed(range(scroll_layout.count())):
            item = scroll_layout.itemAt(i)
            if item.widget():
                scroll_layout.removeWidget(item.widget())
        # Re-add in new order
        for w in widgets:
            scroll_layout.addWidget(w)

    def delete_selected_preset(self, p_type):
        scroll_layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb = self.preset_containers[p_type]
        if not selected:
            return
            
        if selected in widgets:
            widgets.remove(selected)
            selected.setParent(None)
            selected.deleteLater()
            self.preset_containers[p_type] = (scroll_layout, widgets, None, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb)
            
            # Select first available if any
            if widgets:
                self.select_preset(widgets[0])

    def remove_preset(self, pw):
        # This method is no longer used by individual widgets, 
        # but kept for compatibility if needed.
        pass

    def _on_browse_console(self):
        self._on_browse_file(self.traypublisher_path, "Select AYON Console Executable", "Executable Files (*.exe);;All Files (*)")

    def _on_browse_file(self, line_edit, title, filter_str):
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)

    def _on_browse_scan_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Default Scan Folder", self.default_scan_folder.text())
        if dir_path:
            self.default_scan_folder.setText(dir_path)

    def _on_apply(self):
        self.applied.emit(self.get_settings())

    def get_settings(self):
        presets = {}
        extensions = {}
        stills_start = 1001
        stills_end = 1001
        video_tc = False
        video_start = 1001
        stills_thumb_same = True
        for p_type, (layout, widgets, selected, ext_field, start_f, end_f, video_tc_cb, stills_thumb_cb) in self.preset_containers.items():
            p_data = []
            for pw in widgets:
                data = pw.get_data()
                data["Active"] = (pw == selected)
                p_data.append(data)
            presets[p_type] = p_data
            extensions[p_type] = ext_field.text().strip()
            if p_type == "stills":
                stills_start = start_f.value()
                stills_end = end_f.value()
            elif p_type == "videos":
                video_tc = video_tc_cb.isChecked()
                video_start = start_f.value()
            
            if p_type == "stills" and stills_thumb_cb:
                stills_thumb_same = stills_thumb_cb.isChecked()

        return {
            "ayon_server_url": self.server_url.text(),
            "ayon_api_key": self.api_key.text(),
            "version_regex": self.version_regex.text(),
            "default_columns": self.default_cols.value(),
            "age_source": self.age_source.currentText(),
            "label_allowed_chars": self.label_regex.text(),
            "detect_sequences": self.detect_sequences.isChecked(),
            "seq_thumb_frame": self.seq_thumb_frame.currentText(),
            "traypublisher_path": self.traypublisher_path.text(),
            "default_scan_folder": self.default_scan_folder.text(),
            "product_name": self.product_name.text(),
            "product_name_camel": self.product_name_camel.isChecked(),
            "csv_delimiter": self.csv_delimiter.text(),
            "csv_quotechar": self.csv_quotechar.text(),
            "csv_columns": self.csv_columns.toPlainText(),
            "low_res_size": self.low_res_size.value(),
            "high_res_size": self.high_res_size.value(),
            "presets": presets,
            "extensions": extensions,
            "stills_start_frame": stills_start,
            "stills_end_frame": stills_end,
            "video_start_from_tc": video_tc,
            "video_start_frame": video_start,
            "stills_thumb_same": stills_thumb_same,
            "ffmpeg_path": self.ffmpeg_path.text(),
            "ffprobe_path": self.ffprobe_path.text(),
            "oiiotool_path": self.oiiotool_path.text(),
            "ocio_config": self.ocio_config.text()
        }
