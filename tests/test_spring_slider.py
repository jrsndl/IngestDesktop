"""Spring-loaded canvas sliders: relative scaling, knob snaps back to the middle."""
import sys
import unittest

from PySide6.QtWidgets import QApplication, QSlider

app = QApplication.instance() or QApplication(sys.argv)

from gui.spring_slider import SpringSlider
from logic.image_model import ImageItem


class TestSpringSlider(unittest.TestCase):
    def test_drag_scales_from_start_and_springs_back(self):
        s = SpringSlider(4, 200, 10, strength=2.0)
        seen = []
        s.sizeChanged.connect(seen.append)
        s.setSliderDown(True)            # press
        QSlider.setValue(s, 100)         # knob at the right end -> x2
        self.assertEqual(s.value(), 20)
        QSlider.setValue(s, -100)        # left end -> /2 of the START value
        self.assertEqual(s.value(), 5)
        s.setSliderDown(False)           # release
        self.assertEqual(QSlider.value(s), 0)
        self.assertEqual(s.value(), 5)
        self.assertEqual(seen[-1], 5)

    def test_groove_step_is_one_relative_step(self):
        s = SpringSlider(4, 200, 100, strength=2.0)
        QSlider.setValue(s, 100)         # not dragging: one step, then back to the middle
        self.assertEqual(s.value(), 200)
        self.assertEqual(QSlider.value(s), 0)

    def test_setvalue_is_the_logical_value(self):
        s = SpringSlider(20, 1000, 150, auto_apply=False)
        s.setValue(300)
        self.assertEqual(s.value(), 300)
        self.assertEqual(QSlider.value(s), 0)


class TestThumbSliderScalesItems(unittest.TestCase):
    def test_items_keep_their_relative_sizes(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            ta = win.thumb_area
            items = [ImageItem(file_path=f"d:/test/f_{i}.jpg", label=f"F {i}") for i in range(3)]
            win.model.add_items(items)
            thumbs = [ta.item_to_thumb[d] for d in items]
            for i, (t, size) in enumerate(zip(thumbs, (100, 200, 300))):
                t.size = size
                t.setPos(i * 400, 0)
            ta.scene.clearSelection()
            ta._begin_thumb_scale()
            ta._on_thumb_scale(2.0)
            ta._end_thumb_scale()
            self.assertEqual([t.size for t in thumbs], [200, 400, 600])
            # layout kept: left-to-right order and the top row stay as they were
            xs = [t.pos().x() for t in thumbs]
            self.assertEqual(xs, sorted(xs))
            # no overlap after the re-layout
            rects = [t.sceneBoundingRect() for t in thumbs]
            for i in range(len(rects)):
                for j in range(i + 1, len(rects)):
                    self.assertFalse(rects[i].intersects(rects[j]), (i, j))
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
