import unittest
from unittest.mock import MagicMock, patch

from logic.desktop_controller import DesktopController


class DesktopControllerTests(unittest.TestCase):
    def test_switch_next_is_cooldown_gated(self):
        controller = DesktopController()
        with patch.object(controller, "_hotkey_alt_tab") as mocked_switch:
            message_1 = controller.switch_window_next(now_ms=1000)
            message_2 = controller.switch_window_next(now_ms=1100)

        self.assertIn("Switched", message_1)
        self.assertIn("Cooldown", message_2)
        mocked_switch.assert_called_once()

    def test_control_volume_uses_key_taps(self):
        controller = DesktopController()
        with patch.object(controller, "_key_tap") as mocked_tap:
            message = controller.control_volume(3, now_ms=1000)
        self.assertIn("Volume up", message)
        self.assertEqual(mocked_tap.call_count, 3)

    @patch("logic.desktop_controller.pyautogui", new=MagicMock())
    def test_system_scroll_calls_pyautogui(self):
        controller = DesktopController()
        message = controller.system_scroll(-120, now_ms=1000)
        self.assertIn("Scrolled", message)

    @patch("logic.desktop_controller.pyautogui", new=MagicMock())
    def test_click_primary_calls_pyautogui(self):
        controller = DesktopController()
        message = controller.click_primary(200, 220, now_ms=1000)
        self.assertIn("click", message.lower())

    def test_open_application_handles_empty_target(self):
        controller = DesktopController()
        message = controller.open_application("", now_ms=1000)
        self.assertIn("failed", message.lower())


if __name__ == "__main__":
    unittest.main()
