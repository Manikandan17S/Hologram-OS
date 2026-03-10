import unittest
from unittest.mock import patch

from config import MODE_TOGGLE_HOLD_S
from core.gesture_engine import GestureEvent, GestureRecognizer, calculate_angle


def _base_landmarks():
    landmarks = [[idx, 100, 100, -0.05] for idx in range(21)]
    landmarks[0] = [0, 100, 100, -0.05]
    landmarks[2] = [2, 120, 90, -0.05]
    landmarks[5] = [5, 140, 80, -0.05]
    landmarks[9] = [9, 140, 100, -0.05]
    landmarks[13] = [13, 140, 120, -0.05]
    landmarks[17] = [17, 140, 140, -0.05]
    return landmarks


def fist_landmarks():
    lm = _base_landmarks()
    lm[4] = [4, 112, 98, -0.05]
    lm[8] = [8, 110, 100, -0.05]
    lm[12] = [12, 111, 102, -0.05]
    lm[16] = [16, 108, 98, -0.05]
    lm[20] = [20, 109, 101, -0.05]
    return lm


def open_landmarks(index_x=205):
    lm = _base_landmarks()
    lm[4] = [4, 170, 60, -0.05]
    lm[8] = [8, index_x, 80, -0.05]
    lm[12] = [12, 205, 102, -0.05]
    lm[16] = [16, 195, 126, -0.05]
    lm[20] = [20, 185, 150, -0.05]
    return lm


def expand_landmarks():
    lm = _base_landmarks()
    lm[4] = [4, 175, 70, -0.05]
    lm[8] = [8, 220, 80, -0.05]
    lm[12] = [12, 120, 105, -0.05]
    lm[16] = [16, 117, 110, -0.05]
    lm[20] = [20, 113, 114, -0.05]
    return lm


def single_index_landmarks(index_y=80):
    lm = _base_landmarks()
    lm[4] = [4, 120, 92, -0.05]
    lm[8] = [8, 200, index_y, -0.05]
    lm[12] = [12, 120, 104, -0.05]
    lm[16] = [16, 117, 108, -0.05]
    lm[20] = [20, 113, 112, -0.05]
    return lm


def two_finger_landmarks(index_x=200):
    lm = _base_landmarks()
    lm[4] = [4, 120, 92, -0.05]
    lm[8] = [8, index_x, 80, -0.05]
    lm[12] = [12, index_x - 4, 82, -0.05]
    lm[16] = [16, 106, 102, -0.05]
    lm[20] = [20, 104, 104, -0.05]
    return lm


def pinch_landmarks(center_x=200, center_y=100):
    lm = _base_landmarks()
    lm[4] = [4, center_x, center_y, -0.05]
    lm[8] = [8, center_x, center_y, -0.05]
    lm[12] = [12, center_x + 8, center_y + 18, -0.05]
    lm[16] = [16, center_x + 7, center_y + 22, -0.05]
    lm[20] = [20, center_x + 6, center_y + 26, -0.05]
    return lm


