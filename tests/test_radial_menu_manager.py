import unittest
from types import SimpleNamespace

from logic.radial_menu_manager import RadialMenuManager


class RadialMenuManagerTests(unittest.TestCase):
    def test_highlight_and_select_on_double_tap(self):
        manager = RadialMenuManager(items=["a", "b", "c", "d"], radius=100, timeout_ms=2000)
        manager.open((100, 100), now_ms=1000)

        state_hover = manager.update((100, 100), (200, 100), select_event=None, now_ms=1100)
        self.assertTrue(state_hover["active"])
        self.assertEqual(state_hover["highlight_index"], 0)

        select_event = SimpleNamespace(gesture="DOUBLE_TAP", phase="start")
        state_select = manager.update((100, 100), (200, 100), select_event=select_event, now_ms=1150)
        self.assertFalse(state_select["active"])
        self.assertEqual(state_select["selected_item"], "a")

    def test_auto_close_after_timeout(self):
        manager = RadialMenuManager(items=["x", "y"], timeout_ms=500)
        manager.open((50, 50), now_ms=0)
        state = manager.update((50, 50), (80, 50), select_event=None, now_ms=600)
        self.assertFalse(state["active"])


if __name__ == "__main__":
    unittest.main()
