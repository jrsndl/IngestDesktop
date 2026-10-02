"""Frame All frames only what is shown (hidden reviews / filtered items don't count)."""
import sys
import unittest

from PySide6.QtWidgets import QApplication, QGraphicsRectItem

app = QApplication.instance() or QApplication(sys.argv)


class TestFrameAll(unittest.TestCase):
    def test_hidden_items_are_ignored(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            ta = win.thumb_area
            for it in list(ta.scene.items()):
                if it.parentItem() is None:
                    ta.scene.removeItem(it)
            shown = QGraphicsRectItem(0, 0, 100, 100)
            hidden = QGraphicsRectItem(50000, 50000, 100, 100)
            hidden.setVisible(False)
            ta.scene.addItem(shown)
            ta.scene.addItem(hidden)
            rect = ta._visible_content_rect()
            self.assertLess(rect.right(), 1000)
            self.assertLess(rect.bottom(), 1000)
        finally:
            win.close()


    def test_frames_content_far_outside_the_initial_scene_rect(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            win.resize(1200, 800)
            win.show()
            QApplication.processEvents()
            ta = win.thumb_area
            far = QGraphicsRectItem(200000, 100000, 30000, 20000)
            ta.scene.addItem(far)
            ta.scene.clearSelection()
            ta.frame_all()
            vp = ta.view.viewport().rect()
            center = ta.view.mapFromScene(far.sceneBoundingRect().center())
            self.assertLess(abs(center.x() - vp.center().x()), 5)
            self.assertLess(abs(center.y() - vp.center().y()), 5)
            shown = ta.view.mapFromScene(far.sceneBoundingRect()).boundingRect()
            self.assertTrue(vp.adjusted(-2, -2, 2, 2).contains(shown))
        finally:
            win.close()


    def test_panning_has_room_at_any_zoom(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            win.resize(1200, 800)
            win.show()
            QApplication.processEvents()
            ta = win.thumb_area
            ta.view.resetTransform()
            ta.view.scale(0.002, 0.002)          # far out: 1 px = 500 scene units
            ta._grow_scene_rect(False)
            vis = ta.view.mapToScene(ta.view.viewport().rect()).boundingRect()
            sr = ta.scene.sceneRect()
            self.assertLessEqual(sr.left(), vis.left() - 3 * vis.width())
            self.assertGreaterEqual(sr.right(), vis.right() + 3 * vis.width())
            # pan far to the left in steps: the view keeps moving
            start = ta.view.mapToScene(ta.view.viewport().rect().center()).x()
            for _ in range(20):
                ta._grow_scene_rect(False)
                c = ta.view.mapToScene(ta.view.viewport().rect().center())
                ta.view.centerOn(c.x() - vis.width(), c.y())
            end = ta.view.mapToScene(ta.view.viewport().rect().center()).x()
            self.assertLess(end, start - 15 * vis.width())
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
