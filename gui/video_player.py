import os
import sys
import logging
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QSlider, QLabel, QStackedWidget, QStyle, QSizePolicy, QFrame)
from PySide6.QtCore import Qt, QUrl, QTime, Signal, Slot

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError as e:
    logging.warning(f"QtMultimedia not available in PySide6: {e}")
    MULTIMEDIA_AVAILABLE = False

def is_multimedia_available():
    if not MULTIMEDIA_AVAILABLE:
        return False
    try:
        import json
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                cfg = json.load(f)
                if cfg.get("disable_inline_video", False):
                    return False
    except Exception:
        pass
    return True

logger = logging.getLogger("IngestDesktop.VideoPlayer")


def format_time(ms):
    """Format milliseconds into a MM:SS or HH:MM:SS string."""
    if ms < 0:
        return "00:00"
    seconds = int((ms / 1000) % 60)
    minutes = int((ms / (1000 * 60)) % 60)
    hours = int((ms / (1000 * 60 * 60)) % 24)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class VideoPlayerPanel(QWidget):
    """
    A premium inline video player panel for reviewing MP4 videos.
    Embeds QtMultimedia widgets and falls back elegantly to system media player if missing.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = None
        self.is_playing = False
        
        # Style sheet for premium styling
        self.setStyleSheet("""
            QWidget#PlayerContainer {
                background-color: #0d0d0d;
                border-radius: 6px;
                border: 1px solid #1a1a1a;
            }
            QWidget#PlaceholderWidget {
                background-color: #121212;
                border-radius: 6px;
                border: 1px dashed #2a2a2a;
            }
            QLabel#PlaceholderText {
                color: #666666;
                font-size: 14px;
                font-weight: 500;
            }
            QLabel#PlaceholderTitle {
                color: #999999;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#VideoNameLabel {
                color: #e0e0e0;
                font-size: 13px;
                font-weight: 600;
                background-color: rgba(20, 20, 20, 180);
                padding: 6px 10px;
                border-radius: 4px;
            }
            QPushButton#PlayerButton {
                background-color: transparent;
                color: #cccccc;
                border: none;
                font-size: 15px;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton#PlayerButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
            QPushButton#PlayerButton:pressed {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton#SystemPlayButton {
                background-color: #007acc;
                color: white;
                border: none;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton#SystemPlayButton:hover {
                background-color: #0098ff;
            }
            QPushButton#SystemPlayButton:pressed {
                background-color: #005999;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #262626;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #007acc;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: none;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #0098ff;
                transform: scale(1.2);
            }
            QLabel#TimeLabel {
                color: #aaaaaa;
                font-size: 12px;
                font-family: 'Courier New', monospace;
            }
        """)

        # Main Layout is a Stacked Widget to easily toggle between Placeholder and Active Player
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # 1. Setup Placeholder
        self.setup_placeholder()
        
        # 2. Setup Player (Inline or Fallback)
        if is_multimedia_available():
            self.setup_multimedia_player()
        else:
            self.setup_fallback_player()
            
        self.stacked_widget.setCurrentIndex(0)

    def setup_placeholder(self):
        """Creates the default placeholder screen shown when no video is selected."""
        self.placeholder_widget = QWidget()
        self.placeholder_widget.setObjectName("PlaceholderWidget")
        layout = QVBoxLayout(self.placeholder_widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)
        
        icon_lbl = QLabel("🎬")
        icon_lbl.setStyleSheet("font-size: 48px; color: #444444;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)
        
        title_lbl = QLabel("Media Preview")
        title_lbl.setObjectName("PlaceholderTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)
        
        desc_lbl = QLabel("Select a video file or an item\nwith a converted review to preview")
        desc_lbl.setObjectName("PlaceholderText")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)
        
        self.stacked_widget.addWidget(self.placeholder_widget)

    def setup_multimedia_player(self):
        """Creates the active PySide6 QMediaPlayer player UI."""
        self.player_widget = QWidget()
        self.player_widget.setObjectName("PlayerContainer")
        layout = QVBoxLayout(self.player_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Video Output Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setStyleSheet("background-color: black; border-radius: 4px;")
        
        # Title Overlay
        self.lbl_title = QLabel("No Video Loaded")
        self.lbl_title.setObjectName("VideoNameLabel")
        self.lbl_title.setAlignment(Qt.AlignLeft)
        
        # Bottom Controls
        controls_widget = QFrame()
        controls_widget.setStyleSheet("background-color: #141414; border-radius: 4px; padding: 4px;")
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(6, 6, 6, 6)
        controls_layout.setSpacing(6)
        
        # Row 1: Timeline Slider & Time Counter
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(0, 0, 0, 0)
        
        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.sliderMoved.connect(self.set_position)
        
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setObjectName("TimeLabel")
        self.lbl_time.setAlignment(Qt.AlignCenter)
        
        slider_layout.addWidget(self.timeline_slider, 1)
        slider_layout.addWidget(self.lbl_time)
        controls_layout.addLayout(slider_layout)
        
        # Row 2: Buttons (Play, Pause, Stop, Volume, Fullscreen)
        btns_layout = QHBoxLayout()
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.setSpacing(4)
        
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("PlayerButton")
        self.btn_play.setToolTip("Play")
        self.btn_play.clicked.connect(self.play_video)
        
        self.btn_stop = QPushButton("■")
        self.btn_stop.setObjectName("PlayerButton")
        self.btn_stop.setToolTip("Stop")
        self.btn_stop.clicked.connect(self.stop_video)
        
        # Volume
        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setObjectName("PlayerButton")
        self.btn_mute.setToolTip("Mute/Unmute")
        self.btn_mute.setFixedWidth(40)
        self.btn_mute.clicked.connect(self.toggle_mute)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.sliderMoved.connect(self.set_volume)
        
        # System Launch Button (as fallback/utility)
        self.btn_system_launch = QPushButton("↗ System")
        self.btn_system_launch.setObjectName("PlayerButton")
        self.btn_system_launch.setToolTip("Open in external system player")
        self.btn_system_launch.clicked.connect(self.open_in_system_player)
        
        btns_layout.addWidget(self.btn_play)
        btns_layout.addWidget(self.btn_stop)
        btns_layout.addSpacing(10)
        btns_layout.addWidget(self.btn_mute)
        btns_layout.addWidget(self.volume_slider)
        btns_layout.addStretch()
        btns_layout.addWidget(self.btn_system_launch)
        
        controls_layout.addLayout(btns_layout)
        
        layout.addWidget(self.lbl_title, 0)
        layout.addWidget(self.video_widget, 1)
        layout.addWidget(controls_widget, 0)
        
        self.stacked_widget.addWidget(self.player_widget)
        
        # Instantiate actual QMediaPlayer
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        # Signal Connections
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.errorOccurred.connect(self.on_player_error)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        
        self.audio_output.setVolume(0.7)

    def setup_fallback_player(self):
        """Creates a fallback UI to play video in default Windows player if QtMultimedia fails."""
        self.fallback_widget = QWidget()
        self.fallback_widget.setObjectName("PlayerContainer")
        layout = QVBoxLayout(self.fallback_widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)
        
        icon_lbl = QLabel("🎥")
        icon_lbl.setStyleSheet("font-size: 54px; color: #007acc;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)
        
        self.lbl_fallback_title = QLabel("Video Ready")
        self.lbl_fallback_title.setObjectName("PlaceholderTitle")
        self.lbl_fallback_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_fallback_title)
        
        desc_lbl = QLabel("QtMultimedia extension is not active in this PySide6 installation.\nUse the button below to preview in your default system player.")
        desc_lbl.setObjectName("PlaceholderText")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)
        
        self.btn_fallback_play = QPushButton("▶ Open in System Player")
        self.btn_fallback_play.setObjectName("SystemPlayButton")
        self.btn_fallback_play.clicked.connect(self.open_in_system_player)
        layout.addWidget(self.btn_fallback_play)
        
        self.stacked_widget.addWidget(self.fallback_widget)

    @Slot(str, str)
    def load_video(self, video_path, name=""):
        """Loads and prepares a video file for playing."""
        if not video_path or not os.path.exists(video_path):
            self.clear_video()
            return
            
        self.video_path = video_path
        
        if is_multimedia_available():
            self.stop_video()
            self.lbl_title.setText(name or os.path.basename(video_path))
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.stacked_widget.setCurrentWidget(self.player_widget)
            
            # Start playing automatically for premium responsive feel
            self.play_video()
        else:
            self.lbl_fallback_title.setText(name or os.path.basename(video_path))
            self.stacked_widget.setCurrentWidget(self.fallback_widget)

    def clear_video(self):
        """Clears current active video and returns to placeholder state."""
        self.video_path = None
        if is_multimedia_available():
            self.stop_video()
            self.player.setSource(QUrl())
            self.lbl_title.setText("No Video Loaded")
        self.stacked_widget.setCurrentIndex(0)

    @Slot()
    def play_video(self):
        """Plays or pauses the currently active video."""
        if not is_multimedia_available() or not self.video_path:
            return
            
        if self.is_playing:
            self.player.pause()
            self.btn_play.setText("▶")
            self.btn_play.setToolTip("Play")
            self.is_playing = False
        else:
            self.player.play()
            self.btn_play.setText("❚❚")
            self.btn_play.setToolTip("Pause")
            self.is_playing = True

    @Slot()
    def stop_video(self):
        """Stops video playback and resets playhead to start."""
        if not is_multimedia_available():
            return
        self.player.stop()
        self.btn_play.setText("▶")
        self.btn_play.setToolTip("Play")
        self.is_playing = False
        self.timeline_slider.setValue(0)
        self.lbl_time.setText(f"00:00 / {format_time(self.player.duration())}")

    @Slot()
    def toggle_mute(self):
        """Mutes/unmutes audio output."""
        if not is_multimedia_available():
            return
        muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not muted)
        self.btn_mute.setText("🔇" if not muted else "🔊")

    @Slot(int)
    def set_volume(self, value):
        """Sets playback audio volume (0-100)."""
        if not is_multimedia_available():
            return
        vol = float(value / 100.0)
        self.audio_output.setVolume(vol)
        self.audio_output.setMuted(value == 0)
        self.btn_mute.setText("🔇" if value == 0 else "🔊")

    @Slot(int)
    def set_position(self, position):
        """Seeks to the given millisecond position in the timeline."""
        if not is_multimedia_available():
            return
        self.player.setPosition(position)

    @Slot(int)
    def on_position_changed(self, position):
        """Triggers when playback head moves, updates timeline GUI."""
        if not self.timeline_slider.isSliderDown():
            self.timeline_slider.setValue(position)
        self.lbl_time.setText(f"{format_time(position)} / {format_time(self.player.duration())}")

    @Slot(int)
    def on_duration_changed(self, duration):
        """Triggers when video loads and specifies total length in ms."""
        self.timeline_slider.setRange(0, duration)
        self.lbl_time.setText(f"{format_time(self.player.position())} / {format_time(duration)}")

    @Slot(object)
    def on_playback_state_changed(self, state):
        """Syncs the Play/Pause button with the player's actual state."""
        state_name = str(state)
        if "PlayingState" in state_name or state == 1:
            self.btn_play.setText("❚❚")
            self.btn_play.setToolTip("Pause")
            self.is_playing = True
        else:
            self.btn_play.setText("▶")
            self.btn_play.setToolTip("Play")
            self.is_playing = False

    @Slot(QMediaPlayer.Error, str)
    def on_player_error(self, error, error_string):
        """Handles PySide6 playback issues (e.g. missing decoders) and offers system fallback."""
        logger.error(f"QMediaPlayer Error ({error}): {error_string}")
        
        # If inline playback fails, switch to fallback interface so user isn't stuck
        self.stop_video()
        if hasattr(self, "fallback_widget"):
            self.lbl_fallback_title.setText(self.lbl_title.text() + " (Format Unplayable Inline)")
            self.stacked_widget.setCurrentWidget(self.fallback_widget)

    @Slot()
    def open_in_system_player(self):
        if not self.video_path or not os.path.exists(self.video_path):
            return
            
        try:
            # On Windows, os.startfile opens in system default player
            if sys.platform == "win32":
                os.startfile(self.video_path)
            else:
                import subprocess
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, self.video_path], check=True)
        except Exception as e:
            logger.error(f"Failed to open system default player: {e}")


