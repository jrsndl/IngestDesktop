"""Quiet notification helpers.

On Windows, QMessageBox.information/warning/critical make the system play its
"asterisk"/"exclamation" sound every time a box appears. For routine
confirmations ("Settings saved", "Preset saved", "CSV exported") that beep is
noise, so we show a plain QDialog instead, which Windows does not treat as an
alert. A sound is played only when the user enabled "play_sounds" in
Preferences > General (default: off).
"""
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QStyle, QVBoxLayout)
from PySide6.QtCore import Qt
import os


def sounds_enabled(config):
    return bool((config or {}).get("play_sounds", False))


def play_notification_sound(config, error=False):
    """Play a short system sound if the user enabled sounds."""
    if not sounds_enabled(config):
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION if error else winsound.MB_OK)
    except Exception:
        QApplication.beep()


def show_info(parent, title, text, config=None, icon=QStyle.SP_MessageBoxInformation):
    """Modal info box that looks like QMessageBox.information but stays silent
    unless sounds are enabled in preferences."""
    if os.environ.get("INGESTDESKTOP_NO_DIALOGS"):  # automated tests: never block on a popup
        print(f"[{title}] {text}")
        return
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

    row = QHBoxLayout()
    icon_lbl = QLabel()
    icon_lbl.setPixmap(dlg.style().standardIcon(icon).pixmap(32, 32))
    icon_lbl.setAlignment(Qt.AlignTop)
    row.addWidget(icon_lbl)
    msg = QLabel(text)
    msg.setWordWrap(True)
    msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
    msg.setMinimumWidth(320)
    row.addWidget(msg, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    buttons.accepted.connect(dlg.accept)

    layout = QVBoxLayout(dlg)
    layout.addLayout(row)
    layout.addWidget(buttons)

    play_notification_sound(config)
    dlg.exec()


def show_warning(parent, title, text, config=None):
    show_info(parent, title, text, config, icon=QStyle.SP_MessageBoxWarning)
