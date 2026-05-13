from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QFormLayout, QSpinBox, QComboBox, QFileDialog, 
                             QTabWidget, QScrollArea, QWidget, QCheckBox, QPlainTextEdit,
                             QRadioButton, QButtonGroup)
from PySide6.QtCore import Qt, Signal
from gui.preset_widget import PresetWidget

class PreferencesDialog(QDialog):
    applied = Signal(object)
    
    def __init__(self, config, secrets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(600, 600)
        self.config = config
        self.secrets = secrets
        
        self.layout = QVBoxLayout(self)
        
        # Tab Widget
        self.tabs = QTabWidget()
        
        # 1. General Tab (Core backend settings)
        self.general_tab = QWidget()
        self.general_layout = QVBoxLayout(self.general_tab)
        self.form = QFormLayout()
        
        # AYON Settings
        self.server_url = QLineEdit(self.config.get("ayon_server_url", ""))
        
        # Scanner Settings
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

        self.form.addRow("Default Scan Folder:", self.scan_folder_layout)
        self.form.addRow("Age Calculation Source:", self.age_source)
        self.form.addRow("Sequence Detection:", self.detect_sequences)
        
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

        # Version Collision settings
        self.ver_collision_fail = QRadioButton("fail on existing")
        self.ver_collision_lowest = QRadioButton("set to lowest available")
        self.ver_collision_group = QButtonGroup(self)
        self.ver_collision_group.addButton(self.ver_collision_fail)
        self.ver_collision_group.addButton(self.ver_collision_lowest)
        
        ver_collision_layout = QHBoxLayout()
        ver_collision_layout.addWidget(self.ver_collision_fail)
        ver_collision_layout.addWidget(self.ver_collision_lowest)
        
        # Load from config
        ver_collision_pref = self.config.get("version_collision", "fail")
        if ver_collision_pref == "lowest":
            self.ver_collision_lowest.setChecked(True)
        else:
            self.ver_collision_fail.setChecked(True)
            
        self.form.addRow("Version Collision:", ver_collision_layout)
        
        self.general_layout.addLayout(self.form)
        self.general_layout.addStretch()
        self.tabs.addTab(self.general_tab, "General")

        # 1.2 AYON Tab (New)
        self.ayon_tab = QWidget()
        self.ayon_layout = QVBoxLayout(self.ayon_tab)
        self.ayon_form = QFormLayout()

        # Moved from General
        self.ayon_form.addRow("AYON Server URL:", self.server_url)
        self.ayon_form.addRow("AYON Console Path:", self.console_layout)
        self.ayon_form.addRow("Product Name Template:", self.product_name)
        self.ayon_form.addRow("Product Name camelCase:", self.product_name_camel)

        # New AYON settings
        self.ayon_project_name = QLineEdit(self.config.get("ayon_project_name", ""))
        self.csv_ingest_folder = QLineEdit(self.config.get("ayon_csv_ingest_folder", "/edit/csvingest"))
        self.csv_ingest_task = QLineEdit(self.config.get("ayon_csv_ingest_task", "csvingest"))
        self.csv_preset = QLineEdit(self.config.get("ayon_csv_preset", "Default"))
        self.ignore_validators = QCheckBox("Ignore Validators")
        self.ignore_validators.setChecked(self.config.get("ayon_ignore_validators", True))

        self.ayon_form.addRow("Project {ayon_project_name}:", self.ayon_project_name)
        self.ayon_form.addRow("CSV Ingest Folder:", self.csv_ingest_folder)
        self.ayon_form.addRow("CSV Ingest Task:", self.csv_ingest_task)
        self.ayon_form.addRow("CSV Preset:", self.csv_preset)
        self.ayon_form.addRow(self.ignore_validators)

        self.ayon_layout.addLayout(self.ayon_form)
        self.ayon_layout.addStretch()
        self.tabs.addTab(self.ayon_tab, "AYON")

        # 1.5 Auto-Assign Tab (Moved next to General)
        self.auto_assign_tab = QWidget()
        self.auto_assign_layout = QVBoxLayout(self.auto_assign_tab)
        self.auto_assign_form = QFormLayout()

        self.auto_assign_multi_match = QCheckBox("Assign first match if more than one leaf folder name matches")
        self.auto_assign_multi_match.setChecked(self.config.get("auto_assign_multi_match", False))

        self.auto_assign_fallback_task = QCheckBox("Assign first task if folder match is found, but task match is not")
        self.auto_assign_fallback_task.setChecked(self.config.get("auto_assign_fallback_task", False))

        # Regex fields
        self.version_regex = QLineEdit(self.config.get("version_regex", r"([._]v|v)(\d+)"))
        self.folder_regex = QLineEdit(self.config.get("folder_regex", r"^([^_]*_[^_]*)_.*$"))
        self.task_regex = QLineEdit(self.config.get("task_regex", r"^[^_]*_[^_]*_([^_]*).*$"))
        self.sequence_regex = QLineEdit(self.config.get("sequence_regex", r"^[^_]*_([^_]*)_[^_]*.*$"))
        self.episode_regex = QLineEdit(self.config.get("episode_regex", r"^[^_]*_([^_]*)_[^_]*.*$"))

        self.auto_assign_form.addRow("Version Regex:", self.version_regex)
        self.auto_assign_form.addRow("Folder Regex {folder_name}:", self.folder_regex)
        self.auto_assign_form.addRow("Task Regex {task_name}:", self.task_regex)
        self.auto_assign_form.addRow("Sequence Regex {sequence}:", self.sequence_regex)
        self.auto_assign_form.addRow("Episode Regex {episode}:", self.episode_regex)
        
        self.auto_assign_form.addRow(self.auto_assign_multi_match)
        self.auto_assign_form.addRow(self.auto_assign_fallback_task)

        self.auto_assign_layout.addLayout(self.auto_assign_form)
        self.auto_assign_layout.addStretch()
        self.tabs.addTab(self.auto_assign_tab, "Auto-Assign")

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
        self.csv_layout.addWidget(self.csv_columns, 1) # Add stretch factor 1 to expand
        
        self.tabs.addTab(self.csv_tab, "CSV")

        # 1.6 Thumbs Tab (New)
        self.thumbs_tab = QWidget()
        self.thumbs_layout = QVBoxLayout(self.thumbs_tab)
        self.thumbs_form = QFormLayout()

        # Moved from GUI tab
        self.seq_thumb_frame = QComboBox()
        self.seq_thumb_frame.addItems(["First", "Second", "Middle"])
        self.seq_thumb_frame.setCurrentText(self.config.get("seq_thumb_frame", "Middle"))

        self.high_res_size = QSpinBox()
        self.high_res_size.setRange(128, 2048)
        self.high_res_size.setSuffix(" px")
        # Try thumb_size first, then high_res_size as fallback
        val = self.config.get("thumb_size", self.config.get("high_res_size", 512))
        self.high_res_size.setValue(val)

        # New Thumbnail settings
        self.thumb_location = QComboBox()
        self.thumb_location.addItems(["Same as File", "Relative to Source Folder", "Custom"])
        self.thumb_location.setCurrentText(self.config.get("thumb_location", "Relative to Source Folder"))

        self.thumb_location_path = QLineEdit(self.config.get("thumb_location_path", "_thumbs"))
        self.thumb_location.currentTextChanged.connect(self._on_thumb_location_changed)

        self.thumb_suffix = QLineEdit(self.config.get("thumb_suffix", "_thumbnail"))
        
        self.thumb_format = QComboBox()
        self.thumb_format.addItems([".jpg", ".png"])
        self.thumb_format.setCurrentText(self.config.get("thumb_format", ".jpg"))

        from PySide6.QtWidgets import QSlider
        self.thumb_quality = QSlider(Qt.Horizontal)
        self.thumb_quality.setRange(0, 100)
        self.thumb_quality.setValue(self.config.get("thumb_quality", 80))
        self.thumb_quality_lbl = QLabel(f"{self.thumb_quality.value()}")
        self.thumb_quality.valueChanged.connect(lambda v: self.thumb_quality_lbl.setText(str(v)))

        quality_lay = QHBoxLayout()
        quality_lay.addWidget(self.thumb_quality)
        quality_lay.addWidget(self.thumb_quality_lbl)

        self.cmd_stills = QPlainTextEdit(self.config.get("cmd_stills", ""))
        self.cmd_stills.setMaximumHeight(50)
        self.cmd_videos = QPlainTextEdit(self.config.get("cmd_videos", ""))
        self.cmd_videos.setMaximumHeight(50)
        self.cmd_sequences = QPlainTextEdit(self.config.get("cmd_sequences", ""))
        self.cmd_sequences.setMaximumHeight(50)

        self.thumbs_form.addRow("Sequence Thumbnail Frame:", self.seq_thumb_frame)
        self.thumbs_form.addRow("High-Res Thumbnail Size:", self.high_res_size)
        self.thumbs_form.addRow("Thumbnail Location:", self.thumb_location)
        self.thumbs_form.addRow("Thumbnail Path:", self.thumb_location_path)
        self.thumbs_form.addRow("Thumbnail Suffix:", self.thumb_suffix)
        self.thumbs_form.addRow("Thumbnail File Format:", self.thumb_format)
        self.thumbs_form.addRow("Thumbnail Quality:", quality_lay)
        self.thumbs_form.addRow("Stills: Thumbnail Command:", self.cmd_stills)
        self.thumbs_form.addRow("Videos: Thumbnail Command:", self.cmd_videos)
        self.thumbs_form.addRow("Sequences: Thumbnail Command:", self.cmd_sequences)

        self.thumbs_layout.addLayout(self.thumbs_form)
        self.thumbs_layout.addStretch()
        self.tabs.addTab(self.thumbs_tab, "Conversions")
        self._on_thumb_location_changed(self.thumb_location.currentText())

        # 1.7 Clipboard Tab
        self.clipboard_tab = QWidget()
        self.clipboard_layout = QVBoxLayout(self.clipboard_tab)
        self.clipboard_form = QFormLayout()
        
        import os
        default_root = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Downloads")
        self.clip_temp_root = QLineEdit(self.config.get("clip_temp_root", default_root))
        self.clip_folder_template = QLineEdit(self.config.get("clip_folder_template", "IngestDesktop_{yy}{mm}{dd}"))
        self.clip_file_prefix = QLineEdit(self.config.get("clip_file_prefix", "clipboard"))
        self.clip_file_counter = QSpinBox()
        self.clip_file_counter.setRange(1, 10)
        self.clip_file_counter.setValue(self.config.get("clip_file_counter", 3))
        
        self.clipboard_form.addRow("Default Temp Root:", self.clip_temp_root)
        self.clipboard_form.addRow("Folder Template:", self.clip_folder_template)
        self.clipboard_form.addRow("File Prefix:", self.clip_file_prefix)
        self.clipboard_form.addRow("Counter Padding:", self.clip_file_counter)
        
        self.clipboard_layout.addLayout(self.clipboard_form)
        self.clipboard_layout.addStretch()
        self.tabs.addTab(self.clipboard_tab, "Clipboard")

        # 2. GUI Tab (UI and Preview settings)
        self.gui_tab = QWidget()
        self.gui_layout = QVBoxLayout(self.gui_tab)
        self.gui_form = QFormLayout()

        self.default_cols = QSpinBox()
        self.default_cols.setRange(5, 100)
        self.default_cols.setValue(self.config.get("default_columns", 12))

        self.default_text_size = QSpinBox()
        self.default_text_size.setRange(4, 64)
        self.default_text_size.setValue(self.config.get("default_text_size", 10))

        self.default_thumb_size = QSpinBox()
        self.default_thumb_size.setRange(20, 1024)
        self.default_thumb_size.setSuffix(" px")
        self.default_thumb_size.setValue(self.config.get("default_thumb_size", 150))

        self.label_regex = QLineEdit(self.config.get("label_allowed_chars", "^[a-zA-Z0-9_\\-\\.\\s]*$"))
        
        self.low_res_size = QSpinBox()
        self.low_res_size.setRange(64, 512)
        self.low_res_size.setSuffix(" px")
        self.low_res_size.setValue(self.config.get("low_res_size", 150))

        self.gui_form.addRow("Default Columns:", self.default_cols)
        self.gui_form.addRow("Default Text Size:", self.default_text_size)
        self.gui_form.addRow("Default Thumbnail Size:", self.default_thumb_size)
        self.gui_form.addRow("Allowed Label Characters:", self.label_regex)
        self.gui_form.addRow("Low-Res Thumbnail Size:", self.low_res_size)

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

        # Secrets Tab
        self.secrets_tab = QWidget()
        self.secrets_layout = QVBoxLayout(self.secrets_tab)
        self.secrets_form = QFormLayout()
        
        self.api_key = QLineEdit(self.secrets.get("ayon_api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.secrets_form.addRow("AYON API Key:", self.api_key)

        self.secrets_form.addRow(QLabel("")) # Spacer
        self.secrets_form.addRow(QLabel("<b>Ftrack:</b>"))
        
        self.ftrack_server = QLineEdit(self.secrets.get("ftrack_server", ""))
        self.secrets_form.addRow("Ftrack Server:", self.ftrack_server)
        
        self.ftrack_user = QLineEdit(self.secrets.get("ftrack_api_user", ""))
        self.secrets_form.addRow("Ftrack API User:", self.ftrack_user)
        
        self.ftrack_key = QLineEdit(self.secrets.get("ftrack_api_key", ""))
        self.ftrack_key.setEchoMode(QLineEdit.Password)
        self.secrets_form.addRow("Ftrack API Key:", self.ftrack_key)
        
        self.secrets_layout.addLayout(self.secrets_form)
        self.secrets_layout.addStretch()
        self.tabs.addTab(self.secrets_tab, "Secrets")


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

    def _on_thumb_location_changed(self, text):
        is_custom_or_rel = text in ["Relative to Source Folder", "Custom"]
        self.thumb_location_path.setVisible(is_custom_or_rel)
        # Find the label for this field to hide it too
        label = self.thumbs_form.labelForField(self.thumb_location_path)
        if label:
            label.setVisible(is_custom_or_rel)

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

        new_config = {
            "ayon_server_url": self.server_url.text(),
            "version_regex": self.version_regex.text(),
            "default_columns": self.default_cols.value(),
            "default_text_size": self.default_text_size.value(),
            "default_thumb_size": self.default_thumb_size.value(),
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
            "thumb_size": self.high_res_size.value(),
            "thumb_location": self.thumb_location.currentText(),
            "thumb_location_path": self.thumb_location_path.text(),
            "thumb_suffix": self.thumb_suffix.text(),
            "thumb_format": self.thumb_format.currentText(),
            "thumb_quality": self.thumb_quality.value(),
            "cmd_stills": self.cmd_stills.toPlainText(),
            "cmd_videos": self.cmd_videos.toPlainText(),
            "cmd_sequences": self.cmd_sequences.toPlainText(),
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
            "ocio_config": self.ocio_config.text(),
            "version_collision": "lowest" if self.ver_collision_lowest.isChecked() else "fail",
            "auto_assign_multi_match": self.auto_assign_multi_match.isChecked(),
            "auto_assign_fallback_task": self.auto_assign_fallback_task.isChecked(),
            "folder_regex": self.folder_regex.text(),
            "task_regex": self.task_regex.text(),
            "sequence_regex": self.sequence_regex.text(),
            "episode_regex": self.episode_regex.text(),
            "ayon_project_name": self.ayon_project_name.text(),
            "ayon_csv_ingest_folder": self.csv_ingest_folder.text(),
            "ayon_csv_ingest_task": self.csv_ingest_task.text(),
            "ayon_csv_preset": self.csv_preset.text(),
            "ayon_ignore_validators": self.ignore_validators.isChecked(),
            "clip_temp_root": self.clip_temp_root.text(),
            "clip_folder_template": self.clip_folder_template.text(),
            "clip_file_prefix": self.clip_file_prefix.text(),
            "clip_file_counter": self.clip_file_counter.value()
        }
        new_secrets = {
            "ayon_api_key": self.api_key.text(),
            "ftrack_server": self.ftrack_server.text(),
            "ftrack_api_user": self.ftrack_user.text(),
            "ftrack_api_key": self.ftrack_key.text()
        }
        return new_config, new_secrets
