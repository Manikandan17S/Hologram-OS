import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List

from config import (
    EXPAND_OPEN_ARM_RATIO,
    EXPAND_OPEN_DISTANCE_RATIO,
    EXPAND_OPEN_MIN_CONFIDENCE,
    EXPAND_OPEN_MIN_STABLE_FRAMES,
    DOUBLE_TAP_MIN_CONFIDENCE,
    DOUBLE_TAP_MOTION_PX,
    DOUBLE_TAP_STABLE_FRAMES,
    DOUBLE_TAP_TAP_TIMEOUT_S,
    DOUBLE_TAP_WINDOW_S,
    EXPAND_CONFIRMATION_FRAMES,
    EXPAND_THRESHOLD,
    FINGER_BENT_ANGLE,
    FINGER_EXTENDED_ANGLE,
    FINGER_SPREAD_BENT_ANGLE_DEG,
    FINGER_SPREAD_EXTENDED_ANGLE_DEG,
    GESTURE_MIN_CONFIDENCE,
    GESTURE_STABLE_MAX_FRAMES,
    GESTURE_STABLE_MIN_FRAMES,
    GESTURE_STABLE_FRAMES,
    GESTURE_STABLE_TARGET_MS,
    HOLD_TIME_FOR_EXPAND,
    MODE_TOGGLE_HOLD_S,
    OPEN_PALM_CONFIRMATION_FRAMES,
    PINCH_RATIO_THRESHOLD,
    SWIPE_MAX_DURATION_S,
    SWIPE_MIN_DISTANCE_PX,
    SWIPE_TWO_MAX_DURATION_S,
    SWIPE_TWO_MIN_DISTANCE_PX,
)
from logic.depth_controller import DepthController
from utils.math_utils import calculate_distance


@dataclass
class GestureEvent:
    gesture: str
    phase: str
    stable_frames: int
    confidence: float
    timestamp: float


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _to_xy(point):
    if isinstance(point, dict):
        return float(point.get("x", 0.0)), float(point.get("y", 0.0))
    if isinstance(point, (list, tuple)):
        if len(point) >= 3:
            return float(point[1]), float(point[2])
        if len(point) >= 2:
            return float(point[0]), float(point[1])
    return 0.0, 0.0


def calculate_angle(a, b, c):
    ax, ay = _to_xy(a)
    bx, by = _to_xy(b)
    cx, cy = _to_xy(c)

    ab = (ax - bx, ay - by)
    cb = (cx - bx, cy - by)

    dot = (ab[0] * cb[0]) + (ab[1] * cb[1])
    mag_ab = math.hypot(*ab)
    mag_cb = math.hypot(*cb)
    if mag_ab * mag_cb == 0:
        return 180.0

    cosine = _clamp(dot / (mag_ab * mag_cb), -1.0, 1.0)
    return math.degrees(math.acos(cosine))


IMPULSE_GESTURES = {
    "SWIPE_LEFT",
    "SWIPE_RIGHT",
    "SWIPE_UP",
    "SWIPE_DOWN",
    "SWIPE_LEFT_TWO",
    "PUSH",
    "PULL",
    "DOUBLE_TAP",
    "MODE_TOGGLE",
}
ADAPTIVE_STABILITY_GESTURES = {
    "FIST",
    "OPEN_PALM",
    "PINCH",
    "PUSH",
    "PULL",
    "SWIPE_LEFT",
    "SWIPE_RIGHT",
    "SWIPE_UP",
    "SWIPE_DOWN",
    "SWIPE_LEFT_TWO",
}


