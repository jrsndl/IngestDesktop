"""pytest setup.

Tests must never read or write the real preference files: every test session
gets an empty settings folder (built-in defaults only) and saving is disabled.
"""
import os
import sys
import tempfile

_settings_dir = tempfile.mkdtemp(prefix="ingestdesktop_test_settings_")
os.environ["INGESTDESKTOP_CONFIG_DIR"] = _settings_dir
os.environ.setdefault("INGESTDESKTOP_NO_SAVE", "1")
# Confirmation boxes (gui/notify.py) are printed instead of shown, so no popup waits for a click
os.environ.setdefault("INGESTDESKTOP_NO_DIALOGS", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
