import unittest
from unittest.mock import patch

import pygame

from ui.gesture_overlay import GestureOverlay


class GestureOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_notify_and_alpha_timeline(self):
        overlay = GestureOverlay(enabled=True)
        with patch("ui.gesture_overlay.time.time", return_value=10.0):
            overlay.notify("DOUBLE_TAP", "Click")

        with patch("ui.gesture_overlay.time.time", return_value=10.1):
            alpha_in = overlay._compute_alpha(10.1)
        with patch("ui.gesture_overlay.time.time", return_value=10.5):
            alpha_visible = overlay._compute_alpha(10.5)
        with patch("ui.gesture_overlay.time.time", return_value=12.3):
            alpha_done = overlay._compute_alpha(12.3)

        self.assertGreater(alpha_in, 0)
        self.assertEqual(alpha_visible, 255)
        self.assertEqual(alpha_done, 0)
        self.assertFalse(overlay.active)

    def test_notify_replaces_text_and_resets_timer(self):
        overlay = GestureOverlay(enabled=True)
        with patch("ui.gesture_overlay.time.time", return_value=1.0):
            overlay.notify("FIST", "Grab File")

        with patch("ui.gesture_overlay.time.time", return_value=1.5):
            overlay.notify("MODE_TOGGLE", "Switching Mode")

        self.assertEqual(overlay.gesture_name, "MODE_TOGGLE")
        self.assertEqual(overlay.action_description, "Switching Mode")
        self.assertAlmostEqual(overlay.triggered_at, 1.5)

    def test_render_draws_without_error(self):
        overlay = GestureOverlay(enabled=True)
        canvas = pygame.Surface((1280, 720), pygame.SRCALPHA)
        with patch("ui.gesture_overlay.time.time", return_value=5.0):
            overlay.notify("SWIPE_LEFT_TWO", "Navigate Back")
        with patch("ui.gesture_overlay.time.time", return_value=5.25):
            overlay.render(canvas)


if __name__ == "__main__":
    unittest.main()
