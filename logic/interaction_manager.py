import os
import time
import math
from dataclasses import dataclass

from config import (
    ACTION_COOLDOWN_MS,
    DELETE_HOLD_MS,
    DESKTOP_CURSOR_SMOOTHING,
    DESKTOP_SCROLL_DELTA,
    MODE_TOGGLE_COOLDOWN_MS,
    NAV_COOLDOWN_MS,
    SAFE_DELETE_MODE,
    EXPAND_OPEN_DISTANCE_RATIO,
    GRAB_BASE_Z,
    GRAB_DEPTH_SCALE,
    GRAB_FOLLOW_SMOOTHING,
    GRAB_RADIUS,
    UI_HEIGHT,
    UI_WIDTH,
)
from filesystem.drive_scanner import get_drives
from filesystem.file_operations import delete_item, open_file
from filesystem.folder_navigator import FolderNavigator
from logic.desktop_controller import DesktopController
from logic.radial_menu_manager import RadialMenuManager
from logic.spatial_layout_engine import SpatialLayoutEngine
from ui.file_object import FileObject
from ui.layout_engine import GridSystem
from utils.collision import point_vs_rect, rect_vs_rect


FILE_MODE = "FILE_MODE"
DESKTOP_MODE = "DESKTOP_MODE"


@dataclass
class InputEvent:
    gesture: str = "IDLE"
    phase: str = "none"
    stable_frames: int = 0
    confidence: float = 0.0
    timestamp: float = 0.0


