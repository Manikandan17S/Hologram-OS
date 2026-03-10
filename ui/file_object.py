import pygame

from ui.animations import HoverEffect
from ui.icon_loader import get_visual_surface, resolve_file_type


class FileObject:
    def __init__(self, name, path, is_folder, position=(0, 0)):
        self.name = name
        self.path = path
        self.is_folder = is_folder
        self.file_type = resolve_file_type(path, is_folder)
        self.x, self.y = position
        self.z = 1.0
        self.target_z = 1.0
        self.depth_state = "default"
        self.w, self.h = 110, 96
        self.hover_effect = HoverEffect(base_scale=1.0, hover_scale=1.05, speed=0.18)
        self.rect = pygame.Rect(self.x, self.y, self.w, self.h)
        self.display_rect = pygame.Rect(self.x, self.y, self.w, self.h)
        self.current_hover_scale = 1.0
        self.selected = False
        self.dragging = False
        self.drag_offset = (0, 0)
        self._preview_cache_key = None
        self._preview_cache_surface = None

    def update(self):
        scale = self.hover_effect.update()
        if self.dragging or self.depth_state in ("grabbed", "expand_armed"):
            scale *= 1.15
        self.current_hover_scale = scale
        center = self.rect.center
        w = int(self.w * scale)
        h = int(self.h * scale)
        self.display_rect = pygame.Rect(0, 0, w, h)
        self.display_rect.center = center

    def _apply_brightness(self, color, brightness):
        brightness = max(0.35, min(1.4, float(brightness)))
        return tuple(max(0, min(255, int(channel * brightness))) for channel in color)

    def _resolve_draw_rect(self, projection):
        if not projection:
            return self.display_rect

        depth_scale = max(0.5, min(2.0, float(projection.get("scale", 1.0))))
        total_scale = self.current_hover_scale * depth_scale
        draw_w = max(34, int(self.w * total_scale))
        draw_h = max(28, int(self.h * total_scale))
        draw_x = int(projection.get("x", self.x))
        draw_y = int(projection.get("y", self.y))
        return pygame.Rect(draw_x, draw_y, draw_w, draw_h)

    def _panel_colors(self):
        file_palette = {
            "folder": ((35, 195, 245), (125, 245, 255)),
            "image": ((65, 190, 145), (170, 250, 220)),
            "video": ((235, 152, 72), (255, 220, 168)),
            "file": ((120, 168, 230), (214, 236, 255)),
        }
        base_color, edge_color = file_palette.get(self.file_type, file_palette["file"])

        if self.dragging:
            base_color = (255, 140, 60)
            edge_color = (255, 210, 120)
        elif self.selected:
            base_color = (255, 220, 70)
            edge_color = (255, 245, 160)
        return base_color, edge_color

    def _apply_surface_tone(self, visual_surface, brightness, alpha):
        toned = visual_surface.copy()
        if brightness < 1.0:
            amount = max(70, min(255, int(255 * brightness)))
            toned.fill((amount, amount, amount, 255), special_flags=pygame.BLEND_RGBA_MULT)
        elif brightness > 1.0:
            lift = max(0, min(70, int((brightness - 1.0) * 90)))
            if lift > 0:
                toned.fill((lift, lift, lift, 0), special_flags=pygame.BLEND_RGB_ADD)
        if alpha < 255:
            toned.set_alpha(alpha)
        return toned

    def _get_preview_surface(self, preview_size):
        preview_w = max(12, int(preview_size[0]))
        preview_h = max(12, int(preview_size[1]))
        cache_key = (self.path, self.file_type, preview_w, preview_h)
        if self._preview_cache_key == cache_key and self._preview_cache_surface is not None:
            return self._preview_cache_surface

        preview = get_visual_surface(self.path, self.file_type, (preview_w, preview_h))
        self._preview_cache_key = cache_key
        self._preview_cache_surface = preview
        return preview

    def draw(self, surface, font, projection=None):
        alpha = 255
        brightness = 1.0
        if projection:
            alpha = max(70, min(255, int(projection.get("alpha", 255))))
            brightness = float(projection.get("brightness", 1.0))

        draw_rect = self._resolve_draw_rect(projection)
        self.display_rect = draw_rect
        base_color, edge_color = self._panel_colors()

        base_color = self._apply_brightness(base_color, brightness)
        edge_color = self._apply_brightness(edge_color, brightness)

        glow_rect = draw_rect.inflate(16, 16)
        glow_surface = pygame.Surface((glow_rect.w, glow_rect.h), pygame.SRCALPHA)
        glow_alpha = int(38 * (alpha / 255.0))
        pygame.draw.rect(glow_surface, (*edge_color, glow_alpha), glow_surface.get_rect(), border_radius=16)
        surface.blit(glow_surface, glow_rect.topleft)

        body_surface = pygame.Surface((draw_rect.w, draw_rect.h), pygame.SRCALPHA)
        pygame.draw.rect(body_surface, (*base_color, alpha), body_surface.get_rect(), border_radius=14)
        pygame.draw.rect(body_surface, (*edge_color, alpha), body_surface.get_rect(), 2, border_radius=14)
        surface.blit(body_surface, draw_rect.topleft)

        icon_margin_x = max(8, int(draw_rect.w * 0.14))
        icon_margin_y = max(8, int(draw_rect.h * 0.12))
        icon_w = max(18, draw_rect.w - (icon_margin_x * 2))
        icon_h = max(18, int(draw_rect.h * 0.56))
        icon_rect = pygame.Rect(0, 0, icon_w, icon_h)
        icon_rect.centerx = draw_rect.centerx
        icon_rect.top = draw_rect.top + icon_margin_y

        preview_surface = self._get_preview_surface((icon_rect.w, icon_rect.h))
        if preview_surface is not None:
            toned_preview = self._apply_surface_tone(preview_surface, brightness, alpha)
            surface.blit(toned_preview, icon_rect.topleft)

        if self.hover_effect.is_hovered:
            pulse_rect = draw_rect.inflate(10, 10)
            hover_glow = pygame.Surface((pulse_rect.w, pulse_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(hover_glow, (165, 250, 255, 42), hover_glow.get_rect(), border_radius=18)
            pygame.draw.rect(hover_glow, (210, 255, 255, 180), hover_glow.get_rect(), 1, border_radius=18)
            surface.blit(hover_glow, pulse_rect.topleft)

        title = self.name if len(self.name) <= 14 else f"{self.name[:11]}..."
        text_surface = font.render(title, True, self._apply_brightness((235, 245, 255), brightness))
        if alpha < 255:
            text_surface.set_alpha(alpha)
        surface.blit(
            text_surface,
            (
                draw_rect.centerx - text_surface.get_width() // 2,
                draw_rect.bottom + 6,
            ),
        )

    def on_hover_enter(self):
        self.hover_effect.is_hovered = True

    def on_hover_exit(self):
        self.hover_effect.is_hovered = False

    def start_drag(self, cursor_x, cursor_y):
        self.dragging = True
        origin_x = float(self.display_rect.x)
        origin_y = float(self.display_rect.y)
        self.x = origin_x
        self.y = origin_y
        self.rect.topleft = (int(origin_x), int(origin_y))
        self.drag_offset = (origin_x - cursor_x, origin_y - cursor_y)
        self.selected = True

    def end_drag(self):
        self.dragging = False
        self.selected = False

    def move_to(self, x, y):
        self.x = x
        self.y = y
        self.rect.topleft = (int(x), int(y))
        self.display_rect.topleft = (int(x), int(y))
