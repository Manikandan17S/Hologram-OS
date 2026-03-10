import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque

import cv2

from config import (
    ADAPTIVE_LANDMARK_SMOOTHING,
    LANDMARK_SMOOTHING_FACTOR,
    LANDMARK_SMOOTHING_MAX_FACTOR,
    LANDMARK_SMOOTHING_MIN_FACTOR,
    LANDMARK_SMOOTHING_VELOCITY_REF,
    MAX_NUM_HANDS,
    MP_MIN_DETECTION_CONFIDENCE,
    MP_MIN_TRACKING_CONFIDENCE,
    MP_MODEL_COMPLEXITY,
)

# Force CPU path for stability on some Windows + MediaPipe builds.
os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("GLOG_minloglevel", "2")

try:
    import mediapipe as mp
except Exception:  # pragma: no cover - environment dependent
    mp = None


def smooth_landmarks(prev, current, smoothing_factor):
    if current is None:
        return None

    if prev is None or len(prev) != len(current):
        return [point.copy() if isinstance(point, dict) else list(point) for point in current]

    smoothing_factor = max(0.0, min(1.0, float(smoothing_factor)))
    current_weight = 1.0 - smoothing_factor
    smoothed = []
    for p, c in zip(prev, current):
        if isinstance(c, dict):
            merged = dict(c)
            merged["x"] = (float(p.get("x", 0.0)) * smoothing_factor) + (float(c.get("x", 0.0)) * current_weight)
            merged["y"] = (float(p.get("y", 0.0)) * smoothing_factor) + (float(c.get("y", 0.0)) * current_weight)
            merged["z"] = (float(p.get("z", 0.0)) * smoothing_factor) + (float(c.get("z", 0.0)) * current_weight)
            smoothed.append(merged)
            continue

        smoothed.append(
            [
                c[0],
                (float(p[1]) * smoothing_factor) + (float(c[1]) * current_weight),
                (float(p[2]) * smoothing_factor) + (float(c[2]) * current_weight),
                (float(p[3]) * smoothing_factor) + (float(c[3]) * current_weight),
            ]
        )
    return smoothed


def _point_xy(point):
    if isinstance(point, dict):
        return float(point.get("x", 0.0)), float(point.get("y", 0.0))
    return float(point[1]), float(point[2])


def estimate_landmark_velocity(prev, current, sample_ids=(0, 8, 12)):
    if prev is None or current is None:
        return 0.0
    if len(prev) != len(current):
        return 0.0

    ids = [idx for idx in sample_ids if 0 <= idx < len(current)]
    if not ids:
        return 0.0

    total = 0.0
    for idx in ids:
        prev_x, prev_y = _point_xy(prev[idx])
        curr_x, curr_y = _point_xy(current[idx])
        dx = curr_x - prev_x
        dy = curr_y - prev_y
        total += (dx * dx + dy * dy) ** 0.5
    return total / len(ids)


def adaptive_smoothing_factor(
    base_factor,
    velocity,
    min_factor=LANDMARK_SMOOTHING_MIN_FACTOR,
    max_factor=LANDMARK_SMOOTHING_MAX_FACTOR,
    velocity_ref=LANDMARK_SMOOTHING_VELOCITY_REF,
):
    base_factor = max(0.0, min(1.0, float(base_factor)))
    min_factor = max(0.0, min(1.0, float(min_factor)))
    max_factor = max(min_factor, min(1.0, float(max_factor)))
    velocity_ref = max(1.0, float(velocity_ref))

    normalized_velocity = max(0.0, min(1.0, float(velocity) / velocity_ref))
    dynamic_factor = max_factor - ((max_factor - min_factor) * normalized_velocity)
    blended = (base_factor * 0.35) + (dynamic_factor * 0.65)
    return max(min_factor, min(max_factor, blended))