class InteractionManager:
    def __init__(self, overlay=None):
        self.navigator = FolderNavigator()
        self.grid_system = GridSystem(cols=6)
        self.file_objects = []
        self.folder_history = []
        self.scroll_offset = 0.0
        self.scroll_min_offset = 0.0
        self.scroll_max_offset = 0.0
        self.dragging_object = None
        self.grabbed_object = None
        self.expand_armed = False
        self.expand_anchor = None
        self.expand_initial_distance = None
        self.expand_visual_ratio = 1.0
        self.current_drives = []
        self.overlay = overlay
        self.last_overlay_key = ""
        self.last_overlay_emit_ms = 0

        self.desktop_controller = DesktopController()
        self.radial_menu = RadialMenuManager()
        self.radial_state = self.radial_menu._base_state()
        self.spatial_engine = SpatialLayoutEngine()
        self.mode = FILE_MODE
        self.last_frame_ms = None

        self.cooldowns = {"open": 0, "navigate": 0, "mode_toggle": 0}
        self.delete_hold_started_ms = None
        self.delete_progress = 0.0
        self.delete_armed = False
        self.push_pulse_until_ms = 0
        self.double_tap_flash_until_ms = 0
        self.mode_switch_until_ms = 0

        self.status_text = ""
        self.status_expires_ms = 0
        self.frame_state = {}
        self.desktop_open_palm_started_ms = None
        self.desktop_volume_anchor_y = None
        self.load_drives()

    def _now_ms(self):
        return int(time.time() * 1000)

    def _set_status(self, message, duration_ms=1300, now_ms=None):
        self.status_text = message
        base_time = self._now_ms() if now_ms is None else now_ms
        self.status_expires_ms = base_time + duration_ms

    def _emit_action(self, gesture_name, action_description, now_ms=None, force=False):
        if not self.overlay:
            return
        now_ms = self._now_ms() if now_ms is None else now_ms
        key = f"{gesture_name}|{action_description}"
        if not force and key == self.last_overlay_key and (now_ms - self.last_overlay_emit_ms) < 280:
            return
        self.last_overlay_key = key
        self.last_overlay_emit_ms = now_ms
        try:
            self.overlay.notify(gesture_name, action_description)
        except Exception:
            # Overlay failures should never break interaction routing.
            pass

    def _current_status(self, now_ms):
        if now_ms <= self.status_expires_ms:
            return self.status_text
        return ""

    def _can_fire(self, action_name, now_ms, cooldown_ms):
        last_trigger = self.cooldowns.get(action_name, 0)
        if now_ms - last_trigger >= cooldown_ms:
            self.cooldowns[action_name] = now_ms
            return True
        return False

    def _event_from_hand(self, hand):
        if not hand:
            return InputEvent()

        event = hand.get("event")
        if event is not None:
            return InputEvent(
                gesture=getattr(event, "gesture", "IDLE"),
                phase=getattr(event, "phase", "none"),
                stable_frames=int(getattr(event, "stable_frames", 0)),
                confidence=float(getattr(event, "confidence", 0.0)),
                timestamp=float(getattr(event, "timestamp", 0.0)),
            )

        gesture = hand.get("gesture", "IDLE")
        phase = hand.get("phase", "none" if gesture == "IDLE" else "hold")
        return InputEvent(
            gesture=gesture,
            phase=phase,
            stable_frames=int(hand.get("stable_frames", 0)),
            confidence=float(hand.get("confidence", 0.0)),
            timestamp=float(hand.get("timestamp", 0.0)),
        )

    def _mode_debug_name(self):
        if self.mode == FILE_MODE:
            return "file"
        if self.mode == DESKTOP_MODE:
            return "desktop"
        return str(self.mode)

    def _clear_delete_hold(self):
        self.delete_hold_started_ms = None
        self.delete_progress = 0.0
        self.delete_armed = False

    def _clear_grabbed_state(self, reset_depth=True):
        if self.grabbed_object and reset_depth and not self.spatial_engine.has_focus():
            self.spatial_engine.animate_depth_transition(
                self.grabbed_object,
                self.spatial_engine.base_z,
                "default",
            )
        if self.grabbed_object:
            self.grabbed_object.expand_visual_scale = 1.0
        self.grabbed_object = None
        self.expand_armed = False
        self.expand_anchor = None
        self.expand_initial_distance = None
        self.expand_visual_ratio = 1.0

    def _start_spatial_grab(self, hovered_obj, now_ms):
        if not hovered_obj:
            return False
        if self.dragging_object:
            return False
        self.grabbed_object = hovered_obj
        self.expand_armed = False
        self.expand_anchor = None
        self.expand_initial_distance = None
        self.expand_visual_ratio = 1.0
        self.grabbed_object.expand_visual_scale = 1.0
        self.spatial_engine.focus_object = None
        for obj in self.file_objects:
            if obj is hovered_obj:
                self.spatial_engine.animate_depth_transition(obj, 0.65, "grabbed")
            else:
                self.spatial_engine.animate_depth_transition(obj, self.spatial_engine.base_z, "default")
        self._set_status(f"Grabbed: {hovered_obj.name}", now_ms=now_ms)
        self._emit_action("PINCH", "Grab Layer", now_ms=now_ms, force=True)
        return True

    def _screen_to_world(self, pinch_x, pinch_y, z_value):
        z_value = max(0.52, float(z_value))
        inverse_z = 1.0 / z_value
        center_x = UI_WIDTH * 0.5
        center_y = UI_HEIGHT * 0.5

        world_x = (float(pinch_x) - center_x * (1.0 - inverse_z)) / inverse_z
        world_y = (float(pinch_y) - center_y * (1.0 - inverse_z)) / inverse_z
        return world_x, world_y

    def _reset_scroll_state(self):
        self.scroll_offset = 0.0
        self.scroll_min_offset = 0.0
        self.scroll_max_offset = 0.0

    def _update_scroll_bounds(self):
        total_items = len(self.file_objects)
        if total_items <= 0:
            self._reset_scroll_state()
            return

        cols = max(1, int(self.grid_system._effective_cols()))
        rows = (total_items + cols - 1) // cols
        slot_h = int(self.grid_system.item_h + self.grid_system.margin)
        content_bottom = self.grid_system.start_y + max(0, rows - 1) * slot_h + self.grid_system.item_h
        viewport_bottom = UI_HEIGHT - 140
        self.scroll_min_offset = min(0.0, float(viewport_bottom - content_bottom))
        self.scroll_max_offset = 0.0
        self.scroll_offset = max(self.scroll_min_offset, min(self.scroll_max_offset, self.scroll_offset))

    def _apply_scroll_offset(self):
        for obj in self.file_objects:
            if obj is self.dragging_object or obj is self.grabbed_object:
                continue
            base_x = float(getattr(obj, "base_x", obj.x))
            base_y = float(getattr(obj, "base_y", obj.y))
            obj.x = base_x
            obj.y = base_y + self.scroll_offset
            obj.rect.topleft = (int(obj.x), int(obj.y))
            obj.display_rect.topleft = obj.rect.topleft

    def _scroll_files(self, delta, now_ms):
        if not self.file_objects:
            return False
        previous_offset = float(self.scroll_offset)
        self.scroll_offset = max(
            self.scroll_min_offset,
            min(self.scroll_max_offset, previous_offset + float(delta)),
        )
        if abs(self.scroll_offset - previous_offset) < 0.5:
            return False
        self._apply_scroll_offset()
        self._set_status("Scroll files", duration_ms=500, now_ms=now_ms)
        return True

    def _find_grab_candidate(self, cursor_pos, radius):
        if not cursor_pos:
            return None

        best_obj = None
        best_distance = float("inf")
        radius = max(0.0, float(radius))
        cursor_x, cursor_y = float(cursor_pos[0]), float(cursor_pos[1])
        for obj in self.file_objects:
            if point_vs_rect(cursor_pos, obj.display_rect):
                return obj
            magnetic_rect = obj.display_rect.inflate(int(radius * 2), int(radius * 2))
            if not point_vs_rect(cursor_pos, magnetic_rect):
                continue
            center_x, center_y = obj.display_rect.center
            distance = math.hypot(center_x - cursor_x, center_y - cursor_y)
            if distance < best_distance:
                best_distance = distance
                best_obj = obj
        return best_obj

    def _is_expand_open_start(self, expand_open_event):
        if not expand_open_event:
            return False
        if getattr(expand_open_event, "gesture", "IDLE") != "EXPAND_OPEN":
            return False
        return getattr(expand_open_event, "phase", "none") == "start"

    def _is_expand_open_hold(self, expand_open_event):
        if not expand_open_event:
            return False
        if getattr(expand_open_event, "gesture", "IDLE") != "EXPAND_OPEN":
            return False
        return getattr(expand_open_event, "phase", "none") == "hold"

    def _handle_expand_open(self, expand_open_event, now_ms, two_hand_pinch_active=False):
        if not two_hand_pinch_active:
            return
        if not self._is_expand_open_start(expand_open_event):
            return
        print("EXPAND STARTED, grabbed:", self.grabbed_object)
        if not self.grabbed_object:
            return
        self.expand_armed = False
        self.expand_anchor = None
        self.expand_initial_distance = None
        self.expand_visual_ratio = 1.0
        if self.spatial_engine.set_focus_layer(self.grabbed_object):
            folder_or_file = self.grabbed_object
            self._set_status(f"Expanded open: {folder_or_file.name}", now_ms=now_ms)
            if folder_or_file.is_folder:
                self._open_hovered_item(
                    folder_or_file,
                    now_ms,
                    gesture_name="EXPAND_OPEN",
                    overlay_desc="Open Folder",
                )
            else:
                try:
                    os.startfile(folder_or_file.path)
                    self._emit_action("EXPAND_OPEN", "Open File", now_ms=now_ms, force=True)
                except OSError as exc:
                    self._set_status(f"Open failed: {exc}", now_ms=now_ms)
        self._clear_grabbed_state(reset_depth=False)

    def _build_file_objects(self, items):
        self.file_objects = []
        for index, item in enumerate(items):
            x, y = self.grid_system.get_position(index)
            is_folder = item["type"] == "folder"
            file_obj = FileObject(item["name"], item["path"], is_folder, (x, y))
            file_obj.base_x = float(x)
            file_obj.base_y = float(y)
            file_obj.expand_visual_scale = 1.0
            self.file_objects.append(file_obj)
        self.spatial_engine.bind_objects(self.file_objects)
        self._reset_scroll_state()
        self._update_scroll_bounds()
        self._apply_scroll_offset()
        self.grabbed_object = None
        self.expand_armed = False
        self.expand_anchor = None
        self.expand_initial_distance = None
        self.expand_visual_ratio = 1.0

    def load_drives(self):
        drives = get_drives()
        self.current_drives = drives
        items = [{"name": drive, "path": drive, "type": "folder"} for drive in drives]
        self._build_file_objects(items)
        self.navigator.current_path = None

    def load_folder(self, path):
        if self.navigator.set_path(path):
            self._build_file_objects(self.navigator.list_contents())
            return True
        return False

    def _reload_current_path(self):
        if self.navigator.current_path:
            self._build_file_objects(self.navigator.list_contents())
        else:
            self.load_drives()

    def navigate_back(self, now_ms):
        print("HISTORY STACK:", self.folder_history)
        if self.folder_history:
            previous_path = self.folder_history.pop()
            if previous_path:
                if self.load_folder(previous_path):
                    self._reload_current_path()
                    self._set_status("Navigated back", now_ms=now_ms)
                    return True
                self._set_status("Back target unavailable", now_ms=now_ms)
                return False

            self.load_drives()
            self._reload_current_path()
            self._set_status("Drive hub", now_ms=now_ms)
            return True

        self._set_status("Already at root folder", now_ms=now_ms)
        return False

    def _update_hover_state(self, cursor_pos):
        hovered_obj = None
        for obj in self.file_objects:
            if point_vs_rect(cursor_pos, obj.display_rect):
                obj.on_hover_enter()
                hovered_obj = obj
            else:
                obj.on_hover_exit()
        return hovered_obj

    def _end_drag(self):
        if self.dragging_object:
            self.dragging_object.end_drag()
        self.dragging_object = None
        self._clear_delete_hold()

    def _update_delete_hold(self, now_ms, dustbin):
        if not self.dragging_object or not dustbin:
            self._clear_delete_hold()
            return

        dustbin.hovered = rect_vs_rect(self.dragging_object.display_rect, dustbin.rect)
        if not dustbin.hovered:
            self._clear_delete_hold()
            return

        if self.delete_hold_started_ms is None:
            self.delete_hold_started_ms = now_ms

        elapsed = now_ms - self.delete_hold_started_ms
        self.delete_progress = min(1.0, elapsed / max(1, DELETE_HOLD_MS))
        self.delete_armed = self.delete_progress >= 1.0

    def _release_drag(self, dustbin, now_ms):
        if not self.dragging_object:
            return

        dropped_obj = self.dragging_object
        should_delete = dustbin and rect_vs_rect(dropped_obj.display_rect, dustbin.rect) and self.delete_armed

        if should_delete:
            success, message = delete_item(dropped_obj.path, mode=SAFE_DELETE_MODE)
            self._set_status(message, 1700, now_ms=now_ms)
            self._emit_action("OPEN_PALM", "Delete Item", now_ms=now_ms, force=True)
            if success and dropped_obj in self.file_objects:
                self.file_objects.remove(dropped_obj)
        else:
            self._set_status(f"Dropped {dropped_obj.name}", now_ms=now_ms)
            self._emit_action("OPEN_PALM", "Drop Item", now_ms=now_ms)

        self._end_drag()

    def _toggle_mode(self, now_ms):
        self.mode = DESKTOP_MODE if self.mode == FILE_MODE else FILE_MODE
        self.mode_switch_until_ms = now_ms + 900
        self.radial_menu.close()
        self.radial_state = self.radial_menu._base_state()
        self._clear_grabbed_state(reset_depth=True)
        self._set_status(f"Mode: {self.mode}", now_ms=now_ms)
        self._emit_action("MODE_TOGGLE", "Switching Mode", now_ms=now_ms, force=True)

    def _run_desktop_action(self, action_name, now_ms):
        mapping = {
            "open_app": lambda: self.desktop_controller.open_application("explorer", now_ms=now_ms),
            "close_window": lambda: self.desktop_controller.close_active_window(now_ms=now_ms),
            "next_window": lambda: self.desktop_controller.switch_window_next(now_ms=now_ms),
            "prev_window": lambda: self.desktop_controller.switch_window_previous(now_ms=now_ms),
            "volume_up": lambda: self.desktop_controller.control_volume(2, now_ms=now_ms),
            "volume_down": lambda: self.desktop_controller.control_volume(-2, now_ms=now_ms),
            "play_pause": lambda: self.desktop_controller.media_play_pause(now_ms=now_ms),
            "scroll_down": lambda: self.desktop_controller.system_scroll(-DESKTOP_SCROLL_DELTA, now_ms=now_ms),
            "scroll_up": lambda: self.desktop_controller.system_scroll(DESKTOP_SCROLL_DELTA, now_ms=now_ms),
        }
        action_fn = mapping.get(action_name)
        if not action_fn:
            return f"No desktop action: {action_name}"
        return action_fn()

    def _open_hovered_item(self, hovered_obj, now_ms, gesture_name="EXPAND", overlay_desc=None):
        if not hovered_obj:
            return
        if not self._can_fire("open", now_ms, ACTION_COOLDOWN_MS):
            return
        if hovered_obj.is_folder:
            previous_path = self.navigator.current_path
            # store history BEFORE navigation
            # Only push valid paths to history.
            if previous_path != hovered_obj.path:
                self.folder_history.append(previous_path)
            if self.load_folder(hovered_obj.path):
                self._set_status(f"Opened {hovered_obj.name}", now_ms=now_ms)
                self._emit_action(gesture_name, overlay_desc or "Open Folder", now_ms=now_ms, force=True)
        else:
            success, message = open_file(hovered_obj.path)
            self._set_status(message if success else f"Open failed: {message}", now_ms=now_ms)
            if success:
                self._emit_action(gesture_name, overlay_desc or "Open File", now_ms=now_ms, force=True)

    def _handle_push_action(self, right_event, hovered_obj, now_ms):
        if right_event.gesture == "PUSH" and right_event.phase == "start":
            self.push_pulse_until_ms = now_ms + 260
            if self.mode == FILE_MODE:
                if hovered_obj and hovered_obj.is_folder:
                    if self.spatial_engine.set_focus_layer(hovered_obj):
                        self._set_status(f"Focused layer: {hovered_obj.name}", now_ms=now_ms)
                        self._emit_action("PUSH", "Focus Layer", now_ms=now_ms, force=True)
                else:
                    self._open_hovered_item(hovered_obj, now_ms, gesture_name="PUSH", overlay_desc="Open File")
            else:
                if self.radial_menu.active and self.radial_menu.highlight_index >= 0:
                    selected = self.radial_menu.items[self.radial_menu.highlight_index]
                    message = self._run_desktop_action(selected, now_ms)
                    self.radial_menu.close()
                    self._set_status(message, now_ms=now_ms)
                    self._emit_action("PUSH", message, now_ms=now_ms, force=True)
                else:
                    message = self.desktop_controller.open_application("explorer", now_ms=now_ms)
                    self._set_status(message, now_ms=now_ms)
                    self._emit_action("PUSH", "Open Application", now_ms=now_ms, force=True)

    def _handle_pull_action(self, right_event, now_ms):
        if right_event.gesture != "PULL" or right_event.phase != "start":
            return
        if self.mode == FILE_MODE:
            if self.spatial_engine.has_focus():
                self.spatial_engine.return_to_parent()
                self._set_status("Returned to parent layer", now_ms=now_ms)
                self._emit_action("PULL", "Return Layer", now_ms=now_ms, force=True)
            else:
                self.navigate_back(now_ms)
                self._emit_action("PULL", "Navigate Back", now_ms=now_ms, force=True)
        else:
            message = self.desktop_controller.close_active_window(now_ms=now_ms)
            self._set_status(message, now_ms=now_ms)
            self._emit_action("PULL", "Close Window", now_ms=now_ms, force=True)

    def _compute_dt(self, now_ms):
        if self.last_frame_ms is None:
            self.last_frame_ms = now_ms
            return 1.0 / 60.0

        delta = max(1, now_ms - self.last_frame_ms)
        self.last_frame_ms = now_ms
        return min(0.12, delta / 1000.0)

    def _handle_two_finger_swipe_left(self, right_event, now_ms):
        if right_event.phase != "start":
            return

        if self.mode == FILE_MODE:
            if right_event.gesture not in ("SWIPE_LEFT_TWO", "SWIPE_LEFT"):
                return
            # Prevent interference while dragging.
            # Only block if dragging (not grabbed).
            if self.dragging_object:
                return

            print("BACK NAVIGATION TRIGGERED")

            if self.navigate_back(now_ms):
                self._emit_action(right_event.gesture, "Navigate Back", now_ms=now_ms)

        elif self.mode == DESKTOP_MODE:
            if right_event.gesture != "SWIPE_LEFT_TWO":
                return
            self._set_status(
                self.desktop_controller.navigate_swipe("left", now_ms=now_ms),
                now_ms=now_ms,
            )

    def _handle_file_scroll_swipes(self, right_event, now_ms):
        if right_event.phase != "start":
            return
        if self.dragging_object:
            return
        if right_event.gesture == "SWIPE_UP":
            if self._scroll_files(-120.0, now_ms):
                self._emit_action("SWIPE_UP", "Scroll Down", now_ms=now_ms)
        elif right_event.gesture == "SWIPE_DOWN":
            if self._scroll_files(120.0, now_ms):
                self._emit_action("SWIPE_DOWN", "Scroll Up", now_ms=now_ms)

    def _handle_desktop_shortcuts(self, right_event, left_event, now_ms):
        if right_event.gesture == "SWIPE_LEFT" and right_event.phase == "start":
            self._set_status(self.desktop_controller.navigate_swipe("left", now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_LEFT", "Switch App", now_ms=now_ms)
        elif right_event.gesture == "SWIPE_RIGHT" and right_event.phase == "start":
            self._set_status(self.desktop_controller.navigate_swipe("right", now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_RIGHT", "Switch App", now_ms=now_ms)
        elif right_event.gesture == "SWIPE_UP" and right_event.phase == "start":
            self._set_status(self.desktop_controller.navigate_swipe("up", now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_UP", "Task View", now_ms=now_ms)
        elif right_event.gesture == "SWIPE_DOWN" and right_event.phase == "start":
            self._set_status(self.desktop_controller.navigate_swipe("down", now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_DOWN", "Show Desktop", now_ms=now_ms)
        elif left_event.gesture == "SWIPE_LEFT" and left_event.phase == "start":
            self._set_status(self.desktop_controller.media_previous_track(now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_LEFT", "Previous Track", now_ms=now_ms)
        elif left_event.gesture == "SWIPE_RIGHT" and left_event.phase == "start":
            self._set_status(self.desktop_controller.media_next_track(now_ms=now_ms), now_ms=now_ms)
            self._emit_action("SWIPE_RIGHT", "Next Track", now_ms=now_ms)
        elif left_event.gesture == "OPEN_PALM" and left_event.phase == "start":
            self._set_status(self.desktop_controller.media_play_pause(now_ms=now_ms), now_ms=now_ms)
            self._emit_action("OPEN_PALM", "Play/Pause", now_ms=now_ms)

    def _handle_file_mode(
        self,
        right_hand,
        left_hand,
        right_event,
        left_event,
        dustbin,
        now_ms,
        expand_open_event=None,
    ):
        self.radial_menu.close()
        self.radial_state = self.radial_menu._base_state()
        hovered_obj = None
        two_hand_pinch = (
            right_event.gesture == "PINCH"
            and left_event.gesture == "PINCH"
        )
        expand_open_started = self._is_expand_open_start(expand_open_event)
        expand_open_hold = self._is_expand_open_hold(expand_open_event)
        if expand_open_started and two_hand_pinch:
            # Consume expand-open first so x/y tracking halts immediately on trigger frame.
            self._handle_expand_open(
                expand_open_event,
                now_ms,
                two_hand_pinch_active=two_hand_pinch,
            )
        self._handle_two_finger_swipe_left(right_event, now_ms)

        if right_hand:
            cursor_pos = right_hand["cursor"]
            if not self.dragging_object and not self.grabbed_object:
                hovered_obj = self._update_hover_state(cursor_pos)

            if self.grabbed_object:
                if right_event.gesture == "PINCH":
                    # Two-hand pinch uses midpoint for stable cinematic expansion anchoring.
                    two_hand_pinch = bool(left_hand and left_event.gesture == "PINCH")
                    if two_hand_pinch:
                        right_pinch = right_hand.get("pinch_center", right_hand["cursor"])
                        left_pinch = left_hand.get("pinch_center", left_hand["cursor"])
                        pinch_x = (right_pinch[0] + left_pinch[0]) * 0.5
                        pinch_y = (right_pinch[1] + left_pinch[1]) * 0.5
                        pair_distance = math.hypot(right_pinch[0] - left_pinch[0], right_pinch[1] - left_pinch[1])
                        if self.expand_initial_distance is None:
                            self.expand_initial_distance = max(1.0, pair_distance)
                        ratio = pair_distance / max(1.0, self.expand_initial_distance)
                        self.expand_visual_ratio = max(1.0, min(ratio, EXPAND_OPEN_DISTANCE_RATIO + 0.25))
                    else:
                        pinch_x, pinch_y = right_hand.get("pinch_center", right_hand["cursor"])
                        self.expand_initial_distance = None
                        self.expand_visual_ratio = 1.0
                    self.grabbed_object.expand_visual_scale = self.expand_visual_ratio

                    # Freeze depth while two-hand expand is active but threshold not emitted.
                    if two_hand_pinch and not expand_open_started:
                        if expand_open_hold:
                            if not self.expand_armed or self.expand_anchor is None:
                                self.expand_anchor = (self.grabbed_object.x, self.grabbed_object.y)
                            self.expand_armed = True
                        else:
                            self.expand_armed = False
                            self.expand_anchor = None
                        depth_state = "expand_armed" if self.expand_armed else "grabbed"
                        self.spatial_engine.animate_depth_transition(
                            self.grabbed_object,
                            self.grabbed_object.z,
                            depth_state,
                        )
                    else:
                        self.expand_armed = False
                        self.expand_anchor = None
                        if not expand_open_started and self.grabbed_object.depth_state != "grabbed":
                            self.spatial_engine.animate_depth_transition(
                                self.grabbed_object,
                                self.grabbed_object.z,
                                "grabbed",
                            )

                    if not expand_open_started:
                        if self.expand_armed and self.expand_anchor is not None:
                            self.grabbed_object.x, self.grabbed_object.y = self.expand_anchor
                        else:
                            world_x, world_y = self._screen_to_world(
                                pinch_x,
                                pinch_y,
                                self.grabbed_object.z,
                            )
                            target_x = world_x - (self.grabbed_object.w * 0.5)
                            target_y = world_y - (self.grabbed_object.h * 0.5)
                            if self.grabbed_object:
                                follow_smoothing = GRAB_FOLLOW_SMOOTHING
                            else:
                                follow_smoothing = 0.35
                            self.grabbed_object.x += (target_x - self.grabbed_object.x) * follow_smoothing
                            self.grabbed_object.y += (target_y - self.grabbed_object.y) * follow_smoothing
                            if not self.expand_armed:
                                hand_depth = float(right_hand.get("hand_depth_z", 0.0))
                                target_z = float(GRAB_BASE_Z) + (hand_depth * float(GRAB_DEPTH_SCALE))
                                target_z = max(0.52, min(2.0, target_z))
                                self.grabbed_object.z += (target_z - self.grabbed_object.z) * 0.25
                                self.grabbed_object.target_z = self.grabbed_object.z
                        self.grabbed_object.rect.topleft = (
                            int(self.grabbed_object.x),
                            int(self.grabbed_object.y),
                        )
                        self.grabbed_object.display_rect.topleft = self.grabbed_object.rect.topleft
                    if dustbin:
                        dustbin.hovered = rect_vs_rect(self.grabbed_object.rect, dustbin.rect)
                elif right_event.gesture == "OPEN_PALM" and right_event.phase == "start":
                    dropped_obj = self.grabbed_object
                    if dropped_obj:
                        over_trash = bool(
                            dustbin and rect_vs_rect(dropped_obj.rect, dustbin.rect)
                        )
                        if over_trash:
                            success, message = delete_item(
                                dropped_obj.path,
                                mode=SAFE_DELETE_MODE,
                            )
                            if success and dropped_obj in self.file_objects:
                                self.file_objects.remove(dropped_obj)
                                self._update_scroll_bounds()
                                self._apply_scroll_offset()
                            self._set_status(message, now_ms=now_ms)
                        else:
                            self._set_status("Released", now_ms=now_ms)
                    # Clear grabbed state AFTER trash logic.
                    self._clear_grabbed_state(reset_depth=True)
                elif right_event.gesture != "PINCH":
                    self._set_status("Released", now_ms=now_ms)
                    self._clear_grabbed_state(reset_depth=True)
            elif right_event.gesture == "PINCH" and right_event.phase == "start":
                if not self.dragging_object:
                    grab_candidate = hovered_obj or self._find_grab_candidate(cursor_pos, GRAB_RADIUS)
                    if grab_candidate:
                        self._start_spatial_grab(grab_candidate, now_ms)
            elif right_event.gesture == "FIST":
                if right_event.phase == "start" and not self.dragging_object and hovered_obj:
                    self.dragging_object = hovered_obj
                    self.dragging_object.start_drag(cursor_pos[0], cursor_pos[1])
                    self._set_status(f"Grabbed {hovered_obj.name}", now_ms=now_ms)
                    self._emit_action("FIST", "Grab File", now_ms=now_ms, force=True)

                if right_event.phase in ("start", "hold") and self.dragging_object:
                    obj = self.dragging_object
                    obj.move_to(cursor_pos[0] + obj.drag_offset[0], cursor_pos[1] + obj.drag_offset[1])
                    self._set_status(f"Dragging {obj.name}", duration_ms=250, now_ms=now_ms)
                    self._update_delete_hold(now_ms, dustbin)
                    if right_event.phase == "start" or right_event.stable_frames <= 2:
                        self._emit_action("FIST HOLD", "Dragging File", now_ms=now_ms)

            elif right_event.gesture == "EXPAND" and right_event.phase == "start":
                if hovered_obj and not self.dragging_object:
                    self._open_hovered_item(hovered_obj, now_ms, gesture_name="EXPAND", overlay_desc="Open File")

            elif right_event.gesture == "DOUBLE_TAP" and right_event.phase == "start":
                self.double_tap_flash_until_ms = now_ms + 220
                self._emit_action("DOUBLE_TAP", "Click", now_ms=now_ms)

            elif right_event.gesture == "OPEN_PALM" and right_event.phase == "start":
                self._release_drag(dustbin, now_ms)

            if self.dragging_object and dustbin:
                dustbin.hovered = rect_vs_rect(self.dragging_object.display_rect, dustbin.rect)
                if not dustbin.hovered:
                    self._clear_delete_hold()
        else:
            for obj in self.file_objects:
                obj.on_hover_exit()
            if self.grabbed_object:
                self._set_status("Tracking lost. Layer release.", now_ms=now_ms)
                self._clear_grabbed_state(reset_depth=True)
            if self.dragging_object:
                self._set_status("Tracking lost. Drag cancelled.", now_ms=now_ms)
                self._end_drag()

        if not self.grabbed_object:
            self._handle_push_action(right_event, hovered_obj, now_ms)
            self._handle_pull_action(right_event, now_ms)

        if dustbin:
            dustbin.delete_progress = self.delete_progress
            dustbin.armed = self.delete_armed
        self._handle_file_scroll_swipes(right_event, now_ms)

    def _handle_desktop_mode(self, right_hand, left_hand, right_event, left_event, now_ms):
        if self.dragging_object:
            self._end_drag()
        if self.grabbed_object:
            self._clear_grabbed_state(reset_depth=True)

        if right_hand:
            cursor = right_hand.get("cursor", (0, 0))
            ui_x = float(cursor[0]) / max(1.0, float(UI_WIDTH))
            ui_y = float(cursor[1]) / max(1.0, float(UI_HEIGHT))
            self.desktop_controller.move_cursor(ui_x, ui_y, smoothing=DESKTOP_CURSOR_SMOOTHING)

        if right_hand and right_event.gesture == "OPEN_PALM":
            if self.desktop_open_palm_started_ms is None:
                self.desktop_open_palm_started_ms = now_ms
            if (now_ms - self.desktop_open_palm_started_ms) >= 1000 and not self.radial_menu.active:
                center = right_hand.get("palm_center", right_hand["cursor"])
                self.radial_menu.open(center, now_ms=now_ms)
                self._set_status("Radial menu open", duration_ms=800, now_ms=now_ms)
                self._emit_action("OPEN_PALM", "Open Radial Menu", now_ms=now_ms)
        else:
            self.desktop_open_palm_started_ms = None

        if right_event.gesture == "FIST":
            if right_event.phase == "start":
                self._set_status(self.desktop_controller.start_drag(now_ms=now_ms), now_ms=now_ms)
                self._emit_action("FIST", "Drag Start", now_ms=now_ms)
            if right_hand and right_event.phase in ("start", "hold"):
                cursor = right_hand.get("cursor", (0, 0))
                ui_x = float(cursor[0]) / max(1.0, float(UI_WIDTH))
                ui_y = float(cursor[1]) / max(1.0, float(UI_HEIGHT))
                self.desktop_controller.update_drag(ui_x, ui_y)
        elif self.desktop_controller.drag_active:
            self.desktop_controller.end_drag()

        if right_event.gesture == "PINCH":
            if right_event.phase == "start":
                self._set_status(self.desktop_controller.pinch_click(now_ms=now_ms), now_ms=now_ms)
                self._emit_action("PINCH", "Click", now_ms=now_ms)
            elif right_event.phase == "hold" and right_hand:
                cursor = right_hand.get("cursor", (0, 0))
                ui_x = float(cursor[0]) / max(1.0, float(UI_WIDTH))
                ui_y = float(cursor[1]) / max(1.0, float(UI_HEIGHT))
                self.desktop_controller.window_grab_drag(ui_x, ui_y, now_ms=now_ms)

        if left_hand and left_event.gesture == "PINCH":
            pinch_y = float(left_hand.get("cursor", (0, 0))[1])
            if self.desktop_volume_anchor_y is None:
                self.desktop_volume_anchor_y = pinch_y
            delta = pinch_y - self.desktop_volume_anchor_y
            if abs(delta) >= 24.0:
                self._set_status(self.desktop_controller.volume_from_vertical_delta(delta, now_ms=now_ms), now_ms=now_ms)
                self._emit_action("PINCH", "Volume Control", now_ms=now_ms)
                self.desktop_volume_anchor_y = pinch_y
        else:
            self.desktop_volume_anchor_y = None

        palm_center = right_hand.get("palm_center") if right_hand else None
        index_tip = right_hand.get("cursor") if right_hand else None
        self.radial_state = self.radial_menu.update(
            palm_center,
            index_tip,
            select_event=right_event,
            now_ms=now_ms,
        )
        selected_item = self.radial_state.get("selected_item")
        if selected_item:
            message = self._run_desktop_action(selected_item, now_ms)
            self._set_status(message, now_ms=now_ms)
            self._emit_action("DOUBLE_TAP", message, now_ms=now_ms, force=True)

        if right_event.gesture == "DOUBLE_TAP" and right_event.phase == "start":
            self.double_tap_flash_until_ms = now_ms + 220
            if not self.radial_menu.active and not selected_item:
                cursor = right_hand.get("cursor") if right_hand else None
                if cursor:
                    message = self.desktop_controller.click_primary(cursor[0], cursor[1], now_ms=now_ms)
                else:
                    message = self.desktop_controller.click_primary(now_ms=now_ms)
                self._set_status(message, now_ms=now_ms)
                self._emit_action("DOUBLE_TAP", "Click", now_ms=now_ms, force=True)

        self._handle_two_finger_swipe_left(right_event, now_ms)
        self._handle_desktop_shortcuts(right_event, left_event, now_ms)
        self._handle_push_action(right_event, hovered_obj=None, now_ms=now_ms)
        self._handle_pull_action(right_event, now_ms)

    def handle_input(
        self,
        right_hand,
        left_hand,
        dustbin,
        mode_toggle_event=None,
        expand_open_event=None,
        mode_hold_progress=0.0,
        now_ms=None,
    ):
        now_ms = self._now_ms() if now_ms is None else now_ms
        print("CURRENT MODE:", self._mode_debug_name())
        right_event = self._event_from_hand(right_hand)
        left_event = self._event_from_hand(left_hand)

        if (
            mode_toggle_event
            and getattr(mode_toggle_event, "gesture", "IDLE") == "MODE_TOGGLE"
            and getattr(mode_toggle_event, "phase", "none") == "start"
            and self._can_fire("mode_toggle", now_ms, MODE_TOGGLE_COOLDOWN_MS)
            and not self.dragging_object
            and not self.grabbed_object
            and not self.desktop_controller.drag_active
            and not self.radial_menu.active
        ):
            self._toggle_mode(now_ms)

        if dustbin:
            dustbin.hovered = False
            if self.mode != FILE_MODE:
                dustbin.delete_progress = 0.0
                dustbin.armed = False

        if self.mode == FILE_MODE:
            self._handle_file_mode(
                right_hand,
                left_hand,
                right_event,
                left_event,
                dustbin,
                now_ms,
                expand_open_event=expand_open_event,
            )
        else:
            self._handle_desktop_mode(right_hand, left_hand, right_event, left_event, now_ms)

        dt = self._compute_dt(now_ms)
        self.spatial_engine.update(dt)

        for obj in self.file_objects:
            obj.update()

        right_ui_scale = right_hand.get("ui_scale", 1.0) if right_hand else 1.0
        left_ui_scale = left_hand.get("ui_scale", 1.0) if left_hand else 1.0
        ui_scale = (right_ui_scale * 0.75) + (left_ui_scale * 0.25)

        self.frame_state = {
            "status_text": self._current_status(now_ms),
            "current_path": self.navigator.current_path or "Drives",
            "delete_progress": self.delete_progress,
            "delete_armed": self.delete_armed,
            "dragging_name": self.dragging_object.name if self.dragging_object else "",
            "grabbed_name": self.grabbed_object.name if self.grabbed_object else "",
            "expand_armed": bool(self.expand_armed),
            "expand_ratio": float(self.expand_visual_ratio),
            "right_event": right_event,
            "left_event": left_event,
            "mode": self.mode,
            "radial_menu": self.radial_state,
            "ui_scale": ui_scale,
            "push_confirmation": now_ms <= self.push_pulse_until_ms,
            "double_tap_flash": now_ms <= self.double_tap_flash_until_ms,
            "mode_switch_animation": now_ms <= self.mode_switch_until_ms,
            "mode_hold_progress": float(mode_hold_progress),
            "mode_hold_active": bool(mode_hold_progress > 0.0),
            "spatial_focus_active": self.spatial_engine.has_focus(),
        }
        return self.frame_state
