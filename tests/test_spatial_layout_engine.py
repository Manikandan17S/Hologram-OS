import unittest

from config import SPATIAL_BASE_Z, SPATIAL_FOCUS_Z, SPATIAL_PARENT_Z
from logic.spatial_layout_engine import SpatialLayoutEngine
from ui.file_object import FileObject


class SpatialLayoutEngineTests(unittest.TestCase):
    def test_bind_objects_initializes_depth_fields(self):
        engine = SpatialLayoutEngine()
        objects = [
            FileObject("A", "C:\\A", True, (10, 10)),
            FileObject("B", "C:\\B", False, (120, 10)),
        ]

        engine.bind_objects(objects)

        self.assertEqual(len(engine.objects), 2)
        self.assertFalse(engine.has_focus())
        for obj in objects:
            self.assertEqual(obj.z, SPATIAL_BASE_Z)
            self.assertEqual(obj.target_z, SPATIAL_BASE_Z)
            self.assertEqual(obj.depth_state, "default")

    def test_set_focus_layer_sets_parent_depth_targets(self):
        engine = SpatialLayoutEngine()
        focused = FileObject("Folder", "C:\\Folder", True, (10, 10))
        sibling = FileObject("Readme.txt", "C:\\Readme.txt", False, (120, 10))
        engine.bind_objects([focused, sibling])

        ok = engine.set_focus_layer(focused)

        self.assertTrue(ok)
        self.assertTrue(engine.has_focus())
        self.assertIs(engine.focus_object, focused)
        self.assertEqual(focused.target_z, SPATIAL_FOCUS_Z)
        self.assertEqual(focused.depth_state, "focus")
        self.assertEqual(sibling.target_z, SPATIAL_PARENT_Z)
        self.assertEqual(sibling.depth_state, "parent")

    def test_update_interpolates_depth(self):
        engine = SpatialLayoutEngine(smoothing_factor=0.2)
        obj = FileObject("Folder", "C:\\Folder", True, (10, 10))
        engine.bind_objects([obj])
        obj.z = 1.0
        obj.target_z = 1.5

        engine.update(1.0 / 60.0)

        self.assertGreater(obj.z, 1.0)
        self.assertLess(obj.z, 1.5)

    def test_return_to_parent_resets_targets(self):
        engine = SpatialLayoutEngine()
        focused = FileObject("Folder", "C:\\Folder", True, (10, 10))
        sibling = FileObject("Readme.txt", "C:\\Readme.txt", False, (120, 10))
        engine.bind_objects([focused, sibling])
        engine.set_focus_layer(focused)

        engine.return_to_parent()

        self.assertFalse(engine.has_focus())
        for obj in (focused, sibling):
            self.assertEqual(obj.target_z, SPATIAL_BASE_Z)
            self.assertEqual(obj.depth_state, "default")


if __name__ == "__main__":
    unittest.main()
