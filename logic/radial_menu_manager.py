import math
import time

from config import RADIAL_MENU_ITEMS, RADIAL_MENU_RADIUS, RADIAL_MENU_TIMEOUT_MS


class RadialMenuManager:
    def __init__(self, items=None, radius=RADIAL_MENU_RADIUS, timeout_ms=RADIAL_MENU_TIMEOUT_MS):
        self.items = list(items) if items else list(RADIAL_MENU_ITEMS)
        self.radius = int(radius)
        self.timeout_ms = int(timeout_ms)
        self.active = False
        self.center = (0, 0)
        self.highlight_index = -1
        self.opened_at_ms = 0
        self.last_selected_item = None

    def _now_ms(self):
        return int(time.time() * 1000)

    def set_items(self, items):
        self.items = list(items or [])
        self.highlight_index = -1

    def open(self, center, now_ms=None):
        now_ms = self._now_ms() if now_ms is None else now_ms
        self.active = True
        self.center = (int(center[0]), int(center[1]))
        self.highlight_index = -1
        self.opened_at_ms = now_ms
        self.last_selected_item = None

    def close(self):
        self.active = False
        self.highlight_index = -1

    def _calculate_highlight_index(self, center, index_tip):
        if not self.items or not center or not index_tip:
            return -1

        dx = index_tip[0] - center[0]
        dy = center[1] - index_tip[1]
        if dx == 0 and dy == 0:
            return -1

        angle = math.atan2(dy, dx)
        if angle < 0:
            angle += 2 * math.pi

        segment_angle = (2 * math.pi) / len(self.items)
        return int(angle // segment_angle)

    def _base_state(self):
        return {
            "active": self.active,
            "selected_item": None,
            "highlight_index": self.highlight_index,
            "center": self.center,
            "radius": self.radius,
            "items": self.items,
        }

    def update(self, palm_center, index_tip, select_event=None, now_ms=None):
        now_ms = self._now_ms() if now_ms is None else now_ms
        selected_item = None

        if not self.active:
            return self._base_state()

        if now_ms - self.opened_at_ms > self.timeout_ms:
            self.close()
            return self._base_state()

        if palm_center:
            self.center = (int(palm_center[0]), int(palm_center[1]))

        self.highlight_index = self._calculate_highlight_index(self.center, index_tip)

        if select_event and self.highlight_index >= 0:
            gesture = getattr(select_event, "gesture", "")
            phase = getattr(select_event, "phase", "")
            is_confirm = phase == "start" and gesture in ("DOUBLE_TAP", "PINCH")
            if is_confirm:
                selected_item = self.items[self.highlight_index]
                self.last_selected_item = selected_item
                self.close()

        state = self._base_state()
        state["selected_item"] = selected_item
        return state
