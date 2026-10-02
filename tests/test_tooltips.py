"""Every button, toggle and input has a tooltip; tooltips wait 2 s before showing."""
import sys
import unittest

from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QAbstractSpinBox,
                               QLineEdit, QSlider, QPlainTextEdit, QTabBar, QStyle, QAbstractScrollArea)

app = QApplication.instance() or QApplication(sys.argv)

from gui import tooltips
tooltips.install_all()

_CONTROL_TYPES = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit, QSlider, QPlainTextEdit)


def _missing(root):
    """Controls in `root` without a tooltip (internal parts of other widgets are skipped)."""
    out = []
    for w in root.findChildren(_CONTROL_TYPES):
        p = w.parentWidget()
        # the line edit inside a spin box / combo box, tab bar scroll arrows, scroll bars...
        if isinstance(p, (QAbstractSpinBox, QComboBox, QTabBar, QAbstractScrollArea)):
            continue
        if p is not None and isinstance(p.parentWidget(), QAbstractScrollArea) and isinstance(w, QAbstractButton):
            continue
        if not w.toolTip():
            out.append(f"{type(w).__name__} '{getattr(w, 'text', lambda: '')()}' "
                       f"(object '{w.objectName()}', parent {type(p).__name__})")
    return out


class TestTooltips(unittest.TestCase):
    def test_preferences_controls_have_tooltips(self):
        from gui.prefs_dialog import PreferencesDialog
        dlg = PreferencesDialog({}, {})
        self.assertEqual(_missing(dlg), [])
        # tabs too
        for i in range(dlg.tabs.count()):
            self.assertTrue(dlg.tabs.tabToolTip(i), dlg.tabs.tabText(i))
        # a form label shows its field's tooltip
        lbl = dlg.thumbs_form.labelForField(dlg.thumb_suffix)
        self.assertEqual(lbl.toolTip(), dlg.thumb_suffix.toolTip())

    def test_main_window_controls_have_tooltips(self):
        from gui.main_window import MainWindow
        win = MainWindow()
        try:
            self.assertEqual(_missing(win), [])
        finally:
            win.close()

    def test_dialogs_have_tooltips(self):
        from gui.canvas.widgets import BackdropDialog, SequenceRenameDialog, ArrangeDialog
        from gui.window.dialogs import RenameDialog, SearchReplaceDialog
        for dlg in (BackdropDialog(), SequenceRenameDialog(), ArrangeDialog("grid"),
                    RenameDialog("x"), SearchReplaceDialog()):
            self.assertEqual(_missing(dlg), [], type(dlg).__name__)

    def test_tip_wraps_long_text_as_rich_text(self):
        t = tooltips.tip("a < b\nnext line")
        self.assertTrue(t.startswith("<qt>"))
        self.assertIn("a &lt; b<br>next line", t)

    def test_tooltip_delay_is_two_seconds(self):
        style = tooltips.TooltipDelayStyle()
        self.assertEqual(style.styleHint(QStyle.SH_ToolTip_WakeUpDelay), 2000)


if __name__ == "__main__":
    unittest.main()
