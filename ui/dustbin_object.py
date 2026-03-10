import pygame


class Dustbin:
    def __init__(self, x, y, size=120):
        self.rect = pygame.Rect(x, y, size, size)
        self.color_default = (230, 60, 70)
        self.color_hover = (255, 120, 90)
        self.hovered = False
        self.delete_progress = 0.0
        self.armed = False

    def draw(self, surface, font):
        body_color = self.color_hover if self.hovered else self.color_default
        if self.armed:
            body_color = (255, 205, 85)

        glow = pygame.Surface((self.rect.w + 22, self.rect.h + 22), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*body_color, 56), glow.get_rect(), border_radius=18)
        surface.blit(glow, (self.rect.x - 11, self.rect.y - 11))

        pygame.draw.rect(surface, body_color, self.rect, border_radius=12)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2, border_radius=12)

        text = font.render("TRASH", True, (255, 255, 255))
        surface.blit(
            text,
            (
                self.rect.centerx - text.get_width() // 2,
                self.rect.centery - text.get_height() // 2 - 6,
            ),
        )

        bar_w = int(self.rect.w * 0.8)
        bar_x = self.rect.centerx - bar_w // 2
        bar_y = self.rect.bottom - 18
        pygame.draw.rect(surface, (70, 30, 40), (bar_x, bar_y, bar_w, 8), border_radius=4)
        if self.delete_progress > 0:
            fill = int(bar_w * min(1.0, self.delete_progress))
            color = (255, 200, 80) if self.delete_progress < 1.0 else (120, 255, 140)
            pygame.draw.rect(surface, color, (bar_x, bar_y, fill, 8), border_radius=4)
