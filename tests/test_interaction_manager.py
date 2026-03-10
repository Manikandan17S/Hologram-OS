import unittest
from unittest.mock import patch

from config import DELETE_HOLD_MS
from core.gesture_engine import GestureEvent
from logic.interaction_manager import DESKTOP_MODE, FILE_MODE, InteractionManager
from ui.dustbin_object import Dustbin
from ui.file_object import FileObject


def hand_input(x, y, gesture, phase, hand_depth_z=0.0):
    return {
        "cursor": (x, y),
        "palm_center": (x, y),
        "pinch_center": (x, y),
        "hand_depth_z": float(hand_depth_z),
        "event": GestureEvent(
            gesture=gesture,
            phase=phase,
            stable_frames=1,
            confidence=1.0,
            timestamp=0.0,
        ),
    }


def mode_toggle_event():
    return GestureEvent(
        gesture="MODE_TOGGLE",
        phase="start",
        stable_frames=1,
        confidence=1.0,
        timestamp=0.0,
    )


def expand_open_event():
    return GestureEvent(
        gesture="EXPAND_OPEN",
        phase="start",
        stable_frames=3,
        confidence=0.95,
        timestamp=0.0,
    )


def expand_armed_event():
    return GestureEvent(
        gesture="EXPAND_OPEN",
        phase="hold",
        stable_frames=2,
        confidence=0.82,
        timestamp=0.0,
    )


