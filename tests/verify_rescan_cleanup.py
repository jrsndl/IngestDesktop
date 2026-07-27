import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from logic.image_model import ImageItem
from gui.main_window import MainWindow

def test_rescan_cleanup():
    app = QApplication.instance() or QApplication(sys.argv)
    
    # 1. Create a temp directory structure
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Create a few files
        file1 = os.path.join(temp_dir, "still_v01.png")
        file2 = os.path.join(temp_dir, "still_v02.png")
        file_seq1 = os.path.join(temp_dir, "seq_v01.1001.png")
        file_seq2 = os.path.join(temp_dir, "seq_v01.1002.png")
        
        with open(file1, "w") as f: f.write("test")
        with open(file2, "w") as f: f.write("test")
        with open(file_seq1, "w") as f: f.write("test")
        with open(file_seq2, "w") as f: f.write("test")
        
        # Patch start_scan to be a no-op to prevent scanning in constructor
        original_start_scan = MainWindow.start_scan
        MainWindow.start_scan = lambda self, directory: None
        
        win = MainWindow()
        
        # Add items to model
        item1 = ImageItem(file1.replace("\\", "/"), label="still_v01", version=1)
        item2 = ImageItem(file2.replace("\\", "/"), label="still_v02", version=2)
        item_seq = ImageItem(file_seq1.replace("\\", "/"), label="seq_v01", version=1, is_sequence=True)
        
        win.model.items = [item1, item2, item_seq]
        win.top_bar.path_display.setText(temp_dir)
        
        # Verify initial state
        assert len(win.model.items) == 3
        
        # Now delete file1 on disk, and one file from seq
        os.remove(file1)
        os.remove(file_seq1)
        
        # Run rescan_current
        # Since start_scan is mocked, let's verify rescan_current handles clean up properly
        # Wait, rescan_current calls ImageScanner. Let's patch ImageScanner so it doesn't do real background scanning
        from logic.scanner import ImageScanner
        original_start = ImageScanner.start
        ImageScanner.start = lambda self: None
        
        # Call rescan_current
        win.rescan_current()
        
        # Since file1 was deleted, item1 should be removed.
        # Since file_seq1 was deleted but file_seq2 still exists, item_seq should NOT be removed, and item_seq.file_path should be updated to file_seq2.
        assert len(win.model.items) == 2
        assert item1 not in win.model.items
        assert item2 in win.model.items
        assert item_seq in win.model.items
        assert item_seq.file_path == file_seq2.replace("\\", "/")
        
        # Now delete file2 and file_seq2
        os.remove(file2)
        os.remove(file_seq2)
        
        # Call rescan_current again
        win.rescan_current()
        
        # Both should be removed now
        assert len(win.model.items) == 0
        
        print("Rescan cleanup test passed!")
        
        # Restore patches
        MainWindow.start_scan = original_start_scan
        ImageScanner.start = original_start
        win.close()
        win.deleteLater()
        app.processEvents()
        
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    try:
        test_rescan_cleanup()
        import os
        os._exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
