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

        orig_addAction = QMenu.addAction
        def mock_addAction(menu_self, *args, **kwargs):
            res = orig_addAction(menu_self, *args, **kwargs)
            if args and hasattr(args[0], 'text'):
                captured_actions.append(args[0])
            return res

        QMenu.addAction = mock_addAction
        orig_exec = QMenu.exec
        QMenu.exec = lambda *a, **k: None

        try:
            cme = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), QPoint(10, 10))
            area.contextMenuEvent(cme)
            
            arrange_actions = [act for act in captured_actions if act.text() == "Arrange"]
            self.assertEqual(len(arrange_actions), 1)
            arrange_action = arrange_actions[0]
            
            self.assertEqual(arrange_action.shortcut().toString(), "Alt+A")
        finally:
            QMenu.addAction = orig_addAction
            QMenu.exec = orig_exec

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
