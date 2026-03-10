import time
from collections import deque

from config import ADAPTIVE_QUALITY, MIN_FPS, TARGET_FPS


class FPSCounter:
    def __init__(self, max_samples=45):
        self.frame_times = deque(maxlen=max_samples)
        self.start_time = time.perf_counter()
        self.current_fps = 0.0
        self.avg_fps = 0.0
        self.frame_time_ms = 0.0
        self.quality_profile = "high"
        self._quality_lock_frames = 0

    def _update_quality(self):
        if not ADAPTIVE_QUALITY:
            self.quality_profile = "high"
            return

        self._quality_lock_frames = max(0, self._quality_lock_frames - 1)
        if self._quality_lock_frames > 0:
            return

        if self.avg_fps < (MIN_FPS - 4):
            target_quality = "low"
        elif self.avg_fps < (TARGET_FPS * 0.75):
            target_quality = "medium"
        else:
            target_quality = "high"

        if target_quality != self.quality_profile:
            self.quality_profile = target_quality
            self._quality_lock_frames = 20

    def update(self):
        current_time = time.perf_counter()
        delta = current_time - self.start_time
        self.start_time = current_time

        if delta > 0:
            self.frame_times.append(delta)
            self.current_fps = 1.0 / delta
            self.frame_time_ms = delta * 1000.0

        if self.frame_times:
            avg_time = sum(self.frame_times) / len(self.frame_times)
            if avg_time > 0:
                self.avg_fps = 1.0 / avg_time

        self._update_quality()
        return self.current_fps

    def get_fps(self):
        return self.current_fps

    def get_metrics(self):
        return {
            "fps": self.current_fps,
            "avg_fps": self.avg_fps,
            "frame_time_ms": self.frame_time_ms,
            "quality_profile": self.quality_profile,
        }