class HandTracker:
    def __init__(self):
        if mp is None:  # pragma: no cover - environment dependent
            raise RuntimeError("mediapipe is required for HandTracker")
        if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "hands"):
            raise RuntimeError(
                "Installed mediapipe build does not include solutions.hands. "
                "Install a compatible mediapipe wheel for this project."
            )

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils

        self.max_num_hands = int(MAX_NUM_HANDS)
        self.min_detection_confidence = float(MP_MIN_DETECTION_CONFIDENCE)
        self.min_tracking_confidence = float(MP_MIN_TRACKING_CONFIDENCE)
        self.requested_model_complexity = int(MP_MODEL_COMPLEXITY)
        self.current_model_complexity = self._normalize_complexity(self.requested_model_complexity)
        if self.current_model_complexity > 1 and not self._supports_complexity_two():
            self.current_model_complexity = 1

        self.hands = None
        self.results = None
        self.prev_landmarks = {"right": None, "left": None}
        self.prev_raw_landmarks = {"right": None, "left": None}
        self.process_times = deque(maxlen=36)
        self._async_queue = queue.Queue(maxsize=2)
        self._async_running = False
        self._async_draw = False
        self._async_thread = None
        self._async_lock = threading.Lock()
        self._async_frame = None
        self._async_hands = []
        self._initialize_hands(self.current_model_complexity)

    def _normalize_complexity(self, complexity):
        return int(max(0, min(2, complexity)))

    def _supports_complexity_two(self):
        # model_complexity=2 can hard-crash some MediaPipe builds.
        probe_code = (
            "import os, cv2, numpy as np, mediapipe as mp; "
            "os.environ['MEDIAPIPE_DISABLE_GPU']='1'; "
            "hands=mp.solutions.hands.Hands(static_image_mode=False,max_num_hands=2,"
            f"model_complexity=2,min_detection_confidence={self.min_detection_confidence},"
            f"min_tracking_confidence={self.min_tracking_confidence}); "
            "frame=np.zeros((64,64,3),dtype=np.uint8); "
            "hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)); "
            "hands.close()"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", probe_code],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _initialize_hands(self, complexity):
        complexity = self._normalize_complexity(complexity)
        if self.hands is not None:
            try:
                self.hands.close()
            except Exception:
                pass

        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.max_num_hands,
            model_complexity=complexity,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )
        self.current_model_complexity = complexity
        self.prev_landmarks["right"] = None
        self.prev_landmarks["left"] = None
        self.prev_raw_landmarks["right"] = None
        self.prev_raw_landmarks["left"] = None

    def _estimated_fps(self):
        if not self.process_times:
            return 60.0
        avg_time = sum(self.process_times) / len(self.process_times)
        if avg_time <= 0:
            return 60.0
        return 1.0 / avg_time

    def _maybe_fallback_model(self):
        if self.current_model_complexity <= 1:
            return
        if len(self.process_times) < 14:
            return
        if self._estimated_fps() < 28.0:
            self._initialize_hands(1)

    def find_hands(self, frame, draw=False):
        started = time.perf_counter()
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(img_rgb)
        elapsed = max(0.0001, time.perf_counter() - started)
        self.process_times.append(elapsed)
        self._maybe_fallback_model()

        if self.results.multi_hand_landmarks:
            for hand_landmarks in self.results.multi_hand_landmarks:
                if draw:
                    self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
        return frame, self.results

    def _async_worker(self):
        while self._async_running:
            try:
                frame = self._async_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if frame is None:
                continue

            processed_frame, _ = self.find_hands(frame, draw=self._async_draw)
            hands_data = self.get_hands(processed_frame.shape)
            with self._async_lock:
                self._async_frame = processed_frame
                self._async_hands = hands_data

    def start_async(self, draw=False):
        if self._async_running:
            return

        self._async_draw = bool(draw)
        self._async_running = True
        self._async_thread = threading.Thread(target=self._async_worker, daemon=True)
        self._async_thread.start()

    def submit_frame(self, frame):
        if not self._async_running or frame is None:
            return False

        try:
            if self._async_queue.full():
                try:
                    self._async_queue.get_nowait()
                except queue.Empty:
                    pass
            self._async_queue.put_nowait(frame.copy())
            return True
        except queue.Full:
            return False

    def read_async(self):
        with self._async_lock:
            if self._async_frame is None:
                return None, []
            return self._async_frame, list(self._async_hands)

    def stop_async(self):
        self._async_running = False
        if self._async_thread and self._async_thread.is_alive():
            self._async_thread.join(timeout=0.4)

    def get_hands(self, frame_shape):
        hands_list = []
        if not self.results:
            return hands_list
        if not self.results.multi_hand_landmarks or not self.results.multi_handedness:
            self.prev_landmarks["right"] = None
            self.prev_landmarks["left"] = None
            self.prev_raw_landmarks["right"] = None
            self.prev_raw_landmarks["left"] = None
            return hands_list

        h, w, _ = frame_shape
        seen_hands = set()
        total = min(len(self.results.multi_hand_landmarks), len(self.results.multi_handedness))
        for idx in range(total):
            hand_landmarks = self.results.multi_hand_landmarks[idx]
            classification = self.results.multi_handedness[idx].classification[0]
            label = classification.label
            hand_key = str(label).strip().lower()

            lm_list = []
            for lm_id, lm in enumerate(hand_landmarks.landmark):
                lm_list.append([lm_id, float(lm.x * w), float(lm.y * h), float(lm.z)])

            prev = self.prev_landmarks.get(hand_key)
            prev_raw = self.prev_raw_landmarks.get(hand_key)
            velocity = estimate_landmark_velocity(prev_raw, lm_list)
            factor = LANDMARK_SMOOTHING_FACTOR
            if ADAPTIVE_LANDMARK_SMOOTHING:
                factor = adaptive_smoothing_factor(
                    LANDMARK_SMOOTHING_FACTOR,
                    velocity,
                    min_factor=LANDMARK_SMOOTHING_MIN_FACTOR,
                    max_factor=LANDMARK_SMOOTHING_MAX_FACTOR,
                    velocity_ref=LANDMARK_SMOOTHING_VELOCITY_REF,
                )

            smoothed = smooth_landmarks(prev, lm_list, factor)
            self.prev_landmarks[hand_key] = smoothed
            self.prev_raw_landmarks[hand_key] = lm_list
            seen_hands.add(hand_key)

            hands_list.append(
                {
                    "type": label,
                    "landmarks": smoothed,
                    "confidence": float(classification.score),
                    "velocity": float(velocity),
                    "smoothing_factor": float(factor),
                }
            )

        for hand_key in ("right", "left"):
            if hand_key not in seen_hands:
                self.prev_landmarks[hand_key] = None
                self.prev_raw_landmarks[hand_key] = None
        return hands_list
