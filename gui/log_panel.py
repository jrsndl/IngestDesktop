"""Log panel: resizable (drag the grip above it), context menu with Clear and verbosity."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QPlainTextEdit, QMenu
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtCore import Qt, Signal

# Verbosity levels: which message levels are shown
VERBOSITY = {
    "minimal": ("Errors && Warnings", {"error", "warning"}),
    "normal": ("Normal (+ Results)", {"error", "warning", "success"}),
    "verbose": ("Verbose (everything)", {"error", "warning", "success", "info"}),
}
COLORS = {"info": "#aaaaaa", "warning": "#ffcc00", "error": "#ff4444", "success": "#a6e22e"}
MAX_ENTRIES = 5000


class _Grip(QFrame):
    """Thin bar above the log; drag it up/down to resize the log."""
    dragged = Signal(int)  # dy
    released = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setCursor(Qt.SizeVerCursor)
        self.setStyleSheet("QFrame { background-color: #333333; } QFrame:hover { background-color: #ff9800; }")
        self.setToolTip("Drag to resize the log")
        self._last_y = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._last_y = e.globalPosition().y()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._last_y is not None:
            y = e.globalPosition().y()
            self.dragged.emit(int(y - self._last_y))
            self._last_y = y
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._last_y is not None:
            self._last_y = None
            self.released.emit()
            e.accept()


class LogPanel(QWidget):
    height_changed = Signal(int)
    verbosity_changed = Signal(str)

    def __init__(self, parent=None, height=200, verbosity="verbose"):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.grip = _Grip(self)
        self.console = QPlainTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setContextMenuPolicy(Qt.CustomContextMenu)
        self.console.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self.grip)
        lay.addWidget(self.console)
        self._entries = []  # (timestamp_prefix, level, message)
        self.verbosity = verbosity if verbosity in VERBOSITY else "verbose"
        self.grip.dragged.connect(self._on_drag)
        self.grip.released.connect(lambda: self.height_changed.emit(self.height()))
        self.set_log_height(height)

    # -- size --------------------------------------------------------------
    def set_log_height(self, h):
        top = self.window().height() * 0.8 if self.window() is not self else 2000
        h = int(max(60, min(h, max(120, top))))
        self.setFixedHeight(h)

    def _on_drag(self, dy):
        self.set_log_height(self.height() - dy)  # dragging up makes the log taller

    # -- content -----------------------------------------------------------
    def _shown(self, level):
        return level in VERBOSITY[self.verbosity][1] or level not in COLORS

    def _html(self, prefix, level, message):
        color = COLORS.get(level, "#aaaaaa")
        return f'<span style="color: {color};">{prefix}{message}</span>'

    def append(self, prefix, level, message):
        self._entries.append((prefix, level, message))
        if len(self._entries) > MAX_ENTRIES:
            del self._entries[:len(self._entries) - MAX_ENTRIES]
        if self._shown(level):
            self.console.appendHtml(self._html(prefix, level, message))
            sb = self.console.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear(self):
        self._entries = []
        self.console.clear()

    def set_verbosity(self, key):
        if key not in VERBOSITY:
            return
        self.verbosity = key
        self.console.clear()
        for prefix, level, message in self._entries:
            if self._shown(level):
                self.console.appendHtml(self._html(prefix, level, message))
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.verbosity_changed.emit(key)

    def _on_context_menu(self, pos):
        menu = self.console.createStandardContextMenu()
        menu.addSeparator()
        act_clear = QAction("Clear", menu)
        act_clear.triggered.connect(self.clear)
        menu.addAction(act_clear)
        sub = menu.addMenu("Verbosity")
        group = QActionGroup(sub)
        for key, (label, _levels) in VERBOSITY.items():
            a = QAction(label, sub)
            a.setCheckable(True)
            a.setChecked(key == self.verbosity)
            a.triggered.connect(lambda checked=False, k=key: self.set_verbosity(k))
            group.addAction(a)
            sub.addAction(a)
        menu.exec(self.console.viewport().mapToGlobal(pos))
