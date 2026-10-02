"""Edge swipe: a fast move out over a window edge toggles that edge's panel."""
import sys
import unittest

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from gui.edge_swipe import EdgeSwipe


class _Win:
    def geometry(self):
        return QRect(0, 0, 1000, 800)


class _Swipe(EdgeSwipe):
    def _blocked(self):
        return False


def _run(points, dt=0.015):
    s = _Swipe(_Win())
    got = []
    s.swiped.connect(got.append)
    t = 0.0
    for x, y in points:
        s._tick(t, QPoint(x, y))
        t += dt
    for _ in range(30):  # cursor rests where it stopped (settle time)
        s._tick(t, QPoint(*points[-1]))
        t += dt
    return got


class TestEdgeSwipe(unittest.TestCase):
    def test_fast_move_out_right_toggles_right(self):
        self.assertEqual(_run([(600 + i * 60, 400) for i in range(8)]), ["right"])

    def test_fast_move_down_toggles_bottom(self):
        self.assertEqual(_run([(500, 450 + i * 60) for i in range(7)]), ["bottom"])

    def test_slow_move_does_nothing(self):
        self.assertEqual(_run([(900 + i * 5, 400) for i in range(30)]), [])

    def test_move_on_to_another_screen_does_nothing(self):
        self.assertEqual(_run([(600 + i * 80, 400) for i in range(20)]), [])

    def test_one_toggle_per_swipe(self):
        pts = [(600 + i * 60, 400) for i in range(8)] + [(1010, 400)] * 10
        self.assertEqual(_run(pts), ["right"])


if __name__ == "__main__":
    unittest.main()
