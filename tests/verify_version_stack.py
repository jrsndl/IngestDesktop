import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QModelIndex, QItemSelectionModel, QEvent
from PySide6.QtGui import QKeyEvent
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
    # Patch start_scan to be a no-op to prevent background scanner from scanning
    original_start_scan = MainWindow.start_scan
    MainWindow.start_scan = lambda self, directory: None
    
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
    
    # 4. Verify position replication and layout transitions
    print("4. Testing layout transitions and position replication...")
    
    from gui.thumbnail_area import ThumbnailItem
    thumb_v1 = ThumbnailItem(v1_in_win)
    thumb_v3 = ThumbnailItem(v3_in_win)
    win.thumb_area.scene.addItem(thumb_v1)
    win.thumb_area.scene.addItem(thumb_v3)
    win.thumb_area.item_to_thumb = {v1_in_win: thumb_v1, v3_in_win: thumb_v3}
    
    # Set v1's position in scene and mark as manually moved
    pos1 = (100.0, 150.0)
    thumb_v1.setPos(pos1[0], pos1[1])
    thumb_v1.is_manually_moved = True
    v1_in_win.position = pos1
    v1_in_win.is_manually_moved = True
    
    # Change version to 3, which should copy coordinates/manual flag to v3
    win.change_version_stack_picked_version(v1_in_win, 3)
    
    assert v3_in_win.position == pos1, f"Expected position {pos1}, got {v3_in_win.position}"
    assert v3_in_win.is_manually_moved is True
    assert thumb_v3.is_manually_moved is True
    assert thumb_v3.pos().x() == pos1[0]
    assert thumb_v3.pos().y() == pos1[1]
    print("-> Position copying upon picking a different version PASSED.")
    
    # Now verify Off -> On transition:
    # Set different positions for v1 and v3 (stack mode off, both visible)
    # v1 is at y=150, v3 is at y=50 (physically higher)
    v1_in_win.position = (100.0, 150.0)
    thumb_v1.setPos(100.0, 150.0)
    
    v3_in_win.position = (100.0, 50.0)
    thumb_v3.setPos(100.0, 50.0)
    
    # Set stack to Off first
    win.model.v_stack_enabled = False
    win.filter_panel.btn_v_stack.setChecked(False)
    
    # Toggle to On (Off -> On transition)
    win.filter_panel.btn_v_stack.setChecked(True)
    win._save_filter_toggles()
    
    # The picked version is currently 3 (since we changed it to 3 above)
    # The physically highest item of the stack was v3 (y=50). So the picked item (v3) should keep/take y=50.
    assert v3_in_win.position == (100.0, 50.0), f"Expected collapsing to use highest item position, got {v3_in_win.position}"
    print("-> Collapse stack to highest item position (Off -> On transition) PASSED.")
    
    # Now verify On -> Off transition:
    # Position the picked item (v3) at (200.0, 300.0)
    v3_in_win.position = (200.0, 300.0)
    thumb_v3.setPos(200.0, 300.0)
    
    # Toggle to Off (On -> Off transition)
    win.filter_panel.btn_v_stack.setChecked(False)
    win._save_filter_toggles()
    
    # v3 is picked (base position=200,300)
    # Other item (v1) should be positioned vertically below v3 (y = 300 + height + gap_v)
    assert v3_in_win.position == (200.0, 300.0)
    
    h_v3 = thumb_v3.boundingRect().height()
    gap_v = win.thumb_area._last_arrange_vals.get("gap_v", 20)
    expected_y = 300.0 + h_v3 + gap_v
    
    assert v1_in_win.position[0] == 200.0
    assert abs(v1_in_win.position[1] - expected_y) < 1.0, f"Expected other version vertically below at {expected_y}, got {v1_in_win.position[1]}"
    assert v1_in_win.is_manually_moved is True
    assert thumb_v1.is_manually_moved is True
    print("-> Expand stack vertically below base position (On -> Off transition) PASSED.")
    
    # 5. Verify "Version Stack Select" action in Version Stack Mode OFF
    print("5. Testing 'Version Stack Select' context action (stack mode off)...")
    assert win.model.v_stack_enabled is False
    
    # Select just one item first
    win.thumb_area.scene.clearSelection()
    thumb_v1.setSelected(True)
    assert len(win.thumb_area.scene.selectedItems()) == 1
    
    # Trigger selection helper via thumb area
    win.thumb_area._select_all_items_in_stack(v1_in_win)
    # Check that both v1 and v3 are selected
    selected_thumbs = [it for it in win.thumb_area.scene.selectedItems() if isinstance(it, ThumbnailItem)]
    assert len(selected_thumbs) == 2
    assert thumb_v1 in selected_thumbs
    assert thumb_v3 in selected_thumbs
    print("-> Thumbnail 'Version Stack Select' PASSED.")
    
    # Now clear selection and select single item in table/spreadsheet
    win.spreadsheet.table.selectionModel().clearSelection()
    r_idx = win.model.index(win.model.items.index(v1_in_win), 0)
    win.spreadsheet.table.selectionModel().select(r_idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
    
    # Trigger selection helper via spreadsheet
    win.spreadsheet._select_all_items_in_stack(v1_in_win)
    
    # Both rows should be selected
    selected_rows = win.spreadsheet.table.selectionModel().selectedRows()
    assert len(selected_rows) == 2
    print("-> Spreadsheet 'Version Stack Select' PASSED.")
    
    # Now verify selection helper via filter panel
    win.filter_panel.tree.selectionModel().clearSelection()
    win.filter_panel.proxy._rebuild_cache()
    
    # Trigger selection helper via filter panel
    win.filter_panel._select_all_items_in_stack(v1_in_win)
    
    selected_indexes = win.filter_panel.tree.selectionModel().selectedRows()
    assert len(selected_indexes) == 2
    print("-> Filter Panel 'Version Stack Select' PASSED.")
    
    # 6. Verify Version Stack Hotkeys in Thumbnail View
    print("6. Testing Version Stack hotkeys...")
    # Enable version stack mode first so we can change versions
    win.filter_panel.btn_v_stack.setChecked(True)
    win._save_filter_toggles()
    assert win.model.v_stack_enabled is True
    
    # Select the stack item thumbnail
    win.thumb_area.scene.clearSelection()
    thumb_v3.setSelected(True)
    
    key = win.model.get_version_stack_key(v3_in_win)
    stack = win.model.version_stacks.get(key)
    assert stack["picked"] == 3
    
    # Test Alt + Down (previous version, which should be 1)
    ev_down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.AltModifier)
    res = win.thumb_area.eventFilter(win.thumb_area.view.viewport(), ev_down)
    assert res is True
    app.processEvents()
    assert stack["picked"] == 1
    print("-> Alt + Down Arrow (previous version) PASSED.")
    
    # Test Alt + Up (next version, which should be 3)
    ev_up = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.AltModifier)
    res = win.thumb_area.eventFilter(win.thumb_area.view.viewport(), ev_up)
    assert res is True
    app.processEvents()
    assert stack["picked"] == 3
    print("-> Alt + Up Arrow (next version) PASSED.")
    
    # Test Alt + Ctrl + Down (minimum version, which should be 1)
    ev_ctrl_down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.AltModifier | Qt.ControlModifier)
    res = win.thumb_area.eventFilter(win.thumb_area.view.viewport(), ev_ctrl_down)
    assert res is True
    app.processEvents()
    assert stack["picked"] == 1
    print("-> Alt + Ctrl + Down Arrow (minimum version) PASSED.")
    
    # Test Alt + Ctrl + Up (maximum version, which should be 3)
    ev_ctrl_up = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.AltModifier | Qt.ControlModifier)
    res = win.thumb_area.eventFilter(win.thumb_area.view.viewport(), ev_ctrl_up)
    assert res is True
    app.processEvents()
    assert stack["picked"] == 3
    print("-> Alt + Ctrl + Up Arrow (maximum version) PASSED.")
    
    print("-> Tag synchronization and version switching PASSED.")
    print("\nALL VERSION STACK TESTS PASSED!")
    
    MainWindow.start_scan = original_start_scan
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