class GestureRecognizer:
    def __init__(self):
        self.states: Dict[str, Dict[str, float]] = {
            "Left": self._initial_state(),
            "Right": self._initial_state(),
        }
        self.depth_controllers = {
            "Left": DepthController(),
            "Right": DepthController(),
        }
        self.mode_hold_started_at = None
        self.mode_hold_progress = 0.0
        self.mode_toggle_emitted = False
        self.pinch_state = {
            "Left": {"active": False, "center": None, "confidence": 0.0, "timestamp": 0.0},
            "Right": {"active": False, "center": None, "confidence": 0.0, "timestamp": 0.0},
        }
        self.expand_open_state = {
            "active": False,
            "initial_distance": 0.0,
            "last_distance": 0.0,
            "ratio": 1.0,
            "stable_frames": 0,
            "emitted": False,
        }

    def _initial_state(self):
        return {
            "last_raw_gesture": "IDLE",
            "confirmed_gesture": "IDLE",
            "stable_frames": 0,
            "expand_frames": 0,
            "open_frames": 0,
            "expand_start_time": 0.0,
            "last_confidence": 0.0,
            "last_swipe_time": -10.0,
            "last_two_swipe_time": -10.0,
            "last_depth_pulse_time": -10.0,
            "index_history": deque(maxlen=8),
            "two_finger_history": deque(maxlen=8),
            "prev_index_y": None,
            "tap_phase": "idle",
            "tap_start_time": 0.0,
            "tap_peak_y": 0.0,
            "tap_count": 0,
            "first_tap_time": 0.0,
            "last_timestamp": None,
            "avg_frame_time_ms": 1000.0 / 60.0,
            "required_stable_frames": GESTURE_STABLE_FRAMES,
            "last_pinch_center": None,
            "last_pinch_ratio": 1.0,
        }

    def _ensure_hand_state(self, hand_type):
        if hand_type not in self.states:
            self.states[hand_type] = self._initial_state()
        if hand_type not in self.depth_controllers:
            self.depth_controllers[hand_type] = DepthController()
        return self.states[hand_type], self.depth_controllers[hand_type]

    def get_depth_state(self, hand_type="Right"):
        controller = self.depth_controllers.get(hand_type)
        if not controller:
            return {"depth": 0.0, "normalized_depth": 0.5, "ui_scale": 1.0, "velocity": 0.0}
        return controller.get_state()

    def get_mode_toggle_progress(self):
        return self.mode_hold_progress

    def get_expand_ratio(self):
        return float(self.expand_open_state.get("ratio", 1.0))

    def detect_mode_toggle(self, right_event, left_event):
        now = time.time()
        right_open = bool(right_event and right_event.gesture == "OPEN_PALM")
        left_open = bool(left_event and left_event.gesture == "OPEN_PALM")
        single_open = (right_open and not left_open) or (left_open and not right_open)

        if single_open:
            if self.mode_hold_started_at is None:
                self.mode_hold_started_at = now
            hold_duration = max(0.0, now - self.mode_hold_started_at)
            self.mode_hold_progress = _clamp(hold_duration / max(0.01, MODE_TOGGLE_HOLD_S))
            stable_frames = int(hold_duration * 30.0)
            if (
                hold_duration >= MODE_TOGGLE_HOLD_S
                and not self.mode_toggle_emitted
                and stable_frames >= GESTURE_STABLE_FRAMES
                and 1.0 >= GESTURE_MIN_CONFIDENCE
            ):
                self.mode_toggle_emitted = True
                return GestureEvent("MODE_TOGGLE", "start", stable_frames, 1.0, now)
        else:
            self.mode_hold_started_at = None
            self.mode_hold_progress = 0.0
            self.mode_toggle_emitted = False

        return GestureEvent("IDLE", "none", 0, 0.0, now)

    def detect_gesture(self, landmarks: List[List[int]], hand_type="Right") -> GestureEvent:
        now = time.time()
        state, depth_controller = self._ensure_hand_state(hand_type)
        self._update_frame_timing(state, now)

        if not landmarks or len(landmarks) < 21:
            self._set_pinch_state(hand_type, False, None, 0.0, now)
            return self._build_event(state, "IDLE", 0.0, now)

        depth_controller.compute_hand_depth(landmarks)
        depth_state = depth_controller.get_state()

        raw_gesture, raw_confidence = self._detect_raw(landmarks, state, depth_state, hand_type, now)
        confirmed_gesture = self._confirm_gesture(state, raw_gesture, now)
        event = self._build_event(state, confirmed_gesture, raw_confidence, now)
        state["last_raw_gesture"] = raw_gesture
        state["last_confidence"] = raw_confidence
        if event.gesture == "PINCH":
            self._set_pinch_state(
                hand_type,
                True,
                state.get("last_pinch_center"),
                event.confidence,
                now,
            )
        else:
            self._set_pinch_state(hand_type, False, None, 0.0, now)
        return event

    def _set_pinch_state(self, hand_type, active, center, confidence, now):
        pinch = self.pinch_state.setdefault(
            hand_type,
            {"active": False, "center": None, "confidence": 0.0, "timestamp": 0.0},
        )
        pinch["active"] = bool(active)
        pinch["center"] = center
        pinch["confidence"] = float(confidence)
        pinch["timestamp"] = float(now)

    def _reset_expand_open_state(self):
        self.expand_open_state["active"] = False
        self.expand_open_state["initial_distance"] = 0.0
        self.expand_open_state["last_distance"] = 0.0
        self.expand_open_state["ratio"] = 1.0
        self.expand_open_state["stable_frames"] = 0
        self.expand_open_state["emitted"] = False

    def detect_expand_open(self, right_hand, left_hand, is_dragging=False, now=None):
        now = time.time() if now is None else float(now)
        if is_dragging:
            self._reset_expand_open_state()
            return GestureEvent("IDLE", "none", 0, 0.0, now)

        right_pinched = self.pinch_state.get("Right", {})
        left_pinched = self.pinch_state.get("Left", {})
        if not right_pinched.get("active") or not left_pinched.get("active"):
            self._reset_expand_open_state()
            return GestureEvent("IDLE", "none", 0, 0.0, now)

        right_center = right_pinched.get("center")
        left_center = left_pinched.get("center")
        if right_center is None or left_center is None:
            self._reset_expand_open_state()
            return GestureEvent("IDLE", "none", 0, 0.0, now)

        distance = calculate_distance(right_center, left_center)
        if distance <= 0:
            self._reset_expand_open_state()
            return GestureEvent("IDLE", "none", 0, 0.0, now)

        if not self.expand_open_state["active"]:
            self.expand_open_state["active"] = True
            self.expand_open_state["initial_distance"] = max(1.0, distance)
            self.expand_open_state["last_distance"] = distance
            self.expand_open_state["ratio"] = 1.0
            self.expand_open_state["stable_frames"] = 1
            self.expand_open_state["emitted"] = False
            return GestureEvent("IDLE", "none", 0, 0.0, now)

        if distance >= self.expand_open_state["last_distance"] * 0.98:
            self.expand_open_state["stable_frames"] += 1
        else:
            self.expand_open_state["stable_frames"] = max(1, self.expand_open_state["stable_frames"] - 1)
        self.expand_open_state["last_distance"] = distance

        initial_distance = max(1.0, self.expand_open_state["initial_distance"])
        ratio = distance / initial_distance
        self.expand_open_state["ratio"] = ratio
        pinch_confidence = min(
            float(right_pinched.get("confidence", 0.0)),
            float(left_pinched.get("confidence", 0.0)),
        )
        expand_confidence = _clamp((ratio - 1.0) / max(0.1, (EXPAND_OPEN_DISTANCE_RATIO - 1.0)))
        confidence = min(pinch_confidence, expand_confidence)

        if (
            not self.expand_open_state["emitted"]
            and self.expand_open_state["stable_frames"] >= EXPAND_OPEN_MIN_STABLE_FRAMES
            and ratio >= EXPAND_OPEN_DISTANCE_RATIO
            and confidence >= EXPAND_OPEN_MIN_CONFIDENCE
        ):
            self.expand_open_state["emitted"] = True
            return GestureEvent(
                "EXPAND_OPEN",
                "start",
                int(self.expand_open_state["stable_frames"]),
                float(confidence),
                now,
            )

        if (
            not self.expand_open_state["emitted"]
            and ratio >= EXPAND_OPEN_ARM_RATIO
        ):
            return GestureEvent(
                "EXPAND_OPEN",
                "hold",
                int(self.expand_open_state["stable_frames"]),
                float(confidence),
                now,
            )

        return GestureEvent("IDLE", "none", 0, 0.0, now)

    def _update_frame_timing(self, state, now):
        last = state.get("last_timestamp")
        if last is not None:
            frame_time_ms = max(4.0, min(100.0, (now - last) * 1000.0))
            prev_avg = float(state.get("avg_frame_time_ms", frame_time_ms))
            state["avg_frame_time_ms"] = (prev_avg * 0.75) + (frame_time_ms * 0.25)
        state["last_timestamp"] = now
        state["required_stable_frames"] = self._required_stable_frames(state)

    def _required_stable_frames(self, state):
        frame_time_ms = max(4.0, float(state.get("avg_frame_time_ms", 1000.0 / 60.0)))
        target_ms = max(40.0, float(GESTURE_STABLE_TARGET_MS))
        frames = int(round(target_ms / frame_time_ms))
        frames = max(int(GESTURE_STABLE_MIN_FRAMES), min(int(GESTURE_STABLE_MAX_FRAMES), frames))
        return frames

    def _classify_finger_state(self, landmarks, mcp_id, pip_id, tip_id, dip_id=None):
        if dip_id is None:
            dip_id = max(pip_id, tip_id - 1)

        mcp_xy = (landmarks[mcp_id][1], landmarks[mcp_id][2])
        pip_xy = (landmarks[pip_id][1], landmarks[pip_id][2])
        dip_xy = (landmarks[dip_id][1], landmarks[dip_id][2])
        tip_xy = (landmarks[tip_id][1], landmarks[tip_id][2])

        pip_valid = calculate_distance(mcp_xy, pip_xy) > 2.0 and calculate_distance(pip_xy, dip_xy) > 2.0
        dip_valid = calculate_distance(pip_xy, dip_xy) > 2.0 and calculate_distance(dip_xy, tip_xy) > 2.0

        pip_joint_angle = calculate_angle(landmarks[mcp_id], landmarks[pip_id], landmarks[dip_id]) if pip_valid else 0.0
        dip_joint_angle = calculate_angle(landmarks[pip_id], landmarks[dip_id], landmarks[tip_id]) if dip_valid else 0.0
        spread_angle = calculate_angle(landmarks[0], landmarks[mcp_id], landmarks[tip_id])
        joint_angle = max(pip_joint_angle, dip_joint_angle)
        composite_angle = max(joint_angle, spread_angle)

        is_extended = (
            joint_angle >= FINGER_EXTENDED_ANGLE
            or spread_angle >= FINGER_SPREAD_EXTENDED_ANGLE_DEG
            or spread_angle >= 105.0
        )
        is_folded = (
            joint_angle <= FINGER_BENT_ANGLE
            and spread_angle <= FINGER_SPREAD_BENT_ANGLE_DEG
        )

        extension_score = _clamp((composite_angle - 120.0) / 48.0)
        fold_score = _clamp((90.0 - composite_angle) / 42.0)
        return is_extended, is_folded, extension_score, fold_score

    def _detect_swipe(self, state, index_tip, now):
        history = state["index_history"]
        history.append((now, index_tip[1], index_tip[2]))
        if len(history) < 2:
            return None, 0.0

        oldest_t, oldest_x, oldest_y = history[0]
        newest_t, newest_x, newest_y = history[-1]
        if newest_t - oldest_t > SWIPE_MAX_DURATION_S:
            while history and (newest_t - history[0][0]) > SWIPE_MAX_DURATION_S:
                history.popleft()
            if len(history) < 2:
                return None, 0.0
            oldest_t, oldest_x, oldest_y = history[0]

        dx = newest_x - oldest_x
        dy = newest_y - oldest_y
        horizontal = abs(dx) >= SWIPE_MIN_DISTANCE_PX and abs(dx) >= abs(dy) * 1.25
        vertical = abs(dy) >= SWIPE_MIN_DISTANCE_PX and abs(dy) >= abs(dx) * 1.25
        if not horizontal and not vertical:
            return None, 0.0
        if now - state["last_swipe_time"] < SWIPE_MAX_DURATION_S:
            return None, 0.0

        state["last_swipe_time"] = now
        history.clear()
        axis_distance = abs(dx) if horizontal else abs(dy)
        confidence = _clamp(axis_distance / max(float(SWIPE_MIN_DISTANCE_PX), 1.0) / 1.1)
        if horizontal:
            return ("SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"), confidence
        return ("SWIPE_DOWN" if dy > 0 else "SWIPE_UP"), confidence

    def _detect_two_finger_swipe_left(self, state, landmarks, finger_states, now):
        two_finger_pose = (
            finger_states[0][0]
            and finger_states[1][0]
            and finger_states[2][1]
            and finger_states[3][1]
        )
        history = state["two_finger_history"]
        if not two_finger_pose:
            history.clear()
            return None

        mid_x = (landmarks[8][1] + landmarks[12][1]) / 2.0
        mid_y = (landmarks[8][2] + landmarks[12][2]) / 2.0
        history.append((now, mid_x, mid_y))
        if len(history) < 2:
            return None

        while history and (now - history[0][0]) > SWIPE_TWO_MAX_DURATION_S:
            history.popleft()
        if len(history) < 2:
            return None

        oldest_t, oldest_x, oldest_y = history[0]
        newest_t, newest_x, newest_y = history[-1]
        dx = newest_x - oldest_x
        dy = newest_y - oldest_y
        dt = max(0.001, newest_t - oldest_t)
        velocity_x = dx / dt

        is_swipe_left = (
            dx <= -SWIPE_TWO_MIN_DISTANCE_PX
            and abs(dx) > abs(dy) * 1.2
            and velocity_x < -SWIPE_TWO_MIN_DISTANCE_PX / max(SWIPE_TWO_MAX_DURATION_S, 0.01)
        )
        if not is_swipe_left:
            return None
        if now - state["last_two_swipe_time"] < SWIPE_TWO_MAX_DURATION_S:
            return None

        state["last_two_swipe_time"] = now
        history.clear()
        confidence = _clamp(abs(dx) / max(float(SWIPE_TWO_MIN_DISTANCE_PX), 1.0) / 1.1)
        return confidence

    def _detect_double_tap(self, state, index_tip, finger_states, hand_type, now):
        if hand_type != "Right":
            state["prev_index_y"] = index_tip[2]
            return None

        index_extended = finger_states[0][0]
        middle_folded = finger_states[1][1]
        ring_folded = finger_states[2][1]
        pinky_folded = finger_states[3][1]
        single_index_pose = index_extended and middle_folded and ring_folded and pinky_folded

        prev_y = state["prev_index_y"]
        state["prev_index_y"] = index_tip[2]
        if prev_y is None:
            return None

        if state["first_tap_time"] and (now - state["first_tap_time"]) > DOUBLE_TAP_WINDOW_S:
            state["tap_count"] = 0
            state["first_tap_time"] = 0.0

        if not single_index_pose:
            state["tap_phase"] = "idle"
            return None

        dy = index_tip[2] - prev_y
        if state["tap_phase"] == "idle":
            if dy > DOUBLE_TAP_MOTION_PX:
                state["tap_phase"] = "down"
                state["tap_start_time"] = now
                state["tap_peak_y"] = index_tip[2]
            return None

        if state["tap_phase"] == "down":
            state["tap_peak_y"] = max(state["tap_peak_y"], index_tip[2])
            if dy < -DOUBLE_TAP_MOTION_PX and (now - state["tap_start_time"]) <= DOUBLE_TAP_TAP_TIMEOUT_S:
                state["tap_phase"] = "idle"
                if state["tap_count"] == 0:
                    # First tap captured immediately.
                    state["tap_count"] = 1
                    state["first_tap_time"] = now
                    return None

                delta = now - state["first_tap_time"]
                if delta <= DOUBLE_TAP_WINDOW_S:
                    state["tap_count"] = 0
                    state["first_tap_time"] = 0.0
                    return _clamp(abs(dy) / max(float(DOUBLE_TAP_MOTION_PX * 2), 1.0))

                # Window expired: reset and treat this as a new first tap.
                state["tap_count"] = 1
                state["first_tap_time"] = now
                return None
            elif (now - state["tap_start_time"]) > DOUBLE_TAP_TAP_TIMEOUT_S:
                state["tap_phase"] = "idle"
        return None

    def _detect_raw(self, landmarks, state, depth_state, hand_type, now):
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        thumb_mcp = landmarks[2]
        index_tip = landmarks[8]
        index_mcp = landmarks[5]

        palm_size = calculate_distance((wrist[1], wrist[2]), (landmarks[9][1], landmarks[9][2]))
        if palm_size == 0:
            palm_size = 1

        pinch_distance = calculate_distance(
            (thumb_tip[1], thumb_tip[2]),
            (index_tip[1], index_tip[2]),
        )
        normalized_pinch = pinch_distance / palm_size
        pinch_base = calculate_distance((index_mcp[1], index_mcp[2]), (wrist[1], wrist[2]))
        if pinch_base <= 0:
            pinch_base = 1.0
        pinch_ratio = pinch_distance / pinch_base
        state["last_pinch_ratio"] = pinch_ratio
        state["last_pinch_center"] = (
            (thumb_tip[1] + index_tip[1]) / 2.0,
            (thumb_tip[2] + index_tip[2]) / 2.0,
        )

        finger_specs = [(5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20)]
        finger_states = []
        extension_scores = []
        fold_scores = []

        for mcp_id, pip_id, dip_id, tip_id in finger_specs:
            is_extended, is_folded, extension_score, fold_score = self._classify_finger_state(
                landmarks, mcp_id, pip_id, tip_id, dip_id=dip_id
            )
            finger_states.append((is_extended, is_folded))
            extension_scores.append(extension_score)
            fold_scores.append(fold_score)

        extended_count = sum(1 for finger_state in finger_states if finger_state[0])
        folded_count = sum(1 for finger_state in finger_states if finger_state[1])
        is_fist = folded_count == 4

        two_swipe_conf = self._detect_two_finger_swipe_left(state, landmarks, finger_states, now)
        if two_swipe_conf is not None:
            return "SWIPE_LEFT_TWO", two_swipe_conf

        index_folded = finger_states[0][1]
        pinch_threshold = float(PINCH_RATIO_THRESHOLD)
        if (
            pinch_ratio <= pinch_threshold
            and not is_fist
            and not index_folded
        ):
            pinch_strength = 1.0 - (pinch_ratio / max(pinch_threshold, 0.001))
            pinch_conf = _clamp(0.58 + (pinch_strength * 0.42))
            return "PINCH", pinch_conf

        swipe_gesture, swipe_conf = self._detect_swipe(state, index_tip, now)
        if swipe_gesture:
            return swipe_gesture, swipe_conf

        double_tap_conf = self._detect_double_tap(state, index_tip, finger_states, hand_type, now)
        if double_tap_conf is not None:
            return "DOUBLE_TAP", double_tap_conf

        if now - state["last_depth_pulse_time"] >= 0.35:
            if depth_state.get("push"):
                state["last_depth_pulse_time"] = now
                return "PUSH", _clamp(depth_state.get("velocity", 0.0) * 4 + 0.5)
            if depth_state.get("pull"):
                state["last_depth_pulse_time"] = now
                return "PULL", _clamp(abs(depth_state.get("velocity", 0.0)) * 4 + 0.5)

        thumb_joint_angle = calculate_angle(landmarks[1], thumb_mcp, thumb_tip)
        thumb_spread_angle = calculate_angle(wrist, thumb_mcp, thumb_tip)
        thumb_extended = max(thumb_joint_angle, thumb_spread_angle) >= FINGER_SPREAD_EXTENDED_ANGLE_DEG

        is_open_palm = extended_count == 4
        is_expand = (
            normalized_pinch > EXPAND_THRESHOLD
            and thumb_extended
            and finger_states[0][0]
            and sum(1 for finger_state in finger_states[1:] if finger_state[1]) >= 2
            and not is_fist
        )

        if is_fist:
            return "FIST", _clamp(sum(fold_scores) / max(len(fold_scores), 1))

        if is_expand:
            spread_conf = _clamp((normalized_pinch - EXPAND_THRESHOLD) / 0.7)
            finger_conf = 1.0 if finger_states[0][0] else 0.0
            return "EXPAND_DETECTED", _clamp((spread_conf * 0.7) + (finger_conf * 0.3))

        if is_open_palm:
            return "OPEN_PALM", _clamp(sum(extension_scores) / max(len(extension_scores), 1))

        return "IDLE", 0.25

    def _confirm_gesture(self, state, raw_gesture, now):
        confirmed = state["confirmed_gesture"]

        if raw_gesture in IMPULSE_GESTURES:
            state["expand_frames"] = 0
            state["open_frames"] = 0
            return raw_gesture

        if raw_gesture == "FIST":
            state["expand_frames"] = 0
            state["open_frames"] = 0
            return "FIST"

        if raw_gesture == "PINCH":
            state["expand_frames"] = 0
            state["open_frames"] = 0
            return "PINCH"

        if raw_gesture == "OPEN_PALM":
            state["expand_frames"] = 0
            state["open_frames"] += 1
            if state["open_frames"] >= OPEN_PALM_CONFIRMATION_FRAMES:
                return "OPEN_PALM"
            return confirmed if confirmed != "IDLE" else "IDLE"

        if raw_gesture == "EXPAND_DETECTED":
            state["open_frames"] = 0
            state["expand_frames"] += 1
            if state["last_raw_gesture"] != "EXPAND_DETECTED":
                state["expand_start_time"] = now
            if state["expand_frames"] >= EXPAND_CONFIRMATION_FRAMES:
                if (now - state["expand_start_time"]) >= HOLD_TIME_FOR_EXPAND:
                    return "EXPAND"
            return confirmed if confirmed != "IDLE" else "IDLE"

        state["open_frames"] = 0
        state["expand_frames"] = 0
        return "IDLE"

    def _build_event(self, state, confirmed_gesture, confidence, now):
        previous_gesture = state["confirmed_gesture"]

        if confirmed_gesture in IMPULSE_GESTURES:
            phase = "start"
            stable_frames = 1
        elif confirmed_gesture != "IDLE":
            if previous_gesture != confirmed_gesture:
                phase = "start"
                stable_frames = 1
            else:
                phase = "hold"
                stable_frames = int(state["stable_frames"]) + 1
        else:
            phase = "end" if previous_gesture != "IDLE" else "none"
            stable_frames = 0

        confidence = _clamp(confidence)
        if confirmed_gesture == "DOUBLE_TAP":
            fixed_required = int(max(2, min(3, DOUBLE_TAP_STABLE_FRAMES)))
            min_conf = min(GESTURE_MIN_CONFIDENCE, DOUBLE_TAP_MIN_CONFIDENCE)
            if confidence < min_conf:
                confirmed_gesture = "IDLE"
                phase = "end" if previous_gesture != "IDLE" else "none"
                stable_frames = 0
            else:
                stable_frames = max(stable_frames, fixed_required)
        elif confirmed_gesture in ADAPTIVE_STABILITY_GESTURES:
            min_conf = GESTURE_MIN_CONFIDENCE
            if confirmed_gesture == "OPEN_PALM":
                min_conf = min(GESTURE_MIN_CONFIDENCE, 0.7)
            elif confirmed_gesture == "PINCH":
                min_conf = min(GESTURE_MIN_CONFIDENCE, 0.5)

            if confidence < min_conf:
                confirmed_gesture = "IDLE"
                phase = "end" if previous_gesture != "IDLE" else "none"
                stable_frames = 0
            else:
                adaptive_required = int(state.get("required_stable_frames", GESTURE_STABLE_FRAMES))
                stable_frames = max(stable_frames, adaptive_required)

        state["stable_frames"] = stable_frames
        state["confirmed_gesture"] = confirmed_gesture

        return GestureEvent(
            gesture=confirmed_gesture,
            phase=phase,
            stable_frames=stable_frames,
            confidence=confidence,
            timestamp=now,
        )
