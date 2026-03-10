from config import UI_HEIGHT, UI_WIDTH

class GridSystem:
    def __init__(self, cols=5, margin=20, item_size=(100, 100)):
        self.cols = cols
        self.margin = margin
        self.item_w, self.item_h = item_size
        self.start_x = 50
        self.start_y = 50

    def _effective_cols(self):
        available = max(1, UI_WIDTH - self.start_x * 2)
        slot = max(1, self.item_w + self.margin)
        auto_cols = max(1, available // slot)
        return max(1, min(self.cols, auto_cols))

    def get_position(self, index):
        """
        Returns (x, y) for the item at index.
        """
        cols = self._effective_cols()
        col = index % cols
        row = index // cols

        x = self.start_x + col * (self.item_w + self.margin)
        y = self.start_y + row * (self.item_h + self.margin)

        return x, y
