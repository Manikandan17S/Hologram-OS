import os
import tempfile
import unittest
from unittest.mock import patch

from filesystem.file_operations import delete_item


class FileOperationsTests(unittest.TestCase):
    def test_delete_rejects_unsafe_mode(self):
        success, message = delete_item("C:\\fake-path", mode="permanent")
        self.assertFalse(success)
        self.assertIn("Unsafe", message)

    def test_delete_rejects_root_path(self):
        root = os.path.abspath(os.sep)
        success, message = delete_item(root, mode="recycle_bin")
        self.assertFalse(success)
        self.assertIn("root", message.lower())

    def test_delete_rejects_protected_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            protected_dir = os.path.join(temp_dir, "Windows")
            os.makedirs(protected_dir, exist_ok=True)
            protected_file = os.path.join(protected_dir, "protected.txt")
            with open(protected_file, "w", encoding="utf-8") as handle:
                handle.write("blocked")

            success, message = delete_item(protected_file, mode="recycle_bin")
            self.assertFalse(success)
            self.assertIn("Protected", message)

    def test_delete_uses_send2trash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "demo.txt")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write("hello")

            with patch("filesystem.file_operations.send2trash") as mocked_send2trash:
                success, message = delete_item(file_path, mode="recycle_bin")

            self.assertTrue(success)
            self.assertIn("Recycle Bin", message)
            mocked_send2trash.assert_called_once_with(os.path.abspath(file_path))


if __name__ == "__main__":
    unittest.main()