class InteractionManagerTests(unittest.TestCase):
    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_expand_is_cooldown_gated(self, _mocked_drives):
        manager = InteractionManager()
        manager.file_objects = [FileObject("Documents", "C:\\Docs", True, (10, 10))]
        dustbin = Dustbin(400, 400)

        with patch.object(manager, "load_folder", return_value=True) as mocked_load_folder:
            manager.handle_input(hand_input(20, 20, "EXPAND", "start"), None, dustbin, now_ms=1000)
            manager.handle_input(hand_input(20, 20, "EXPAND", "start"), None, dustbin, now_ms=1200)
            manager.handle_input(hand_input(20, 20, "EXPAND", "start"), None, dustbin, now_ms=1800)

        self.assertEqual(mocked_load_folder.call_count, 2)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_tracking_loss_cancels_drag_without_delete(self, _mocked_drives):
        manager = InteractionManager()
        manager.file_objects = [FileObject("demo.txt", "C:\\demo.txt", False, (0, 0))]
        dustbin = Dustbin(0, 0)

        manager.handle_input(hand_input(10, 10, "FIST", "start"), None, dustbin, now_ms=1000)
        manager.handle_input(hand_input(20, 20, "FIST", "hold"), None, dustbin, now_ms=1100)
        manager.handle_input(None, None, dustbin, now_ms=1200)

        self.assertIsNone(manager.dragging_object)
        self.assertEqual(len(manager.file_objects), 1)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    @patch("logic.interaction_manager.delete_item", return_value=(True, "Moved to Recycle Bin"))
    def test_delete_requires_hold_then_open_palm(self, mocked_delete, _mocked_drives):
        manager = InteractionManager()
        manager.file_objects = [FileObject("demo.txt", "C:\\demo.txt", False, (0, 0))]
        dustbin = Dustbin(0, 0)

        manager.handle_input(hand_input(10, 10, "FIST", "start"), None, dustbin, now_ms=1000)
        manager.handle_input(hand_input(20, 20, "FIST", "hold"), None, dustbin, now_ms=1010)
        manager.handle_input(
            hand_input(22, 22, "FIST", "hold"),
            None,
            dustbin,
            now_ms=1010 + DELETE_HOLD_MS + 20,
        )
        manager.handle_input(
            hand_input(22, 22, "OPEN_PALM", "start"),
            None,
            dustbin,
            now_ms=1010 + DELETE_HOLD_MS + 40,
        )

        mocked_delete.assert_called_once()
        self.assertEqual(len(manager.file_objects), 0)
        self.assertIsNone(manager.dragging_object)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_mode_toggle_with_global_event(self, _mocked_drives):
        manager = InteractionManager()
        dustbin = Dustbin(0, 0)
        self.assertEqual(manager.mode, FILE_MODE)

        manager.handle_input(
            None,
            None,
            dustbin,
            mode_toggle_event=mode_toggle_event(),
            mode_hold_progress=1.0,
            now_ms=1000,
        )
        self.assertEqual(manager.mode, DESKTOP_MODE)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_overlay_notified_on_mode_toggle(self, _mocked_drives):
        class MockOverlay:
            def __init__(self):
                self.calls = []

            def notify(self, gesture_name, action_description):
                self.calls.append((gesture_name, action_description))

        overlay = MockOverlay()
        manager = InteractionManager(overlay=overlay)
        dustbin = Dustbin(0, 0)
        manager.handle_input(
            None,
            None,
            dustbin,
            mode_toggle_event=mode_toggle_event(),
            mode_hold_progress=1.0,
            now_ms=1000,
        )

        self.assertIn(("MODE_TOGGLE", "Switching Mode"), overlay.calls)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_desktop_radial_selection_routes_action(self, _mocked_drives):
        manager = InteractionManager()
        dustbin = Dustbin(0, 0)
        manager.handle_input(
            None,
            None,
            dustbin,
            mode_toggle_event=mode_toggle_event(),
            mode_hold_progress=1.0,
            now_ms=1000,
        )
        self.assertEqual(manager.mode, DESKTOP_MODE)

        right_open_hold = hand_input(100, 100, "OPEN_PALM", "hold")
        manager.handle_input(right_open_hold, None, dustbin, now_ms=1100)
        manager.handle_input(right_open_hold, None, dustbin, now_ms=2205)

        right_select = hand_input(200, 100, "DOUBLE_TAP", "start")
        right_select["palm_center"] = (100, 100)
        with patch.object(manager.desktop_controller, "open_application", return_value="Opened explorer") as mocked_open:
            manager.handle_input(right_select, None, dustbin, now_ms=2300)
        mocked_open.assert_called_once()

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_double_tap_does_not_open_hovered_file_in_file_mode(self, _mocked_drives):
        manager = InteractionManager()
        manager.file_objects = [FileObject("demo.txt", "C:\\demo.txt", False, (0, 0))]
        dustbin = Dustbin(0, 0)

        with patch("logic.interaction_manager.open_file", return_value=(True, "Opened successfully")) as mocked_open:
            manager.handle_input(hand_input(10, 10, "DOUBLE_TAP", "start"), None, dustbin, now_ms=1000)
        mocked_open.assert_not_called()

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_open_folder_pushes_previous_path_to_history(self, _mocked_drives):
        manager = InteractionManager()
        manager.navigator.current_path = "C:\\Users"
        folder = FileObject("Docs", "C:\\Users\\Docs", True, (0, 0))

        with patch.object(manager, "load_folder", return_value=True) as mocked_load:
            manager._open_hovered_item(folder, now_ms=1000, gesture_name="EXPAND")

        mocked_load.assert_called_once_with(folder.path)
        self.assertEqual(manager.folder_history[-1], "C:\\Users")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_navigate_back_uses_folder_history_stack(self, _mocked_drives):
        manager = InteractionManager()
        manager.folder_history = ["C:\\Users\\HP"]

        with patch.object(manager, "load_folder", return_value=True) as mocked_load:
            with patch.object(manager, "_reload_current_path") as mocked_reload:
                ok = manager.navigate_back(now_ms=1000)

        self.assertTrue(ok)
        mocked_load.assert_called_once_with("C:\\Users\\HP")
        mocked_reload.assert_called_once()
        self.assertEqual(manager.folder_history, [])

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_navigate_back_root_history_empty_sets_status(self, _mocked_drives):
        manager = InteractionManager()
        manager.folder_history = []
        manager.navigator.current_path = None

        ok = manager.navigate_back(now_ms=1000)

        self.assertFalse(ok)
        self.assertEqual(manager.status_text, "Already at root folder")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_navigate_back_to_drive_hub_reloads_ui(self, _mocked_drives):
        manager = InteractionManager()
        manager.folder_history = [None]

        with patch.object(manager, "load_drives") as mocked_load_drives:
            with patch.object(manager, "_reload_current_path") as mocked_reload:
                ok = manager.navigate_back(now_ms=1000)

        self.assertTrue(ok)
        mocked_load_drives.assert_called_once()
        mocked_reload.assert_called_once()

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_swipe_left_two_routes_back_or_prev_window(self, _mocked_drives):
        manager = InteractionManager()
        dustbin = Dustbin(0, 0)
        manager.navigator.current_path = "C:\\Users\\HP\\Documents"

        with patch.object(manager, "navigate_back") as mocked_back:
            manager.handle_input(hand_input(10, 10, "SWIPE_LEFT_TWO", "start"), None, dustbin, now_ms=1000)
        mocked_back.assert_called_once()

        manager.handle_input(
            None,
            None,
            dustbin,
            mode_toggle_event=mode_toggle_event(),
            mode_hold_progress=1.0,
            now_ms=2000,
        )
        with patch.object(manager.desktop_controller, "navigate_swipe", return_value="ok") as mocked_prev:
            manager.handle_input(hand_input(10, 10, "SWIPE_LEFT_TWO", "start"), None, dustbin, now_ms=2500)
        mocked_prev.assert_called_once_with("left", now_ms=2500)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_push_on_folder_sets_spatial_focus(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        other = FileObject("demo.txt", "C:\\demo.txt", False, (160, 0))
        manager.file_objects = [folder, other]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PUSH", "start"), None, dustbin, now_ms=1000)

        self.assertIs(manager.spatial_engine.focus_object, folder)
        self.assertEqual(folder.depth_state, "focus")
        self.assertEqual(other.depth_state, "parent")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_pull_returns_parent_layer_before_navigation(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        manager.spatial_engine.set_focus_layer(folder)
        dustbin = Dustbin(400, 400)

        with patch.object(manager, "navigate_back") as mocked_back:
            manager.handle_input(hand_input(12, 12, "PULL", "start"), None, dustbin, now_ms=1500)

        mocked_back.assert_not_called()
        self.assertFalse(manager.spatial_engine.has_focus())
        self.assertEqual(folder.depth_state, "default")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_pinch_grab_and_expand_open_focuses_folder(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)
        self.assertEqual(folder.depth_state, "grabbed")
        self.assertAlmostEqual(folder.target_z, 0.65, places=2)

        manager.handle_input(
            hand_input(10, 10, "PINCH", "hold"),
            hand_input(120, 10, "PINCH", "hold"),
            dustbin,
            expand_open_event=expand_open_event(),
            now_ms=1100,
        )
        self.assertIsNone(manager.grabbed_object)
        self.assertIs(manager.spatial_engine.focus_object, folder)
        self.assertEqual(folder.depth_state, "focus")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    @patch("logic.interaction_manager.os.startfile")
    def test_pinch_expand_open_launches_file(self, mocked_startfile, _mocked_drives):
        manager = InteractionManager()
        file_obj = FileObject("demo.txt", "C:\\demo.txt", False, (0, 0))
        manager.file_objects = [file_obj]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, file_obj)

        manager.handle_input(
            hand_input(10, 10, "PINCH", "hold"),
            hand_input(120, 10, "PINCH", "hold"),
            dustbin,
            expand_open_event=expand_open_event(),
            now_ms=1100,
        )

        mocked_startfile.assert_called_once_with(file_obj.path)
        self.assertIsNone(manager.grabbed_object)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_grabbed_state_blocks_drag_interaction(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        manager.handle_input(hand_input(10, 10, "FIST", "start"), None, dustbin, now_ms=1030)
        self.assertIsNone(manager.dragging_object)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    @patch("logic.interaction_manager.delete_item", return_value=(True, "Moved to Recycle Bin"))
    def test_pinch_release_over_trash_deletes_grabbed_object(self, mocked_delete, _mocked_drives):
        manager = InteractionManager()
        file_obj = FileObject("trash.txt", "C:\\trash.txt", False, (0, 0))
        manager.file_objects = [file_obj]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(0, 0)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        manager.handle_input(hand_input(10, 10, "PINCH", "hold"), None, dustbin, now_ms=1020)
        self.assertTrue(dustbin.hovered)
        manager.handle_input(hand_input(10, 10, "OPEN_PALM", "start"), None, dustbin, now_ms=1060)

        mocked_delete.assert_called_once_with(file_obj.path, mode="recycle_bin")
        self.assertEqual(len(manager.file_objects), 0)
        self.assertIsNone(manager.grabbed_object)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_file_mode_swipe_up_down_scrolls_and_clamps(self, _mocked_drives):
        manager = InteractionManager()
        items = [
            {"name": f"Item{i}", "path": f"C:\\Item{i}", "type": "folder"}
            for i in range(40)
        ]
        manager._build_file_objects(items)
        dustbin = Dustbin(400, 400)

        self.assertEqual(manager.scroll_offset, 0.0)
        manager.handle_input(hand_input(100, 100, "SWIPE_UP", "start"), None, dustbin, now_ms=1000)
        self.assertLess(manager.scroll_offset, 0.0)
        first_offset = manager.scroll_offset

        manager.handle_input(hand_input(100, 100, "SWIPE_DOWN", "start"), None, dustbin, now_ms=1100)
        self.assertGreaterEqual(manager.scroll_offset, first_offset)
        self.assertLessEqual(manager.scroll_offset, manager.scroll_max_offset)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_grabbed_folder_follows_pinch_center(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        start_pos = (folder.x, folder.y)
        manager.handle_input(hand_input(260, 180, "PINCH", "hold"), None, dustbin, now_ms=1033)

        self.assertNotEqual((folder.x, folder.y), start_pos)
        self.assertGreater(folder.x, start_pos[0])
        self.assertGreater(folder.y, start_pos[1])

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_grab_magnet_snaps_within_radius(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (100, 100))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        for obj in manager.file_objects:
            obj.update()
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(228, 150, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_grabbed_depth_responds_to_hand_depth_z(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(40, 40, "PINCH", "start"), None, dustbin, now_ms=1000)
        z_before = folder.z
        manager.handle_input(
            hand_input(260, 180, "PINCH", "hold", hand_depth_z=0.8),
            None,
            dustbin,
            now_ms=1033,
        )
        self.assertGreater(folder.z, z_before)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_grabbed_folder_releases_when_pinch_breaks(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(10, 10, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)
        manager.handle_input(hand_input(10, 10, "FIST", "start"), None, dustbin, now_ms=1030)

        self.assertIsNone(manager.grabbed_object)
        self.assertEqual(folder.depth_state, "default")

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_two_hand_pinch_uses_midpoint_tracking(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(40, 40, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)
        start_x = folder.x
        z_before = folder.z
        right_x, right_y = 220, 200
        left_x, left_y = 420, 200

        right_world_x, _ = manager._screen_to_world(right_x, right_y, z_before)
        mid_world_x, _ = manager._screen_to_world((right_x + left_x) * 0.5, (right_y + left_y) * 0.5, z_before)
        follow_smoothing = 0.18
        expected_right = start_x + ((right_world_x - (folder.w * 0.5) - start_x) * follow_smoothing)
        expected_mid = start_x + ((mid_world_x - (folder.w * 0.5) - start_x) * follow_smoothing)

        manager.handle_input(
            hand_input(right_x, right_y, "PINCH", "hold", hand_depth_z=0.467),
            hand_input(left_x, left_y, "PINCH", "hold", hand_depth_z=0.467),
            dustbin,
            now_ms=1033,
        )
        self.assertLess(abs(folder.x - expected_mid), abs(folder.x - expected_right))

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_two_hand_pinch_freezes_depth_before_expand_emit(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(40, 40, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)
        manager.handle_input(
            hand_input(220, 200, "PINCH", "hold"),
            hand_input(420, 200, "PINCH", "hold"),
            dustbin,
            now_ms=1033,
        )
        self.assertAlmostEqual(folder.target_z, folder.z, places=3)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_two_hand_pinch_expand_armed_locks_position_to_anchor(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(40, 40, "PINCH", "start"), None, dustbin, now_ms=1000)
        self.assertIs(manager.grabbed_object, folder)
        anchor_x = folder.x
        anchor_y = folder.y
        right_x, right_y = 220, 200
        left_x, left_y = 420, 200

        manager.handle_input(
            hand_input(right_x, right_y, "PINCH", "hold"),
            hand_input(left_x, left_y, "PINCH", "hold"),
            dustbin,
            expand_open_event=expand_armed_event(),
            now_ms=1033,
        )
        self.assertTrue(manager.expand_armed)
        self.assertEqual(folder.depth_state, "expand_armed")
        self.assertEqual(manager.expand_anchor, (anchor_x, anchor_y))
        self.assertEqual(folder.x, anchor_x)
        self.assertEqual(folder.y, anchor_y)

    @patch("logic.interaction_manager.get_drives", return_value=[])
    def test_expand_open_start_clears_anchor(self, _mocked_drives):
        manager = InteractionManager()
        folder = FileObject("Docs", "C:\\Docs", True, (0, 0))
        manager.file_objects = [folder]
        manager.spatial_engine.bind_objects(manager.file_objects)
        dustbin = Dustbin(400, 400)

        manager.handle_input(hand_input(40, 40, "PINCH", "start"), None, dustbin, now_ms=1000)
        manager.handle_input(
            hand_input(220, 200, "PINCH", "hold"),
            hand_input(420, 200, "PINCH", "hold"),
            dustbin,
            expand_open_event=expand_armed_event(),
            now_ms=1033,
        )
        self.assertIsNotNone(manager.expand_anchor)

        manager.handle_input(
            hand_input(220, 200, "PINCH", "hold"),
            hand_input(420, 200, "PINCH", "hold"),
            dustbin,
            expand_open_event=expand_open_event(),
            now_ms=1066,
        )
        self.assertIsNone(manager.expand_anchor)


if __name__ == "__main__":
    unittest.main()
