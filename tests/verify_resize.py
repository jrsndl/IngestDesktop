import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QHoverEvent
from PySide6.QtWidgets import QGraphicsItem

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.image_model import ImageItem, ImageTableModel
from gui.main_window import MainWindow
from gui.thumbnail_area import ThumbnailItem

class MockEvent:
    def __init__(self, pos, button=Qt.LeftButton, scene_pos=None):
        self._pos = pos
        self._button = button
        self._scene_pos = scene_pos or pos
        
    def pos(self):
        return self._pos
        
    def button(self):
        return self._button
        
    def scenePos(self):
        return self._scene_pos
        
    def accept(self):
        pass

def test_thumbnail_resize():
    # 1. Create QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    
    # 2. Mock some items
    item1 = ImageItem(
        "C:/test/file_v001.exr",
        label="file_v001",
        version=1,
        is_sequence=True
    )
    item2 = ImageItem(
        "C:/test/another_v002.exr",
        label="another_v002",
        version=2,
        is_sequence=True
    )
    
    # Initialize MainWindow with patched start_scan to avoid background thread interference
    original_start_scan = MainWindow.start_scan
    MainWindow.start_scan = lambda self, directory: None
    
    win = MainWindow()
    win.model.items = [item1, item2]
    
    # Rebuild items manually in ThumbnailArea
    win.thumb_area.add_items()
    app.processEvents()
    
    thumb1 = win.thumb_area.item_to_thumb.get(item1)
    thumb2 = win.thumb_area.item_to_thumb.get(item2)
    
    assert thumb1 is not None, "ThumbnailItem for item1 should be built"
    assert thumb2 is not None, "ThumbnailItem for item2 should be built"
    
    # Verify default sizes are 150
    assert thumb1.size == 150
    assert thumb2.size == 150
    assert item1.size == 150
    assert item2.size == 150
    
    # 3. Test Hovering over the bottom-right corner changes cursor
    # Calculate corner position of the image border
    img_rect = thumb1.get_image_rect()
    border_rect = img_rect.adjusted(-4, -4, 4, 4)
    corner_pos = QPointF(border_rect.right() - 5, border_rect.bottom() - 5)
    center_pos = QPointF(border_rect.width() / 2, border_rect.height() / 2)
    
    # Move hover to center (should be arrow cursor)
    thumb1.hoverMoveEvent(MockEvent(center_pos))
    assert thumb1.cursor().shape() == Qt.ArrowCursor, "Should be ArrowCursor at center"
    
    # Move hover to corner (should be SizeFDiagCursor)
    thumb1.hoverMoveEvent(MockEvent(corner_pos))
    assert thumb1.cursor().shape() == Qt.SizeFDiagCursor, "Should be SizeFDiagCursor at corner"
    
    # Hover leave should restore cursor
    thumb1.hoverLeaveEvent(MockEvent(corner_pos))
    assert thumb1.cursor().shape() == Qt.ArrowCursor, "Should be ArrowCursor after hover leave"
    
    # 4. Test Single Resize Dragging
    # Press Left Button on corner
    thumb1.mousePressEvent(MockEvent(corner_pos, Qt.LeftButton))
    assert thumb1._resizing is True, "Item should start resizing mode"
    
    # Drag by +50 pixels horizontally
    drag_pos = corner_pos + QPointF(50, 0)
    thumb1.mouseMoveEvent(MockEvent(corner_pos, Qt.LeftButton, scene_pos=drag_pos))
    # The size should increase from 150 to 200
    assert thumb1.size == 200, f"Expected size 200, got {thumb1.size}"
    assert item1.size == 200
    # The second thumbnail should remain at 150 (since it was not selected/resized)
    assert thumb2.size == 150
    
    # Release mouse
    thumb1.mouseReleaseEvent(MockEvent(drag_pos, Qt.LeftButton))
    assert thumb1._resizing is False, "Item should exit resizing mode"
    assert item1.is_manually_moved is True, "Item should be marked manually moved"
    
    # 5. Test Multiselection Resizing
    # Reset size to 150
    thumb1.size = 150
    item1.size = 150
    
    # Select both items
    win.thumb_area.scene.clearSelection()
    thumb1.setSelected(True)
    thumb2.setSelected(True)
    
    # Press Left Button on corner of thumb1
    thumb1.mousePressEvent(MockEvent(corner_pos, Qt.LeftButton))
    assert thumb1._resizing is True
    assert len(thumb1._selected_resizers) == 1, "Should capture other selected item to resize"
    assert thumb1._selected_resizers[0][0] == thumb2
    
    # Drag by -30 pixels
    drag_pos_smaller = corner_pos - QPointF(30, 0)
    thumb1.mouseMoveEvent(MockEvent(corner_pos, Qt.LeftButton, scene_pos=drag_pos_smaller))
    
    # Both sizes should decrease to 120
    assert thumb1.size == 120, f"Expected size 120, got {thumb1.size}"
    assert thumb2.size == 120, f"Expected size 120, got {thumb2.size}"
    assert item1.size == 120
    assert item2.size == 120
    
    # Release mouse
    thumb1.mouseReleaseEvent(MockEvent(drag_pos_smaller, Qt.LeftButton))
    assert thumb1._resizing is False
    assert item1.is_manually_moved is True
    assert item2.is_manually_moved is True
    
    # Restore start_scan function
    MainWindow.start_scan = original_start_scan
    win.close()
    win.deleteLater()
    app.processEvents()
    
    print("\nALL THUMBNAIL RESIZE TESTS PASSED!")
    return True

if __name__ == "__main__":
    try:
        success = test_thumbnail_resize()
        if success:
            import os
            os._exit(0)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
