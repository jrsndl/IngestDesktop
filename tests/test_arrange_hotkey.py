import unittest
import sys

from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtGui import QKeyEvent, QContextMenuEvent
from PySide6.QtCore import Qt, QEvent, QPoint

from gui.thumbnail_area import ThumbnailArea
from logic.image_model import ImageTableModel

app = QApplication.instance() or QApplication(sys.argv)

class TestArrangeHotkey(unittest.TestCase):
    def test_arrange_context_menu_shortcut(self):
        model = ImageTableModel()
        area = ThumbnailArea()
        area.model = model
        
        captured_actions = []

        def collect(menu):
            for act in menu.actions():
                captured_actions.append(act)
                if act.menu():
                    collect(act.menu())

        # Capture the menu instead of showing it (patching QMenu.exec does not
        # stop the real popup with PySide6 6.10)
        area._exec_context_menu = lambda menu, pos: collect(menu)

        cme = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), QPoint(10, 10))
        area.contextMenuEvent(cme)

        arrange_actions = [act for act in captured_actions if act.text() == "Arrange"]
        self.assertEqual(len(arrange_actions), 1)
        arrange_action = arrange_actions[0]

        self.assertEqual(arrange_action.shortcut().toString(), "Alt+A")

    def test_arrange_hotkey_event(self):
        model = ImageTableModel()
        area = ThumbnailArea()
        area.model = model
        
        arranged = []
        area._on_arrange = lambda mode: arranged.append(mode)
        
        # Simulate Alt+A key press
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.AltModifier)
        handled = area.eventFilter(area.view, key_event)
        
        self.assertTrue(handled)
        self.assertEqual(arranged, ["grid"])

if __name__ == "__main__":
    unittest.main()