class VideoPlayerOverlay(QWidget):
    """
    A minimalist, ultra-high-end video overlay that plays video directly
    on top of a thumbnail, with looping enabled and clean interaction.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = None
        self.is_playing = False
        
        # Transparent overlay styling, hidden cursor or minimal controls
        self.setStyleSheet("""
            QWidget {
                background-color: black;
                border-radius: 4px;
            }
            QPushButton#MuteOverlayButton {
                background-color: rgba(20, 20, 20, 180);
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 11px;
                padding: 4px;
            }
            QPushButton#MuteOverlayButton:hover {
                background-color: rgba(0, 122, 204, 200);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if is_multimedia_available():
            self.video_widget = QVideoWidget(self)
            self.video_widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            layout.addWidget(self.video_widget)
            
            # Setup player
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            self.player.errorOccurred.connect(self._on_player_error)
            
            # Set to infinite looping!
            if hasattr(QMediaPlayer, 'Infinite'):
                self.player.setLoops(QMediaPlayer.Infinite)
            else:
                self.player.setLoops(-1)
                
            # Default to muted for professional DAM experience
            self.audio_output.setMuted(True)
            
            # Tiny mute/unmute overlay button in the top-right
            self.btn_mute = QPushButton("🔇", self)
            self.btn_mute.setObjectName("MuteOverlayButton")
            self.btn_mute.setFixedSize(24, 24)
            self.btn_mute.clicked.connect(self.toggle_mute)
        else:
            # Fallback label
            self.lbl_fallback = QLabel("Fallback Player", self)
            self.lbl_fallback.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold; background: #121212; border: 1px solid #333;")
            self.lbl_fallback.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.lbl_fallback)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if is_multimedia_available() and hasattr(self, 'btn_mute'):
            # Place button in top-right corner with a small margin
            self.btn_mute.move(self.width() - self.btn_mute.width() - 6, 6)
            self.btn_mute.raise_()

    @Slot()
    def toggle_mute(self):
        if not is_multimedia_available() or not hasattr(self, 'audio_output'):
            return
        muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not muted)
        self.btn_mute.setText("🔇" if not muted else "🔊")

    def load_video(self, video_path, name=""):
        if not video_path or not os.path.exists(video_path):
            self.clear_video()
            return
            
        if self.video_path == video_path and self.is_playing:
            return # Already playing this video, don't restart it!
            
        self.video_path = video_path
        
        if is_multimedia_available() and hasattr(self, 'player'):
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.show()
            self.player.play()
            self.is_playing = True
        else:
            if hasattr(self, 'lbl_fallback'):
                self.lbl_fallback.setText(f"System Play:\n{os.path.basename(video_path)}")
            self.show()

    def clear_video(self):
        self.video_path = None
        if is_multimedia_available() and hasattr(self, 'player'):
            self.player.stop()
            self.player.setSource(QUrl())
        self.is_playing = False
        self.hide()

    def mousePressEvent(self, event):
        # Toggle play/pause on click
        if event.button() == Qt.LeftButton:
            if is_multimedia_available() and hasattr(self, 'player'):
                if self.is_playing:
                    self.player.pause()
                    self.is_playing = False
                else:
                    self.player.play()
                    self.is_playing = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def _on_player_error(self, error, error_string):
        print(f"[VideoPlayerOverlay Error] QMediaPlayer Error ({error}): {error_string}")
