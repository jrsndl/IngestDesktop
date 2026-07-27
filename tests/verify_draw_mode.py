import sys
import os
import shutil
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import Qt, QPointF, QEvent, QPoint
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QGraphicsItem

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic.image_model import ImageItem
from gui.main_window import MainWindow
from gui.thumbnail_area import DrawItem, DrawingCanvasItem, DrawToolbar

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

def test_draw_mode():
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Initialize MainWindow with patched start_scan to avoid background thread interference
    MainWindow.start_scan = lambda self, directory: None
    
    win = MainWindow()
    thumb_area = win.thumb_area
    
    # Setup test source folder
    test_folder = os.path.abspath("./_test_draw_mode_folder")
    os.makedirs(test_folder, exist_ok=True)
    win.model.source_folder = test_folder
    
    # 1. Test D Shortcut to Enter Draw Mode
    assert not thumb_area._draw_mode_active
    
    # Simulate Key D press event on view
    key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_D, Qt.NoModifier)
    res = thumb_area.eventFilter(thumb_area.view, key_event)
    assert res is True, "Key D should be intercepted to enter Draw Mode"
    assert thumb_area._draw_mode_active is True, "Draw Mode should be active"
    assert thumb_area._canvas_item is not None, "Drawing Canvas Item should be created"
    assert thumb_area.draw_toolbar.isVisible() is True, "Draw Toolbar should be visible"
    
    # 2. Test Stroke Drawing on Canvas
    canvas = thumb_area._canvas_item
    
    # Simulate drawing brush strokes
    canvas.mousePressEvent(MockEvent(QPointF(100, 100), Qt.LeftButton))
    assert canvas.current_stroke is not None
    canvas.mouseMoveEvent(MockEvent(QPointF(150, 150), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(200, 200), Qt.LeftButton))
    
    assert len(canvas.strokes) == 1
    assert canvas.strokes[0]["tool"] == "brush"
    
    # 3. Test Eraser Mode
    thumb_area.draw_toolbar.btn_eraser.click()
    assert canvas.active_tool == "eraser"
    
    # Simulate eraser stroke
    canvas.mousePressEvent(MockEvent(QPointF(150, 150), Qt.LeftButton))
    canvas.mouseMoveEvent(MockEvent(QPointF(160, 160), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(170, 170), Qt.LeftButton))
    
    assert len(canvas.strokes) == 2
    assert canvas.strokes[1]["tool"] == "eraser"
    
    # 4. Test Style & Thickness Options
    thumb_area.draw_toolbar.combo_thickness.setCurrentText("10 px")
    thumb_area.draw_toolbar.combo_style.setCurrentText("Dashed")
    thumb_area.draw_toolbar.btn_brush.click()
    assert canvas.active_tool == "brush"
    assert canvas.active_thickness == 10
    assert canvas.active_style == "dashed"
    
    # Test Arrow Tool
    thumb_area.draw_toolbar.btn_arrow.click()
    assert canvas.active_tool == "arrow"
    canvas.mousePressEvent(MockEvent(QPointF(300, 100), Qt.LeftButton))
    canvas.mouseMoveEvent(MockEvent(QPointF(350, 150), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(350, 150), Qt.LeftButton))
    
    assert len(canvas.strokes) == 3
    assert canvas.strokes[2]["tool"] == "arrow"
    assert len(canvas.strokes[2]["points"]) == 2
    assert canvas.strokes[2]["points"][0] == QPointF(300, 100)
    assert canvas.strokes[2]["points"][1] == QPointF(350, 150)
    
    # Test Circle Tool
    thumb_area.draw_toolbar.btn_circle.click()
    assert canvas.active_tool == "circle"
    canvas.mousePressEvent(MockEvent(QPointF(200, 200), Qt.LeftButton))
    canvas.mouseMoveEvent(MockEvent(QPointF(250, 250), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(250, 250), Qt.LeftButton))
    
    assert len(canvas.strokes) == 4
    assert canvas.strokes[3]["tool"] == "circle"
    assert len(canvas.strokes[3]["points"]) == 2
    assert canvas.strokes[3]["points"][0] == QPointF(200, 200)
    assert canvas.strokes[3]["points"][1] == QPointF(250, 250)
    
    # Test Rectangle Tool
    thumb_area.draw_toolbar.btn_rect.click()
    assert canvas.active_tool == "rectangle"
    canvas.mousePressEvent(MockEvent(QPointF(50, 50), Qt.LeftButton))
    canvas.mouseMoveEvent(MockEvent(QPointF(100, 80), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(100, 80), Qt.LeftButton))
    
    assert len(canvas.strokes) == 5
    assert canvas.strokes[4]["tool"] == "rectangle"
    assert len(canvas.strokes[4]["points"]) == 2
    assert canvas.strokes[4]["points"][0] == QPointF(50, 50)
    assert canvas.strokes[4]["points"][1] == QPointF(100, 80)
    
    # 5. Exit Draw Mode using Escape key and verify file cache and DrawItem creation
    esc_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    res_esc = thumb_area.eventFilter(thumb_area.view, esc_event)
    assert res_esc is True, "Escape key should exit draw mode"
    assert not thumb_area._draw_mode_active
    assert not thumb_area.draw_toolbar.isVisible()
    
    # Verify DrawItem was created in the scene
    scene_items = thumb_area.scene.items()
    draw_items = [it for it in scene_items if isinstance(it, DrawItem)]
    assert len(draw_items) == 1, "A DrawItem should be created in the scene"
    
    draw_item = draw_items[0]
    assert os.path.exists(draw_item.file_path), "PNG file should be cached on disk"
    assert draw_item.file_path.endswith(".png")
    
    # 6. Selecting the DrawItem and entering Draw Mode again to edit / merge strokes
    thumb_area.scene.clearSelection()
    draw_item.setSelected(True)
    assert len(thumb_area.scene.selectedItems()) == 1
    
    # Press D again
    res = thumb_area.eventFilter(thumb_area.view, key_event)
    assert res is True
    assert thumb_area._draw_mode_active is True
    assert thumb_area._edit_draw_item is draw_item, "Should load selected DrawItem for editing"
    assert not draw_item.isVisible(), "Edited DrawItem should be temporarily hidden"
    
    # Draw another brush stroke
    canvas = thumb_area._canvas_item
    canvas.mousePressEvent(MockEvent(QPointF(300, 300), Qt.LeftButton))
    canvas.mouseMoveEvent(MockEvent(QPointF(350, 350), Qt.LeftButton))
    canvas.mouseReleaseEvent(MockEvent(QPointF(400, 400), Qt.LeftButton))
    
    # Exit Draw Mode
    res_esc = thumb_area.eventFilter(thumb_area.view, esc_event)
    assert not thumb_area._draw_mode_active
    assert draw_item.isVisible(), "Edited DrawItem should be visible again"
    
    # 7. Test DrawItem resize handles
    assert draw_item.is_custom_size is False
    orig_w = draw_item.width
    orig_h = draw_item.height
    
    # Press mouse on bottom right corner of DrawItem to simulate resize
    corner = QPointF(draw_item.width - 5, draw_item.height - 5)
    draw_item.setSelected(True)
    draw_item.mousePressEvent(MockEvent(corner, Qt.LeftButton, draw_item.pos() + corner))
    assert draw_item._resizing is True
    
    # Move to drag
    draw_item.mouseMoveEvent(MockEvent(corner + QPointF(50, 50), Qt.LeftButton, draw_item.pos() + corner + QPointF(50, 50)))
    draw_item.mouseReleaseEvent(MockEvent(corner + QPointF(50, 50), Qt.LeftButton, draw_item.pos() + corner + QPointF(50, 50)))
    assert draw_item._resizing is False
    assert draw_item.width == orig_w + 50, f"Expected width {orig_w + 50}, got {draw_item.width}"
    assert draw_item.height == orig_h + 50, f"Expected height {orig_h + 50}, got {draw_item.height}"
    assert draw_item.is_custom_size is True
    
    # 8. Test project Save / Load Serialization
    project_file = os.path.join(test_folder, "test_draw_project.yaml")
    win.current_project_path = project_file
    win.save_project_files(project_file)
    
    assert os.path.exists(project_file)
    
    # Create new window and load the project to verify loading restores DrawItem
    win2 = MainWindow()
    win2.model.source_folder = test_folder
    win2.current_project_path = project_file
    
    original_getOpenFileName = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = lambda *args, **kwargs: (project_file, "IngestProject (*.yaml)")
    
    try:
        win2.perform_open_project()
    finally:
        QFileDialog.getOpenFileName = original_getOpenFileName
    
    scene2_items = win2.thumb_area.scene.items()
    loaded_drawings = [it for it in scene2_items if isinstance(it, DrawItem)]
    assert len(loaded_drawings) == 1, "Drawing should be loaded successfully"
    loaded_draw = loaded_drawings[0]
    assert loaded_draw.width == orig_w + 50
    assert loaded_draw.height == orig_h + 50
    assert loaded_draw.is_custom_size is True
    assert os.path.exists(loaded_draw.file_path)
    
    # 9. Test deletion of DrawItem
    loaded_draw.setSelected(True)
    # Simulate delete key
    delete_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    win2.thumb_area.view.hasFocus = lambda: True
    res_del = win2.thumb_area.eventFilter(win2.thumb_area.view, delete_event)
    assert res_del is True, "Delete key should be handled"
    
    # Verify item is removed from scene and file is deleted from disk
    assert loaded_draw not in win2.thumb_area.scene.items()
    assert not os.path.exists(loaded_draw.file_path), "File should be deleted from disk"
    
    # 10. Test drawing configuration defaults persistence
    # Enter draw mode on win2
    res = win2.thumb_area.eventFilter(win2.thumb_area.view, key_event)
    assert res is True
    assert win2.thumb_area._draw_mode_active is True
    
    # Change toolbar controls
    win2.thumb_area.draw_toolbar.combo_thickness.setCurrentText("20 px")
    win2.thumb_area.draw_toolbar.combo_style.setCurrentText("Dashed")
    
    # Verify values are updated in the configuration
    cfg = win2.thumb_area.get_config()
    assert cfg.get("draw_default_thickness") == "20 px"
    assert cfg.get("draw_default_style") == "Dashed"
    
    # Exit draw mode
    res_esc = win2.thumb_area.eventFilter(win2.thumb_area.view, esc_event)
    assert not win2.thumb_area._draw_mode_active
    
    # Re-enter draw mode and assert defaults are read from config and applied
    res = win2.thumb_area.eventFilter(win2.thumb_area.view, key_event)
    assert res is True
    assert win2.thumb_area._draw_mode_active is True
    assert win2.thumb_area.draw_toolbar.combo_thickness.currentText() == "20 px"
    assert win2.thumb_area.draw_toolbar.combo_style.currentText() == "Dashed"
    
    # Exit draw mode to clean up
    res_esc = win2.thumb_area.eventFilter(win2.thumb_area.view, esc_event)
    
    # 11. Test draw mode hotkeys & tooltips
    # Enter draw mode again
    res = win2.thumb_area.eventFilter(win2.thumb_area.view, key_event)
    assert res is True
    assert win2.thumb_area._draw_mode_active is True

    # Assert tooltips contain key shortcuts
    toolbar = win2.thumb_area.draw_toolbar
    assert "Brush (B)" in toolbar.btn_brush.toolTip()
    assert "Eraser (E)" in toolbar.btn_eraser.toolTip()
    assert "Arrow (A)" in toolbar.btn_arrow.toolTip()
    assert "Brush Color (C)" in toolbar.btn_color.toolTip()
    assert "Delete Drawing (Delete)" in toolbar.btn_delete.toolTip()
    assert "Done (Esc / Right Click)" in toolbar.btn_close.toolTip()
    assert "Brush Thickness ([ / ])" in toolbar.combo_thickness.toolTip()

    # Press keys and verify tool selection changes
    # Start with brush checked
    toolbar.btn_brush.setChecked(True)
    toolbar.btn_eraser.setChecked(False)
    toolbar.btn_arrow.setChecked(False)
    win2.thumb_area._canvas_item.active_tool = "brush"
    
    # Press E key (Eraser)
    e_key = QKeyEvent(QEvent.KeyPress, Qt.Key_E, Qt.NoModifier)
    res_e = win2.thumb_area.eventFilter(win2.thumb_area.view, e_key)
    assert res_e is True
    assert toolbar.btn_eraser.isChecked() is True
    assert toolbar.btn_brush.isChecked() is False
    assert win2.thumb_area._canvas_item.active_tool == "eraser"
    
    # Press B key (Brush)
    b_key = QKeyEvent(QEvent.KeyPress, Qt.Key_B, Qt.NoModifier)
    res_b = win2.thumb_area.eventFilter(win2.thumb_area.view, b_key)
    assert res_b is True
    assert toolbar.btn_brush.isChecked() is True
    assert toolbar.btn_eraser.isChecked() is False
    assert win2.thumb_area._canvas_item.active_tool == "brush"

    # Press A key (Arrow)
    a_key = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier)
    res_a = win2.thumb_area.eventFilter(win2.thumb_area.view, a_key)
    assert res_a is True
    assert toolbar.btn_arrow.isChecked() is True
    assert toolbar.btn_brush.isChecked() is False
    assert win2.thumb_area._canvas_item.active_tool == "arrow"

    # Press [ and ] keys (Brush thickness combo index navigation)
    toolbar.combo_thickness.setCurrentText("5 px") # Index 1
    bracket_right = QKeyEvent(QEvent.KeyPress, Qt.Key_BracketRight, Qt.NoModifier)
    res_br = win2.thumb_area.eventFilter(win2.thumb_area.view, bracket_right)
    assert res_br is True
    assert toolbar.combo_thickness.currentText() == "10 px" # Index 2

    bracket_left = QKeyEvent(QEvent.KeyPress, Qt.Key_BracketLeft, Qt.NoModifier)
    res_bl = win2.thumb_area.eventFilter(win2.thumb_area.view, bracket_left)
    assert res_bl is True
    assert toolbar.combo_thickness.currentText() == "5 px" # Index 1
    
    # Press Delete key to finish and delete/exit Draw Mode
    del_key = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    res_del = win2.thumb_area.eventFilter(win2.thumb_area.view, del_key)
    assert res_del is True
    assert win2.thumb_area._draw_mode_active is False
    
    # Cleanup
    shutil.rmtree(test_folder, ignore_errors=True)
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_draw_mode()
