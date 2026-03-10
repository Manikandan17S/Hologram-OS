from collections import deque

from config import (
    DEPTH_PULL_THRESHOLD,
    DEPTH_PUSH_THRESHOLD,
    DEPTH_SMOOTHING_FRAMES,
    DEPTH_UI_SCALE_MAX,
    DEPTH_UI_SCALE_MIN,
    DEPTH_VELOCITY_SMOOTHING,
)


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


class DepthController:
    def __init__(self, smoothing_frames=DEPTH_SMOOTHING_FRAMES):
        self.raw_history = deque(maxlen=max(5, smoothing_frames))
        self.normalized_history = deque(maxlen=max(5, smoothing_frames))
        self.smoothing_frames = max(3, int(smoothing_frames))
        self.depth_min = None
        self.depth_max = None
        self.last_depth = 0.0
        self.last_norm = 0.5
        self.velocity = 0.0
        self.raw_velocity = 0.0

    def compute_hand_depth(self, landmarks):
        if not landmarks:
            return self.last_depth

        sample_ids = [0, 5, 9, 13, 17, 8]
        z_values = []
        for idx in sample_ids:
            if idx >= len(landmarks):
                continue
            point = landmarks[idx]
            if len(point) > 3:
                z_values.append(-float(point[3]))

        if not z_values:
            return self.last_depth

        raw_depth = sum(z_values) / len(z_values)
        self.raw_history.append(raw_depth)
        smoothed_depth = sum(self.raw_history) / len(self.raw_history)
        if len(self.raw_history) >= 2:
            raw_delta = self.raw_history[-1] - self.raw_history[-2]
            self.raw_velocity = (
                self.raw_velocity * (1.0 - DEPTH_VELOCITY_SMOOTHING)
                + raw_delta * DEPTH_VELOCITY_SMOOTHING
            )
        self.last_depth = smoothed_depth

        normalized = self.normalize_depth(smoothed_depth)
        self.normalized_history.append(normalized)
        if len(self.normalized_history) >= 2:
            instant_velocity = self.normalized_history[-1] - self.normalized_history[-2]
            self.velocity = (
                self.velocity * (1.0 - DEPTH_VELOCITY_SMOOTHING)
                + instant_velocity * DEPTH_VELOCITY_SMOOTHING
            )
        return smoothed_depth

    def normalize_depth(self, depth=None):
        depth = self.last_depth if depth is None else float(depth)

        if self.depth_min is None:
            self.depth_min = depth
            self.depth_max = depth

        self.depth_min = min(self.depth_min, depth)
        self.depth_max = max(self.depth_max, depth)

        # Ensure dynamic range never collapses.
        depth_range = max(0.08, self.depth_max - self.depth_min)
        normalized = (depth - self.depth_min) / depth_range
        self.last_norm = _clamp(normalized)
        return self.last_norm

    def detect_push_gesture(self):
        if len(self.normalized_history) < 3:
            return False
        delta = self.normalized_history[-1] - self.normalized_history[-3]
        raw_delta = self.raw_history[-1] - self.raw_history[-3] if len(self.raw_history) >= 3 else 0.0
        return (delta >= DEPTH_PUSH_THRESHOLD and self.velocity > 0) or (raw_delta >= 0.03 and self.raw_velocity > 0)

    def detect_pull_gesture(self):
        if len(self.normalized_history) < 3:
            return False
        delta = self.normalized_history[-1] - self.normalized_history[-3]
        raw_delta = self.raw_history[-1] - self.raw_history[-3] if len(self.raw_history) >= 3 else 0.0
        return (delta <= DEPTH_PULL_THRESHOLD and self.velocity < 0) or (raw_delta <= -0.03 and self.raw_velocity < 0)

    def get_ui_scale(self):
        span = DEPTH_UI_SCALE_MAX - DEPTH_UI_SCALE_MIN
        return DEPTH_UI_SCALE_MIN + span * self.last_norm

    def get_state(self):
        return {
            "depth": self.last_depth,
            "normalized_depth": self.last_norm,
            "velocity": self.velocity,
            "ui_scale": self.get_ui_scale(),
            "push": self.detect_push_gesture(),
            "pull": self.detect_pull_gesture(),
        }
