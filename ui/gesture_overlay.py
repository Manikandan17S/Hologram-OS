import time

import pygame

from config import OVERLAY_DURATION, OVERLAY_ENABLED, OVERLAY_FADE_TIME


class GestureOverlay:
    def __init__(self, enabled=OVERLAY_ENABLED):
        self.enabled = bool(enabled)
        self.visible_duration = float(OVERLAY_DURATION)
        self.fade_in_time = 0.2
        self.fade_out_time = float(OVERLAY_FADE_TIME)

        self.active = False
        self.gesture_name = ""
        self.action_description = ""
        self.triggered_at = 0.0

        self.icon_map = {
            "DOUBLE_TAP": "🤏",
            "PINCH": "🤏",
            "FIST": "🤲",
            "FIST HOLD": "🤲",
            "OPEN_PALM": "✋",
            "SWIPE_LEFT_TWO": "✌",
            "PUSH": "🤚",
            "PULL": "✋",
            "MODE_TOGGLE": "🖐",
            "EXPAND_OPEN": "👐",
        }

        self.title_font = pygame.font.SysFont("Consolas", 20, bold=True)
        self.subtitle_font = pygame.font.SysFont("Consolas", 16, bold=False)

    def notify(self, gesture_name, action_description):
        if not self.enabled:
            return
        self.gesture_name = str(gesture_name or "GESTURE")
        self.action_description = str(action_description or "")
        self.triggered_at = time.time()
        self.active = True

    def _compute_alpha(self, now):
        if not self.active:
            return 0

        elapsed = now - self.triggered_at
        if elapsed < 0:
            return 0

        fade_in_end = self.fade_in_time
        steady_end = fade_in_end + self.visible_duration
        fade_out_end = steady_end + self.fade_out_time

        if elapsed <= fade_in_end:
            return int(255 * (elapsed / max(self.fade_in_time, 0.001)))
        if elapsed <= steady_end:
            return 255
        if elapsed <= fade_out_end:
            remaining = 1.0 - ((elapsed - steady_end) / max(self.fade_out_time, 0.001))
            return int(255 * max(0.0, remaining))

        self.active = False
        return 0

    def render(self, surface):
        if not self.enabled or not self.active:
            return

        alpha = self._compute_alpha(time.time())
        if alpha <= 0:
            return

        icon = self.icon_map.get(self.gesture_name, "")
        title_text = f"{icon} {self.gesture_name}".strip()
        subtitle_text = self.action_description

        title_surf = self.title_font.render(title_text, True, (230, 250, 255))
        subtitle_surf = self.subtitle_font.render(subtitle_text, True, (185, 240, 250))

        panel_width = max(340, title_surf.get_width() + 38, subtitle_surf.get_width() + 38)
        panel_height = 80
        panel_x = (surface.get_width() - panel_width) // 2
        panel_y = surface.get_height() - panel_height - 24

        glow = pygame.Surface((panel_width + 14, panel_height + 14), pygame.SRCALPHA)
        pygame.draw.rect(
            glow,
            (0, 255, 255, int(alpha * 0.28)),
            glow.get_rect(),
            border_radius=18,
        )
        surface.blit(glow, (panel_x - 7, panel_y - 7))

        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        pygame.draw.rect(panel, (15, 40, 58, int(alpha * 0.72)), panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, (95, 240, 255, int(alpha * 0.95)), panel.get_rect(), 2, border_radius=14)

        panel.blit(title_surf, (18, 14))
        panel.blit(subtitle_surf, (18, 45))
        surface.blit(panel, (panel_x, panel_y))
