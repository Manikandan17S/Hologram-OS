import sys

import pygame


from config import CAMERA_INDEX, UI_HEIGHT, UI_WIDTH
from core.camera import WebcamStream
from core.gesture_engine import GestureRecognizer
from core.hand_tracker import HandTracker
from core.performance_monitor import FPSCounter
from core.smoothing import Stabilizer
from logic.interaction_manager import DESKTOP_MODE, InteractionManager
from ui.dustbin_object import Dustbin
from ui.hologram_renderer import HologramRenderer


def main():
    # 1. Initialize Core
    camera = WebcamStream(src=CAMERA_INDEX).start()
    tracker = HandTracker()
    tracker.start_async(draw=True)
    gesture_engine = GestureRecognizer()

    stabilizer_right = Stabilizer()
    stabilizer_left = Stabilizer()
    desktop_cursor_state = {"Right": None, "Left": None}
    fps_counter = FPSCounter()

    # 2. Initialize UI & Logic
    renderer = HologramRenderer()
    manager = InteractionManager(overlay=renderer.overlay)
    dustbin = Dustbin(UI_WIDTH - 160, UI_HEIGHT - 160)

    frame_state = {
        "hands": {"right": None, "left": None},
        "hud": {},
        "performance": {},
    }

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        latest_frame = camera.read()
        if latest_frame is None:
            continue
        tracker.submit_frame(latest_frame)

        frame, hands_data = tracker.read_async()
        if frame is None:
            continue

        right_hand_input = None
        left_hand_input = None

        for hand in hands_data:
            hand_type = hand["type"]
            landmarks = hand["landmarks"]
            tracking_confidence = float(hand.get("confidence", 0.0))

            gesture_event = gesture_engine.detect_gesture(landmarks, hand_type)
            depth_state = gesture_engine.get_depth_state(hand_type)
            raw_x, raw_y = landmarks[8][1], landmarks[8][2]
            palm_x, palm_y = landmarks[0][1], landmarks[0][2]

            if hand_type not in ("Right", "Left"):
                continue

            stabilizer = stabilizer_right if hand_type == "Right" else stabilizer_left
            smoothed = stabilizer.update((raw_x, raw_y))
            if not smoothed:
                continue

            if manager.mode == DESKTOP_MODE:
                cursor_smoothing = 0.22
                previous_cursor = desktop_cursor_state.get(hand_type)
                if previous_cursor is None:
                    smoothed_cursor = (float(smoothed[0]), float(smoothed[1]))
                else:
                    smoothed_cursor = (
                        previous_cursor[0] + ((float(smoothed[0]) - previous_cursor[0]) * cursor_smoothing),
                        previous_cursor[1] + ((float(smoothed[1]) - previous_cursor[1]) * cursor_smoothing),
                    )
                desktop_cursor_state[hand_type] = smoothed_cursor
            else:
                desktop_cursor_state[hand_type] = None
                smoothed_cursor = (float(smoothed[0]), float(smoothed[1]))

            event_confidence = (gesture_event.confidence + tracking_confidence) / 2.0
            input_data = {
                "cursor": (int(smoothed_cursor[0]), int(smoothed_cursor[1])),
                "palm_center": (int(palm_x), int(palm_y)),
                "pinch_center": (
                    int((landmarks[4][1] + landmarks[8][1]) * 0.5),
                    int((landmarks[4][2] + landmarks[8][2]) * 0.5),
                ),
                "event": gesture_event,
                "gesture": gesture_event.gesture,
                "phase": gesture_event.phase,
                "stable_frames": gesture_event.stable_frames,
                "confidence": min(1.0, event_confidence),
                "depth": float(depth_state.get("depth", 0.0)),
                "normalized_depth": float(depth_state.get("normalized_depth", 0.5)),
                "ui_scale": float(depth_state.get("ui_scale", 1.0)),
                "hand_depth_z": float(-landmarks[9][3]),
            }

            if hand_type == "Right":
                right_hand_input = input_data
            else:
                left_hand_input = input_data

        right_event = right_hand_input["event"] if right_hand_input else None
        left_event = left_hand_input["event"] if left_hand_input else None
        mode_toggle_event = gesture_engine.detect_mode_toggle(right_event, left_event)
        expand_open_event = gesture_engine.detect_expand_open(
            right_hand_input,
            left_hand_input,
            is_dragging=bool(manager.dragging_object),
        )
        print("EXPAND EVENT:", expand_open_event.gesture, expand_open_event.phase)
        mode_hold_progress = gesture_engine.get_mode_toggle_progress()

        hud_state = manager.handle_input(
            right_hand_input,
            left_hand_input,
            dustbin,
            mode_toggle_event=mode_toggle_event,
            expand_open_event=expand_open_event,
            mode_hold_progress=mode_hold_progress,
        )
        fps_counter.update()
        metrics = fps_counter.get_metrics()
        renderer.set_quality_profile(metrics["quality_profile"])

        frame_state["hands"]["right"] = right_hand_input
        frame_state["hands"]["left"] = left_hand_input
        frame_state["hud"] = hud_state
        frame_state["performance"] = metrics

        renderer.draw_camera_feed(frame, metrics=metrics)
        renderer.draw_ui(
            manager.file_objects,
            dustbin,
            frame_state["hands"]["right"],
            frame_state["hands"]["left"],
            hud_state=frame_state["hud"],
            metrics=frame_state["performance"],
        )

        pygame.display.set_caption(
            f"Hologram OS | FPS: {metrics['fps']:.1f} | AVG: {metrics['avg_fps']:.1f} | {metrics['quality_profile']}"
        )
        renderer.update_display()

    tracker.stop_async()
    camera.stop()
    renderer.quit()
    sys.exit()


if __name__ == "__main__":
    main()
