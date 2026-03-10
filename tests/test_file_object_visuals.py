import unittest

import pygame

from ui.file_object import FileObject
from ui.icon_loader import get_icon_surface, get_visual_surface, resolve_file_type


class FileObjectVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_resolve_file_type_by_extension(self):
        self.assertEqual(resolve_file_type("C:\\A\\Docs", True), "folder")
        self.assertEqual(resolve_file_type("C:\\A\\photo.jpeg", False), "image")
        self.assertEqual(resolve_file_type("C:\\A\\clip.mp4", False), "video")
        self.assertEqual(resolve_file_type("C:\\A\\readme.txt", False), "file")

    def test_file_object_sets_file_type(self):
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        image = FileObject("Photo", "C:\\photo.png", False, (0, 0))
        video = FileObject("Clip", "C:\\clip.webm", False, (0, 0))
        generic = FileObject("Note", "C:\\note.md", False, (0, 0))

        self.assertEqual(folder.file_type, "folder")
        self.assertEqual(image.file_type, "image")
        self.assertEqual(video.file_type, "video")
        self.assertEqual(generic.file_type, "file")

    def test_icon_loader_fallback_surfaces(self):
        for kind in ("folder", "image", "video", "file"):
            icon = get_icon_surface(kind, (48, 48))
            self.assertIsInstance(icon, pygame.Surface)
            self.assertEqual(icon.get_size(), (48, 48))

    def test_visual_surface_falls_back_when_thumbnail_missing(self):
        preview = get_visual_surface("C:\\missing\\does_not_exist.png", "image", (56, 56))
        self.assertIsInstance(preview, pygame.Surface)
        self.assertEqual(preview.get_size(), (56, 56))


if __name__ == "__main__":
    unittest.main()
