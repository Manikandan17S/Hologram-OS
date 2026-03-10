class Animator:
    @staticmethod
    def lerp(start, end, t):
        """Linear interpolation."""
        return start + (end - start) * t

    @staticmethod
    def ease_out(t):
        """Ease out cubic."""
        return 1 - (1 - t) ** 3

class HoverEffect:
    def __init__(self, base_scale=1.0, hover_scale=1.2, speed=0.1):
        self.base_scale = base_scale
        self.hover_scale = hover_scale
        self.current_scale = base_scale
        self.speed = speed
        self.is_hovered = False

    def update(self):
        target = self.hover_scale if self.is_hovered else self.base_scale
        self.current_scale = Animator.lerp(self.current_scale, target, self.speed)
        return self.current_scale
