import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.scanner import ImageScanner

def test_scan_ignore_drawcache():
    import tempfile
    import shutil
    
    # Create temp scanning directory
    temp_dir = tempfile.mkdtemp()
    try:
        # Create normal files
        still1 = os.path.join(temp_dir, "stillA_v01.png")
        still2 = os.path.join(temp_dir, "stillB_v01.png")
        with open(still1, "w") as f: f.write("test")
        with open(still2, "w") as f: f.write("test")
        
        # Create drawcache subdirectory and some mock draw cache files
        cache_dir = os.path.join(temp_dir, "_drawcache")
        os.makedirs(cache_dir, exist_ok=True)
        
        draw_file1 = os.path.join(cache_dir, "drawing_123.png")
        draw_file2 = os.path.join(cache_dir, "drawing_456.png")
        with open(draw_file1, "w") as f: f.write("drawing")
        with open(draw_file2, "w") as f: f.write("drawing")
        
        # Instantiate ImageScanner with relative to source folder and _drawcache path
        scanner = ImageScanner(
            temp_dir,
            recursive=True,
            drawing_cache_location="relative to source folder",
            drawing_cache_path="_drawcache",
            detect_sequences=True,
            timeout=2
        )
        
        # Inspect results from the finished signal
        results = []
        scanner.finished.connect(results.extend)
        scanner.run()
        
        print("Found items:")
        for item in results:
            print(f"  - {item.label} (path: {item.file_path})")
        
        # Verify result contains the two normal still items, and NOT the drawcache files!
        assert len(results) == 2, f"Expected 2 scanned items, got {len(results)}"
        
        labels = {item.label for item in results}
        assert "stillA_v01" in labels
        assert "stillB_v01" in labels
        
        for item in results:
            assert "_drawcache" not in item.file_path, f"Scanner failed to ignore draw cache path: {item.file_path}"
            
        print("Scan ignore draw cache test passed!")
        
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    try:
        test_scan_ignore_drawcache()
        os._exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