class GestureEngineTests(unittest.TestCase):
    def test_calculate_angle_with_dict_points(self):
        angle = calculate_angle(
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 1.0, "y": 1.0},
        )
        self.assertAlmostEqual(angle, 90.0, places=3)

    def test_angle_based_finger_state_extended_vs_bent(self):
        recognizer = GestureRecognizer()
        is_extended, is_bent, _, _ = recognizer._classify_finger_state(open_landmarks(), 5, 6, 8)
        self.assertTrue(is_extended)
        self.assertFalse(is_bent)

        is_extended, is_bent, _, _ = recognizer._classify_finger_state(fist_landmarks(), 5, 6, 8)
        self.assertFalse(is_extended)
        self.assertTrue(is_bent)

    def test_fist_start_then_hold(self):
        recognizer = GestureRecognizer()
        event_1 = recognizer.detect_gesture(fist_landmarks(), "Right")
        event_2 = recognizer.detect_gesture(fist_landmarks(), "Right")
        open_events = [recognizer.detect_gesture(open_landmarks(), "Right") for _ in range(6)]

        self.assertEqual(event_1.gesture, "FIST")
        self.assertEqual(event_1.phase, "start")
        self.assertEqual(event_2.gesture, "FIST")
        self.assertEqual(event_2.phase, "hold")
        self.assertTrue(any(event.gesture == "OPEN_PALM" for event in open_events))

    def test_expand_requires_hold_and_frames(self):
        recognizer = GestureRecognizer()
        timestamps = [0.00, 0.10, 0.20, 0.32, 0.45, 0.58, 0.72, 0.86]
        with patch("core.gesture_engine.time.time", side_effect=timestamps):
            events = [recognizer.detect_gesture(expand_landmarks(), "Right") for _ in timestamps]

        self.assertTrue(any(event.gesture == "EXPAND" for event in events))
        expand_events = [event for event in events if event.gesture == "EXPAND"]
        self.assertEqual(expand_events[0].phase, "start")

    def test_double_tap_detection(self):
        recognizer = GestureRecognizer()
        timestamps = [0.00, 0.08, 0.16, 0.24, 0.32]
        ys = [80, 110, 80, 112, 80]
        with patch("core.gesture_engine.time.time", side_effect=timestamps):
            events = [recognizer.detect_gesture(single_index_landmarks(index_y=y), "Right") for y in ys]
        self.assertTrue(any(event.gesture == "DOUBLE_TAP" for event in events))

    def test_double_tap_window_expiry_resets_sequence(self):
        recognizer = GestureRecognizer()
        timestamps = [0.00, 0.08, 0.16, 0.70, 0.78]
        ys = [80, 110, 80, 112, 80]
        with patch("core.gesture_engine.time.time", side_effect=timestamps):
            events = [recognizer.detect_gesture(single_index_landmarks(index_y=y), "Right") for y in ys]
        self.assertFalse(any(event.gesture == "DOUBLE_TAP" for event in events))

    def test_double_tap_uses_fixed_stability_not_adaptive_frames(self):
        recognizer = GestureRecognizer()
        state = recognizer.states["Right"]
        state["required_stable_frames"] = 10
        event = recognizer._build_event(state, "DOUBLE_TAP", 1.0, now=0.0)
        self.assertEqual(event.gesture, "DOUBLE_TAP")
        self.assertEqual(event.phase, "start")
        self.assertGreaterEqual(event.stable_frames, 2)
        self.assertLessEqual(event.stable_frames, 3)

    def test_swipe_left_two_detection(self):
        recognizer = GestureRecognizer()
        timestamps = [0.00, 0.06, 0.12, 0.18]
        xs = [240, 200, 150, 100]
        with patch("core.gesture_engine.time.time", side_effect=timestamps):
            events = [recognizer.detect_gesture(two_finger_landmarks(index_x=x), "Right") for x in xs]
        self.assertTrue(any(event.gesture == "SWIPE_LEFT_TWO" for event in events))

    def test_pinch_detection(self):
        recognizer = GestureRecognizer()
        events = [recognizer.detect_gesture(pinch_landmarks(center_x=220), "Right") for _ in range(3)]
        self.assertTrue(any(event.gesture == "PINCH" for event in events))

    def test_expand_open_from_two_hand_pinch(self):
        recognizer = GestureRecognizer()
        events = []
        frames = [
            (pinch_landmarks(240), pinch_landmarks(320)),
            (pinch_landmarks(236), pinch_landmarks(334)),
            (pinch_landmarks(220), pinch_landmarks(360)),
            (pinch_landmarks(210), pinch_landmarks(376)),
        ]

        now = 0.0
        for right_lm, left_lm in frames:
            right_event = recognizer.detect_gesture(right_lm, "Right")
            left_event = recognizer.detect_gesture(left_lm, "Left")
            expand_event = recognizer.detect_expand_open(
                {"event": right_event},
                {"event": left_event},
                is_dragging=False,
                now=now,
            )
            events.append(expand_event)
            now += 0.06

        self.assertTrue(any(event.gesture == "EXPAND_OPEN" and event.phase == "hold" for event in events))
        self.assertTrue(any(event.gesture == "EXPAND_OPEN" for event in events))

    def test_expand_open_blocked_when_dragging(self):
        recognizer = GestureRecognizer()
        right_event = recognizer.detect_gesture(pinch_landmarks(220), "Right")
        left_event = recognizer.detect_gesture(pinch_landmarks(300), "Left")
        event = recognizer.detect_expand_open(
            {"event": right_event},
            {"event": left_event},
            is_dragging=True,
            now=0.0,
        )
        self.assertEqual(event.gesture, "IDLE")

    def test_mode_toggle_single_open_palm_hold(self):
        recognizer = GestureRecognizer()
        open_event = GestureEvent("OPEN_PALM", "hold", 10, 1.0, 0.0)
        hold = float(MODE_TOGGLE_HOLD_S)
        times = [0.0, hold * 0.4, hold * 0.8, hold + 0.2]
        with patch("core.gesture_engine.time.time", side_effect=times):
            events = [recognizer.detect_mode_toggle(open_event, None) for _ in times]
        self.assertTrue(any(event.gesture == "MODE_TOGGLE" for event in events))

    def test_push_gesture_from_depth_state(self):
        recognizer = GestureRecognizer()
        controller = recognizer.depth_controllers["Right"]
        with patch.object(controller, "compute_hand_depth"), patch.object(
            controller,
            "get_state",
            return_value={
                "push": True,
                "pull": False,
                "velocity": 0.4,
                "depth": 0.2,
                "normalized_depth": 0.7,
                "ui_scale": 1.1,
            },
        ):
            event = recognizer.detect_gesture(open_landmarks(), "Right")
        self.assertEqual(event.gesture, "PUSH")
        self.assertEqual(event.phase, "start")


if __name__ == "__main__":
    unittest.main()
