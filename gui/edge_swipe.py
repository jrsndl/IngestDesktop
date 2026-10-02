"""Show / hide the side and bottom panels by swiping the mouse out over a window edge.

A quick mouse movement that crosses the left, right or bottom edge of the main
window toggles the panel on that side (left = AYON, right = files, bottom =
spreadsheet). Works for a maximized window too: there the cursor stops at the
screen edge, which counts as crossing.

What counts as a swipe (so normal mouse use never toggles anything):
- no mouse button is held, the app is the active app, no popup / modal dialog;
- the cursor came from inside the window, at least START_DISTANCE px from the
  edge, and covered MIN_TRAVEL px in the last WINDOW_S seconds, at least
  MIN_SPEED px/s fast, mostly across the edge;
- after crossing, the cursor stops near the edge: if it travels on more than
  MAX_OVERSHOOT px (e.g. on to a second monitor) the swipe is ignored;
- one swipe per edge: the cursor has to come back inside, away from the edge,
  before that edge can be swiped again.

The cursor is polled (no mouse tracking needed on every widget); the timer only
does work while the app is active.
"""
import time
from collections import deque

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

POLL_MS = 15
WINDOW_S = 0.15        # how far back the movement is measured
MIN_TRAVEL = 120       # px towards the edge within WINDOW_S
MIN_SPEED = 1200       # px/s
START_DISTANCE = 100   # the movement started at least this far inside the window
SETTLE_MS = 250        # wait after crossing, then check where the cursor stopped
MAX_OVERSHOOT = 400    # px past the edge; further = moved to another screen/app
REARM_DISTANCE = 80    # back inside, this far from the edge -> edge can be swiped again

EDGES = ("left", "right", "bottom")


def _dist_inside(edge, p, g):
    """Distance of point p from the given edge of rect g, positive inside the rect."""
    if edge == "left":
        return p.x() - g.left()
    if edge == "right":
        return g.right() - p.x()
    return g.bottom() - p.y()


class EdgeSwipe(QObject):
    swiped = Signal(str)  # "left" | "right" | "bottom"

    def __init__(self, window, parent=None):
        super().__init__(parent if parent is not None else (window if isinstance(window, QObject) else None))
        self.window = window
        self.enabled = True
        self._samples = deque()
        self._armed = {e: True for e in EDGES}
        self._pending = None  # (edge, deadline)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._tick)
        if isinstance(window, QWidget):
            self._timer.start()

    def _blocked(self):
        app = QApplication.instance()
        if not self.enabled or app is None or not self.window.isVisible() or self.window.isMinimized():
            return True
        if app.applicationState() != Qt.ApplicationState.ApplicationActive or not self.window.isActiveWindow():
            return True
        if QApplication.mouseButtons() != Qt.NoButton:
            return True
        return QApplication.activePopupWidget() is not None or QApplication.activeModalWidget() is not None

    def _tick(self, now=None, p=None):
        now = time.monotonic() if now is None else now
        p = QCursor.pos() if p is None else p
        self._samples.append((now, p))
        while self._samples and now - self._samples[0][0] > WINDOW_S:
            self._samples.popleft()

        if self._blocked():
            self._pending = None
            return
        g = self.window.geometry()

        if self._pending is not None:
            edge, deadline = self._pending
            if now >= deadline:
                self._pending = None
                if -_dist_inside(edge, p, g) <= MAX_OVERSHOOT:
                    self.swiped.emit(edge)
            return

        for edge in EDGES:
            d = _dist_inside(edge, p, g)
            if not self._armed[edge]:
                if d > REARM_DISTANCE and g.contains(p):
                    self._armed[edge] = True
                continue
            if d > 1:  # not at / past this edge
                continue
            t0, p0 = self._samples[0]
            dt = now - t0
            if dt < 0.03:
                continue
            travel = _dist_inside(edge, p0, g) - d
            if edge == "bottom":
                across = abs(p.x() - p0.x())
                along_ok = g.left() <= p.x() <= g.right()
            else:
                across = abs(p.y() - p0.y())
                along_ok = g.top() <= p.y() <= g.bottom()
            if (along_ok and g.contains(p0) and _dist_inside(edge, p0, g) >= START_DISTANCE
                    and travel >= MIN_TRAVEL and travel / dt >= MIN_SPEED and across < travel):
                self._armed[edge] = False
                self._pending = (edge, now + SETTLE_MS / 1000.0)
                break
