import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QModelIndex
from logic.image_model import ImageItem, ImageTableModel
from gui.main_window import MainWindow

def test_version_stacking():
    # Initialize PySide6 App context
    app = QApplication.instance() or QApplication(sys.argv)
    
    print("1. Creating ImageTableModel and adding versioned items...")
    model = ImageTableModel()
    model.version_regex = r"([._]v|v)(\d+)"
    
    # 1. Create versions of a sequence in different directories (should stack)
    item_v1 = ImageItem("c:\\fooo\\bar\\seq_v001.1001.exr", label="seq_v001.1001", version=1, is_sequence=True)
    item_v2 = ImageItem("d:\\some\\other\\seq_v003.1001.exr", label="seq_v003.1001", version=3, is_sequence=True)
    
    # 2. Different extension (should NOT stack)
    item_jpg = ImageItem("c:\\foo\\bar\\seq_v001.1001.jpg", label="seq_v001.1001.jpg", version=1, is_sequence=True)
    
    # 3. Still version stack
    item_still_v1 = ImageItem("d:\\show\\still_v01.png", label="still_v01", version=1)
    item_still_v2 = ImageItem("d:\\show\\still_v02.png", label="still_v02", version=2)
    
    # 4. Not part of a stack
    item_single = ImageItem("d:\\show\\single_v01.png", label="single_v01", version=1)
    
    # Add items to model (which triggers rebuild_version_stacks)
    model.items = [item_v1, item_v2, item_jpg, item_still_v1, item_still_v2, item_single]
    
    # Verify version extraction & setup
    assert item_v1.version == 1
    assert item_v2.version == 3
    assert item_jpg.version == 1
    assert item_still_v1.version == 1
    assert item_still_v2.version == 2
    assert item_single.version == 1
    
    print("-> Version extraction PASSED.")
    
    # Verify version stacks dict keys (purely filename and category-based, ignoring directory path)
    print(f"Version stacks calculated: {list(model.version_stacks.keys())}")
    
    seq_key = model.get_version_stack_key(item_v1)
    seq_key_v2 = model.get_version_stack_key(item_v2)
    jpg_key = model.get_version_stack_key(item_jpg)
    still_key = model.get_version_stack_key(item_still_v1)
    single_key = model.get_version_stack_key(item_single)
    
    # Seq keys must be identical across paths
    assert seq_key == seq_key_v2, f"Expected keys to be identical, got {seq_key} vs {seq_key_v2}"
    assert seq_key == ("seq.exr", True), f"Expected ('seq.exr', True), got {seq_key}"
    assert jpg_key == ("seq.jpg", True), f"Expected ('seq.jpg', True), got {jpg_key}"
    assert still_key == ("still.png", False), f"Expected ('still.png', False), got {still_key}"
    
    assert seq_key in model.version_stacks
    assert jpg_key in model.version_stacks
    assert still_key in model.version_stacks
    assert single_key in model.version_stacks
    
    # Check max version default picked
    assert model.version_stacks[seq_key]["picked"] == 3, "Expected default picked version to be max (3)"
    assert model.version_stacks[seq_key]["min"] == 1
    assert model.version_stacks[seq_key]["max"] == 3
    
    assert model.version_stacks[still_key]["picked"] == 2, "Expected default picked version to be max (2)"
    assert model.version_stacks[still_key]["min"] == 1
    assert model.version_stacks[still_key]["max"] == 2
    
    print("-> Stack grouping and default picked logic PASSED.")
    
    # 2. Check visibility by version stack
    # Only picked items should be visible
    model.v_stack_enabled = True
    assert model.is_item_visible_by_v_stack(item_v2, True) is True
    assert model.is_item_visible_by_v_stack(item_v1, True) is False
    
    assert model.is_item_visible_by_v_stack(item_still_v2, True) is True
    assert model.is_item_visible_by_v_stack(item_still_v1, True) is False
    
    assert model.is_item_visible_by_v_stack(item_single, True) is True
    
    print("-> Visibility check logic PASSED.")
    
    # 3. Test changing version and syncing is_tagged state
    # Tag item_v2 (version 3), change version to 1, verify item_v1 becomes tagged
    item_v2.is_tagged = True
    
    # Initialize MainWindow to use its real slot for version change
    print("Initializing MainWindow for signal propagation test...")
    win = MainWindow()
    win.model.items = [item_v1, item_v2, item_jpg, item_still_v1, item_still_v2, item_single]
    win.model.v_stack_enabled = True
    
    # Tag v2 in MainWindow model
    for it in win.model.items:
        if it.file_path == item_v2.file_path:
            it.is_tagged = True
            
    # Trigger version change via Slot
    win.change_version_stack_picked_version(item_v2, 1)
    
    # Now stack picked should be 1
    seq_stack = win.model.version_stacks[seq_key]
    assert seq_stack["picked"] == 1, f"Expected picked version 1, got {seq_stack['picked']}"
    
    # Tag should have migrated from v3 to v1
    v1_in_win = None
    v3_in_win = None
    for it in win.model.items:
        if it.file_path == item_v1.file_path:
            v1_in_win = it
        elif it.file_path == item_v2.file_path:
            v3_in_win = it
            
    assert v1_in_win.is_tagged is True, "Expected tag to sync to v1"
    
    # Visibility should change: v1 is now visible, v3 is not
    assert win.model.is_item_visible_by_v_stack(v1_in_win, True) is True
    assert win.model.is_item_visible_by_v_stack(v3_in_win, True) is False
    
    print("-> Tag synchronization and version switching PASSED.")
    print("\nALL VERSION STACK TESTS PASSED!")
    
    win.close()
    win.deleteLater()
    app.processEvents()
    return True

if __name__ == "__main__":
    try:
        success = test_version_stacking()
        if success:
            import os
            os._exit(0)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
