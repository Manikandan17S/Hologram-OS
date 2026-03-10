import math
from collections import deque

import cv2
import pygame

from config import (
    COLOR_BG,
    CURSOR_TRAIL_LENGTH,
    FULLSCREEN,
    GLOW_ALPHA,
    OVERLAY_ENABLED,
    SCANLINE_ALPHA,
    TARGET_FPS,
    UI_HEIGHT,
    UI_WIDTH,
    VISUAL_PROFILE,
    WINDOW_TITLE,
)
from ui.gesture_overlay import GestureOverlay


class HologramRenderer:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)

        flags = pygame.DOUBLEBUF | pygame.HWSURFACE
        if FULLSCREEN:
            flags |= pygame.FULLSCREEN

        self.screen = pygame.display.set_mode((UI_WIDTH, UI_HEIGHT), flags)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 18, bold=True)
        self.hud_font = pygame.font.SysFont("Consolas", 16, bold=False)
        self.large_font = pygame.font.SysFont("Consolas", 28, bold=True)

        self.frame_index = 0
        self.quality_profile = "high"
        self.trails = {
            "R": deque(maxlen=CURSOR_TRAIL_LENGTH),
            "L": deque(maxlen=CURSOR_TRAIL_LENGTH),
        }
        self.vignette_overlay = self._create_vignette_overlay()
        self.corner_overlay = self._create_corner_brackets_overlay()
        self.mode_switch_until_ms = 0
        self.mode_switch_label = ""
        self.overlay = GestureOverlay(enabled=OVERLAY_ENABLED)

    def _now_ms(self):
        return pygame.time.get_ticks()

    def _create_vignette_overlay(self):
        overlay = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        edge_layers = 16
        for index in range(edge_layers):
            alpha = int((index / max(1, edge_layers - 1)) * 30)
            inset = index * 4
            rect = pygame.Rect(inset, inset, UI_WIDTH - inset * 2, UI_HEIGHT - inset * 2)
            pygame.draw.rect(overlay, (0, 18, 34, alpha), rect, width=5)
        return overlay

    def _create_corner_brackets_overlay(self):
        overlay = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        color = (85, 220, 255, 125)
        length = 42
        margin = 16
        thickness = 2

        # Top-left
        pygame.draw.line(overlay, color, (margin, margin), (margin + length, margin), thickness)
        pygame.draw.line(overlay, color, (margin, margin), (margin, margin + length), thickness)
        # Top-right
        pygame.draw.line(
            overlay,
            color,
            (UI_WIDTH - margin, margin),
            (UI_WIDTH - margin - length, margin),
            thickness,
        )
        pygame.draw.line(
            overlay,
            color,
            (UI_WIDTH - margin, margin),
            (UI_WIDTH - margin, margin + length),
            thickness,
        )
        # Bottom-left
        pygame.draw.line(
            overlay,
            color,
            (margin, UI_HEIGHT - margin),
            (margin + length, UI_HEIGHT - margin),
            thickness,
        )
        pygame.draw.line(
            overlay,
            color,
            (margin, UI_HEIGHT - margin),
            (margin, UI_HEIGHT - margin - length),
            thickness,
        )
        # Bottom-right
        pygame.draw.line(
            overlay,
            color,
            (UI_WIDTH - margin, UI_HEIGHT - margin),
            (UI_WIDTH - margin - length, UI_HEIGHT - margin),
            thickness,
        )
        pygame.draw.line(
            overlay,
            color,
            (UI_WIDTH - margin, UI_HEIGHT - margin),
            (UI_WIDTH - margin, UI_HEIGHT - margin - length),
            thickness,
        )

        return overlay

    def _draw_hologram_overlay(self):
        self.screen.blit(self.vignette_overlay, (0, 0))
        self.screen.blit(self.corner_overlay, (0, 0))

        scanline_step = 8 if self.quality_profile == "high" else 12
        scanline_alpha = max(8, SCANLINE_ALPHA // 4)
        scan_overlay = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        for y in range(0, UI_HEIGHT, scanline_step):
            pygame.draw.line(scan_overlay, (0, 255, 255, scanline_alpha), (0, y), (UI_WIDTH, y), 1)
        self.screen.blit(scan_overlay, (0, 0))

    def set_quality_profile(self, quality_profile):
        self.quality_profile = quality_profile

    def notify_action(self, gesture_name, action_description):
        if self.overlay:
            self.overlay.notify(gesture_name, action_description)

    def draw_camera_feed(self, frame, metrics=None):
        if frame is None:
            self.screen.fill(COLOR_BG)
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_surface = pygame.surfarray.make_surface(frame_rgb.swapaxes(0, 1))
        self.screen.blit(frame_surface, (0, 0))

        tint = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        tint_alpha = 56 if VISUAL_PROFILE == "cinematic" else 28
        if self.quality_profile == "low":
            tint_alpha = int(tint_alpha * 0.7)
        tint.fill((0, 50, 75, tint_alpha))
        self.screen.blit(tint, (0, 0))

        self._draw_hologram_overlay()
        self.frame_index += 1

    def _draw_cursor(self, hand_data, label, ui_scale=1.0):
        if not hand_data:
            self.trails[label].clear()
            return

        cursor = hand_data["cursor"]
        event = hand_data.get("event")
        if event is None:
            gesture = hand_data.get("gesture", "IDLE")
            phase = hand_data.get("phase", "none")
            confidence = hand_data.get("confidence", 0.0)
        else:
            gesture = getattr(event, "gesture", "IDLE")
            phase = getattr(event, "phase", "none")
            confidence = getattr(event, "confidence", 0.0)

        color = (90, 220, 255)
        if gesture == "FIST":
            color = (255, 90, 90)
        elif gesture in ("EXPAND", "PUSH"):
            color = (255, 185, 80)
        elif gesture in ("OPEN_PALM", "DOUBLE_TAP"):
            color = (130, 255, 140)
        elif gesture in ("PULL", "SWIPE_LEFT", "SWIPE_RIGHT", "SWIPE_LEFT_TWO"):
            color = (255, 120, 220)

        base_radius = 10 if phase == "hold" else 12
        radius = max(8, int(base_radius * ui_scale))

        self.trails[label].append(cursor)
        if self.quality_profile != "low":
            trail = list(self.trails[label])
            trail_overlay = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
            for idx, point in enumerate(trail):
                trail_alpha = int((idx / max(1, len(trail))) * 130)
                trail_color = (*color, trail_alpha)
                pygame.draw.circle(trail_overlay, trail_color, point, max(2, idx // 4))
            self.screen.blit(trail_overlay, (0, 0))

        glow = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*color, GLOW_ALPHA), (radius * 3, radius * 3), radius * 2)
        self.screen.blit(glow, (cursor[0] - radius * 3, cursor[1] - radius * 3))

        pygame.draw.circle(self.screen, color, cursor, radius)
        pygame.draw.circle(self.screen, (255, 255, 255), cursor, radius + 2, 1)
        info = self.hud_font.render(
            f"{label}:{gesture}/{phase} {confidence:.2f}", True, (240, 255, 255)
        )
        self.screen.blit(info, (cursor[0] + 14, cursor[1] - 18))

    def _draw_mode_badge(self, mode):
        badge = pygame.Surface((196, 34), pygame.SRCALPHA)
        color = (60, 210, 255) if mode == "FILE_MODE" else (255, 188, 95)
        pygame.draw.rect(badge, (*color, 130), badge.get_rect(), border_radius=10)
        pygame.draw.rect(badge, (255, 255, 255), badge.get_rect(), 1, border_radius=10)
        text = self.hud_font.render(mode, True, (255, 255, 255))
        badge.blit(text, (12, 8))
        self.screen.blit(badge, (UI_WIDTH - 216, 16))

    def _draw_depth_scale_hint(self, ui_scale):
        text = self.hud_font.render(f"Depth Scale: {ui_scale:.2f}", True, (150, 245, 255))
        self.screen.blit(text, (UI_WIDTH - 216, 56))

    def _draw_double_tap_flash(self):
        flash = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        flash.fill((190, 245, 255, 45))
        self.screen.blit(flash, (0, 0))

    def _draw_mode_hold_indicator(self, progress):
        progress = max(0.0, min(1.0, float(progress)))
        if progress <= 0.0:
            return

        width = 240
        x = UI_WIDTH // 2 - width // 2
        y = 26
        pygame.draw.rect(self.screen, (22, 40, 55), (x, y, width, 10), border_radius=5)
        pygame.draw.rect(self.screen, (120, 215, 255), (x, y, int(width * progress), 10), border_radius=5)

    def _draw_mode_switch_animation(self):
        if self._now_ms() > self.mode_switch_until_ms:
            return

        t = max(0.0, (self.mode_switch_until_ms - self._now_ms()) / 900.0)
        panel = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        panel.fill((10, 18, 28, int(58 * t)))
        self.screen.blit(panel, (0, 0))

        txt = self.large_font.render(self.mode_switch_label, True, (255, 235, 180))
        self.screen.blit(
            txt,
            (UI_WIDTH // 2 - txt.get_width() // 2, UI_HEIGHT // 2 - txt.get_height() // 2),
        )

    def _draw_radial_menu(self, radial_state, ui_scale=1.0):
        if not radial_state:
            return

        active = radial_state.get("active", False)
        if not active:
            return

        items = radial_state.get("items", [])
        if not items:
            return

        center = radial_state.get("center", (UI_WIDTH // 2, UI_HEIGHT // 2))
        radius = int(radial_state.get("radius", 110) * ui_scale)
        highlight_index = radial_state.get("highlight_index", -1)
        segment_count = len(items)
        step = (2 * math.pi) / segment_count

        radial_surface = pygame.Surface((UI_WIDTH, UI_HEIGHT), pygame.SRCALPHA)
        for index, item in enumerate(items):
            start = index * step
            end = start + step
            mid = (start + end) / 2

            color = (70, 150, 190, 120)
            if index == highlight_index:
                color = (255, 190, 110, 170)

            points = [center]
            for angle in (start, (start + mid) / 2, mid, (mid + end) / 2, end):
                points.append(
                    (
                        int(center[0] + math.cos(angle) * radius),
                        int(center[1] - math.sin(angle) * radius),
                    )
                )
            pygame.draw.polygon(radial_surface, color, points)
            pygame.draw.polygon(radial_surface, (235, 250, 255, 155), points, 1)

            label_r = int(radius * 0.62)
            label_pos = (
                int(center[0] + math.cos(mid) * label_r),
                int(center[1] - math.sin(mid) * label_r),
            )
            text = item.replace("_", " ").upper()
            text_surf = self.hud_font.render(text[:14], True, (255, 255, 255))
            radial_surface.blit(
                text_surf,
                (label_pos[0] - text_surf.get_width() // 2, label_pos[1] - text_surf.get_height() // 2),
            )

        pygame.draw.circle(radial_surface, (25, 65, 98, 165), center, int(radius * 0.34))
        pygame.draw.circle(radial_surface, (220, 250, 255, 185), center, int(radius * 0.34), 1)
        self.screen.blit(radial_surface, (0, 0))

    def _project_file_object(self, file_obj, ui_scale=1.0):
        z = max(0.52, float(getattr(file_obj, "z", 1.0)))
        inverse_z = 1.0 / z
        center_x = UI_WIDTH * 0.5
        center_y = UI_HEIGHT * 0.5

        # Perspective projection centered on the viewport.
        proj_x = (file_obj.x * inverse_z) + (center_x * (1.0 - inverse_z))
        proj_y = (file_obj.y * inverse_z) + (center_y * (1.0 - inverse_z))
        scale = max(0.5, min(2.0, inverse_z * ui_scale))
        stretch_scale = max(1.0, float(getattr(file_obj, "expand_visual_scale", 1.0)))
        scale = max(0.5, min(2.4, scale * stretch_scale))

        alpha = int(max(76, min(255, 255.0 * (inverse_z ** 0.72))))
        brightness = max(0.45, min(1.5, 1.0 + (inverse_z * 0.3)))
        if stretch_scale > 1.0:
            brightness = min(1.6, brightness + ((stretch_scale - 1.0) * 0.18))
        if getattr(file_obj, "depth_state", "") == "expand_armed":
            scale = max(0.5, min(2.0, scale * 1.05))
            brightness = max(0.45, min(1.6, brightness * 1.08))
        return {
            "x": proj_x,
            "y": proj_y,
            "scale": scale,
            "alpha": alpha,
            "brightness": brightness,
            "z": z,
        }

    def _draw_hud(self, hud_state, metrics):
        panel = pygame.Surface((445, 114), pygame.SRCALPHA)
        pygame.draw.rect(panel, (15, 35, 52, 180), panel.get_rect(), border_radius=12)
        pygame.draw.rect(panel, (95, 235, 255, 255), panel.get_rect(), 1, border_radius=12)
        self.screen.blit(panel, (18, 14))

        current_path = hud_state.get("current_path", "Drives")
        path_label = current_path if len(current_path) < 50 else f"...{current_path[-47:]}"
        fps = metrics.get("fps", 0.0)
        avg_fps = metrics.get("avg_fps", 0.0)
        profile = metrics.get("quality_profile", "high")

        mode = hud_state.get("mode", "FILE_MODE")
        self._draw_mode_badge(mode)
        self._draw_depth_scale_hint(hud_state.get("ui_scale", 1.0))

        self.screen.blit(self.hud_font.render("HOLOGRAM OS V1", True, (180, 255, 255)), (30, 26))
        self.screen.blit(
            self.hud_font.render(f"Path: {path_label}", True, (225, 240, 255)),
            (30, 48),
        )
        self.screen.blit(
            self.hud_font.render(f"FPS {fps:4.1f} | AVG {avg_fps:4.1f} | {profile.upper()}", True, (130, 240, 255)),
            (30, 70),
        )

        status = hud_state.get("status_text", "")
        if status:
            status_surface = self.large_font.render(status, True, (255, 255, 255))
            self.screen.blit(
                status_surface,
                (UI_WIDTH // 2 - status_surface.get_width() // 2, UI_HEIGHT - 58),
            )

        if hud_state.get("delete_progress", 0.0) > 0:
            progress = min(1.0, hud_state["delete_progress"])
            width = 260
            bar_x = UI_WIDTH // 2 - width // 2
            bar_y = UI_HEIGHT - 86
            pygame.draw.rect(self.screen, (50, 30, 30), (bar_x, bar_y, width, 10), border_radius=5)
            fill = int(width * progress)
            fill_color = (255, 180, 80) if progress < 1.0 else (130, 255, 130)
            pygame.draw.rect(self.screen, fill_color, (bar_x, bar_y, fill, 10), border_radius=5)

    def draw_ui(
        self,
        file_objects,
        dustbin,
        right_hand=None,
        left_hand=None,
        hud_state=None,
        metrics=None,
    ):
        hud_state = hud_state or {}
        metrics = metrics or {}
        mode = hud_state.get("mode", "FILE_MODE")
        ui_scale = max(0.7, min(1.35, float(hud_state.get("ui_scale", 1.0))))

        if mode == "FILE_MODE":
            projected = []
            for obj in file_objects:
                projection = self._project_file_object(obj, ui_scale=ui_scale)
                projected.append((projection["z"], obj, projection))

            for _depth, obj, projection in sorted(projected, key=lambda item: item[0], reverse=True):
                obj.draw(self.screen, self.font, projection=projection)
            if dustbin:
                dustbin.draw(self.screen, self.font)

        if hud_state.get("double_tap_flash"):
            self._draw_double_tap_flash()
        if hud_state.get("mode_hold_active"):
            self._draw_mode_hold_indicator(hud_state.get("mode_hold_progress", 0.0))

        if hud_state.get("mode_switch_animation") and self._now_ms() >= self.mode_switch_until_ms:
            self.mode_switch_until_ms = self._now_ms() + 900
            self.mode_switch_label = f"MODE SWITCHED: {mode}"
        self._draw_mode_switch_animation()

        self._draw_cursor(right_hand, "R", ui_scale=ui_scale)
        self._draw_cursor(left_hand, "L", ui_scale=ui_scale)
        self._draw_radial_menu(hud_state.get("radial_menu"), ui_scale=ui_scale)
        self._draw_hud(hud_state, metrics)
        if self.overlay:
            self.overlay.render(self.screen)

    def update_display(self):
        pygame.display.flip()
        self.clock.tick(TARGET_FPS)

    def quit(self):
        pygame.quit()
