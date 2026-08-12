import unittest
import os
import sys
import tempfile
import shutil
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from logic.image_model import ImageItem
from utils import (
    resolve_middle_frame_source_file,
    ensure_repre_middle_frame_thumbnail
)

class TestAyonRepreMiddleFrameThumb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resolve_middle_frame_source_file_sequence(self):
        # Create a mock 5-frame sequence: frame_0001.png to frame_0005.png
        seq_dir = os.path.join(self.temp_dir, "sequence")
        os.makedirs(seq_dir, exist_ok=True)
        frame_paths = []
        for i in range(1, 6):
            p = os.path.join(seq_dir, f"frame_{i:04d}.png")
            img = QImage(30, 30, QImage.Format_RGB32)
            img.fill(QColor("blue"))
            img.save(p)
            frame_paths.append(p)

        # Middle frame of 5 frames should be index 2 -> frame_0003.png
        mid_file = resolve_middle_frame_source_file(frame_paths[0])
        self.assertIsNotNone(mid_file)
        self.assertEqual(os.path.normpath(mid_file), os.path.normpath(frame_paths[2]))

    def test_ensure_repre_middle_frame_thumbnail_creates_cache(self):
        # Create a mock media file
        media_path = os.path.join(self.temp_dir, "test_render.png")
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(QColor("red"))
        img.save(media_path)

        cache_root = os.path.join(self.temp_dir, "thumbs_cache")

        item = ImageItem(
            file_path=media_path,
            label="Shot 010 Comp v001",
            is_ayon_item=True
        )
        setattr(item, "repre_id", "repre-xyz-999")

        secrets_or_config = {
            "ayon_thumbnails_cache": cache_root,
            "ffmpeg_path": "ffmpeg.exe"
        }

        # Run ensure_repre_middle_frame_thumbnail
        res_img = ensure_repre_middle_frame_thumbnail(item, "BCV_009", secrets_or_config)
        self.assertIsNotNone(res_img)
        self.assertTrue(hasattr(item, "thumbnail_image") and item.thumbnail_image is not None)

        # Verify that file was saved in the cache root under project folder
        expected_cache_path = os.path.join(cache_root, "BCV_009", "repre-xyz-999.jpg")
        self.assertTrue(os.path.exists(expected_cache_path))

    def test_ensure_repre_middle_frame_thumbnail_uses_existing_cache(self):
        cache_root = os.path.join(self.temp_dir, "thumbs_cache")
        proj_cache_dir = os.path.join(cache_root, "BCV_009")
        os.makedirs(proj_cache_dir, exist_ok=True)
        cached_file = os.path.join(proj_cache_dir, "repre-already-cached.jpg")

        img = QImage(50, 50, QImage.Format_RGB32)
        img.fill(QColor("green"))
        img.save(cached_file)

        item = ImageItem(
            file_path="non_existent_file.mov",
            label="Shot 020 Comp v001",
            is_ayon_item=True
        )
        setattr(item, "repre_id", "repre-already-cached")

        secrets_or_config = {
            "ayon_thumbnails_cache": cache_root
        }

        res_img = ensure_repre_middle_frame_thumbnail(item, "BCV_009", secrets_or_config)
        self.assertIsNotNone(res_img)
        self.assertTrue(hasattr(item, "thumbnail_image"))

    def test_thumbnail_item_aspect_ratio(self):
        from gui.thumbnail_area import ThumbnailItem
        # 16:9 aspect ratio image (1920x1080)
        media_path = os.path.join(self.temp_dir, "widescreen.png")
        img = QImage(1920, 1080, QImage.Format_RGB32)
        img.fill(QColor("yellow"))
        img.save(media_path)

        item = ImageItem(file_path=media_path, label="16:9 Item", is_ayon_item=True)
        setattr(item, "repre_id", "repre-169")
        secrets_or_config = {"ayon_thumbnails_cache": os.path.join(self.temp_dir, "cache")}

        ensure_repre_middle_frame_thumbnail(item, "BCV_009", secrets_or_config)

        thumb_item = ThumbnailItem(item)
        aspect = thumb_item._get_aspect_ratio()
        self.assertAlmostEqual(aspect, 1920 / 1080, places=1)

if __name__ == "__main__":
    unittest.main()

