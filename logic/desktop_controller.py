import ctypes
import os
import shlex
import subprocess
import time

from config import (
    DESKTOP_ACTION_COOLDOWN_MS,
    DESKTOP_CLICK_COOLDOWN_MS,
    DESKTOP_CURSOR_SMOOTHING,
    DESKTOP_MAX_VOLUME_STEPS,
    DESKTOP_NAV_COOLDOWN_MS,
    DESKTOP_SCROLL_COOLDOWN_MS,
)

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except Exception:  # pragma: no cover - environment dependent
    pyautogui = None

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover - environment dependent
    gw = None


VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MENU = 0x12
VK_TAB = 0x09
VK_F4 = 0x73
VK_LWIN = 0x5B
VK_D = 0x44
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class DesktopController:
    def __init__(self):
        self.cooldowns = {}
        self.cursor_pos = None
        self.drag_active = False

    def _now_ms(self):
        return int(time.time() * 1000)

    def _try_fire(self, action, cooldown_ms, now_ms=None):
        now_ms = self._now_ms() if now_ms is None else now_ms
        last = self.cooldowns.get(action, 0)
        if now_ms - last < cooldown_ms:
            remaining = cooldown_ms - (now_ms - last)
            return False, f"Cooldown {action}: {remaining}ms"
        self.cooldowns[action] = now_ms
        return True, ""

    def _key_tap(self, vk_code):
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

    def _map_ui_to_screen(self, ui_x, ui_y):
        if pyautogui:
            screen_w, screen_h = pyautogui.size()
        else:
            user32 = ctypes.windll.user32
            screen_w = int(user32.GetSystemMetrics(0))
            screen_h = int(user32.GetSystemMetrics(1))
        x = max(0, min(screen_w - 1, int(ui_x * screen_w)))
        y = max(0, min(screen_h - 1, int(ui_y * screen_h)))
        return x, y

    def move_cursor(self, ui_x, ui_y, smoothing=DESKTOP_CURSOR_SMOOTHING):
        try:
            target_x, target_y = self._map_ui_to_screen(float(ui_x), float(ui_y))
            if self.cursor_pos is None:
                self.cursor_pos = (float(target_x), float(target_y))
            else:
                smooth = max(0.01, min(1.0, float(smoothing)))
                current_x, current_y = self.cursor_pos
                current_x += (target_x - current_x) * smooth
                current_y += (target_y - current_y) * smooth
                self.cursor_pos = (current_x, current_y)

            move_x, move_y = int(self.cursor_pos[0]), int(self.cursor_pos[1])
            if pyautogui:
                pyautogui.moveTo(move_x, move_y)
            else:
                ctypes.windll.user32.SetCursorPos(move_x, move_y)
            return "Cursor moved"
        except Exception as exc:
            return f"Cursor move failed: {exc}"

    def pinch_click(self, now_ms=None):
        allowed, message = self._try_fire("pinch_click", DESKTOP_CLICK_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        return self.click_primary(now_ms=now_ms)

    def start_drag(self, now_ms=None):
        allowed, message = self._try_fire("start_drag", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        if self.drag_active:
            return "Drag active"
        try:
            if pyautogui:
                pyautogui.mouseDown()
            else:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.drag_active = True
            return "Drag start"
        except Exception as exc:
            return f"Drag start failed: {exc}"

    def update_drag(self, ui_x, ui_y):
        if not self.drag_active:
            return "Drag inactive"
        try:
            target_x, target_y = self._map_ui_to_screen(float(ui_x), float(ui_y))
            if pyautogui:
                pyautogui.dragTo(target_x, target_y, duration=0, button="left")
            else:
                ctypes.windll.user32.SetCursorPos(target_x, target_y)
            return "Drag update"
        except Exception as exc:
            return f"Drag update failed: {exc}"

    def end_drag(self):
        if not self.drag_active:
            return "Drag inactive"
        try:
            if pyautogui:
                pyautogui.mouseUp()
            else:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.drag_active = False
            return "Drag end"
        except Exception as exc:
            return f"Drag end failed: {exc}"

    def window_grab_drag(self, ui_x, ui_y, now_ms=None):
        allowed, message = self._try_fire("window_grab_drag", DESKTOP_CLICK_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        try:
            target_x, target_y = self._map_ui_to_screen(float(ui_x), float(ui_y))
            if not pyautogui:
                return "Window grab unavailable: pyautogui not installed"
            pyautogui.dragTo(target_x, target_y, duration=0, button="left")
            return "Window drag"
        except Exception as exc:
            return f"Window drag failed: {exc}"

    def navigate_swipe(self, direction, now_ms=None):
        allowed, message = self._try_fire("desktop_nav", DESKTOP_NAV_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        direction = str(direction).lower()
        try:
            if direction == "left":
                self._hotkey_alt_tab(reverse=False)
                return "Switch app next"
            if direction == "right":
                self._hotkey_alt_tab(reverse=True)
                return "Switch app previous"
            if direction == "up":
                if pyautogui:
                    pyautogui.hotkey("win", "tab")
                return "Task view"
            if direction == "down":
                if pyautogui:
                    pyautogui.hotkey("win", "d")
                return "Show desktop"
            return "Unknown navigation"
        except Exception as exc:
            return f"Desktop navigation failed: {exc}"

    def media_next_track(self, now_ms=None):
        allowed, message = self._try_fire("media_next", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        try:
            self._key_tap(VK_MEDIA_NEXT_TRACK)
            return "Next track"
        except Exception as exc:
            return f"Next track failed: {exc}"

    def media_previous_track(self, now_ms=None):
        allowed, message = self._try_fire("media_prev", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        try:
            self._key_tap(VK_MEDIA_PREV_TRACK)
            return "Previous track"
        except Exception as exc:
            return f"Previous track failed: {exc}"

    def volume_from_vertical_delta(self, delta, now_ms=None):
        allowed, message = self._try_fire("volume_gesture", DESKTOP_CLICK_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message
        try:
            if delta < 0:
                self._key_tap(VK_VOLUME_UP)
                return "Volume up"
            self._key_tap(VK_VOLUME_DOWN)
            return "Volume down"
        except Exception as exc:
            return f"Volume gesture failed: {exc}"

    def _hotkey_alt_tab(self, reverse=False):
        if pyautogui:
            if reverse:
                pyautogui.hotkey("alt", "shift", "tab")
            else:
                pyautogui.hotkey("alt", "tab")
            return

        user32 = ctypes.windll.user32
        user32.keybd_event(VK_MENU, 0, 0, 0)
        if reverse:
            user32.keybd_event(0x10, 0, 0, 0)  # Shift
        user32.keybd_event(VK_TAB, 0, 0, 0)
        user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
        if reverse:
            user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    def open_application(self, path_or_name, now_ms=None):
        allowed, message = self._try_fire("open_application", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        if not path_or_name:
            return "Open app failed: empty target"

        target = str(path_or_name).strip()
        try:
            if os.path.exists(target):
                if os.name == "nt":
                    os.startfile(target)
                else:
                    subprocess.Popen([target], close_fds=True)
                return f"Opened: {target}"

            if os.name == "nt":
                subprocess.Popen(target, shell=True, close_fds=True)
            else:
                cmd = shlex.split(target)
                subprocess.Popen(cmd, close_fds=True)
            return f"Launched: {target}"
        except Exception as exc:
            return f"Open app failed: {exc}"

    def close_active_window(self, now_ms=None):
        allowed, message = self._try_fire("close_window", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            if gw:
                active = gw.getActiveWindow()
                if active is not None and active.title:
                    # Keep this as a fast, non-blocking close request.
                    active.close()
                    return "Close window requested"

            if pyautogui:
                pyautogui.hotkey("alt", "f4")
            else:
                user32 = ctypes.windll.user32
                user32.keybd_event(VK_MENU, 0, 0, 0)
                user32.keybd_event(VK_F4, 0, 0, 0)
                user32.keybd_event(VK_F4, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            return "Active window close sent"
        except Exception as exc:
            return f"Close window failed: {exc}"

    def switch_window_next(self, now_ms=None):
        allowed, message = self._try_fire("switch_next", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            self._hotkey_alt_tab(reverse=False)
            return "Switched to next window"
        except Exception as exc:
            return f"Switch next failed: {exc}"

    def switch_window_previous(self, now_ms=None):
        allowed, message = self._try_fire("switch_previous", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            self._hotkey_alt_tab(reverse=True)
            return "Switched to previous window"
        except Exception as exc:
            return f"Switch previous failed: {exc}"

    def control_volume(self, delta, now_ms=None):
        allowed, message = self._try_fire("control_volume", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            delta = int(delta)
            steps = max(1, min(DESKTOP_MAX_VOLUME_STEPS, abs(delta)))
            key_code = VK_VOLUME_UP if delta >= 0 else VK_VOLUME_DOWN
            for _ in range(steps):
                self._key_tap(key_code)
            direction = "up" if delta >= 0 else "down"
            return f"Volume {direction} x{steps}"
        except Exception as exc:
            return f"Volume control failed: {exc}"

    def media_play_pause(self, now_ms=None):
        allowed, message = self._try_fire("media_play_pause", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            self._key_tap(VK_MEDIA_PLAY_PAUSE)
            return "Media play/pause toggled"
        except Exception as exc:
            return f"Media toggle failed: {exc}"

    def system_scroll(self, delta, now_ms=None):
        allowed, message = self._try_fire("system_scroll", DESKTOP_SCROLL_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            if not pyautogui:
                return "Scroll unavailable: pyautogui not installed"
            pyautogui.scroll(int(delta))
            return f"Scrolled {int(delta)}"
        except Exception as exc:
            return f"Scroll failed: {exc}"

    def click_primary(self, x=None, y=None, now_ms=None):
        allowed, message = self._try_fire("primary_click", DESKTOP_ACTION_COOLDOWN_MS, now_ms=now_ms)
        if not allowed:
            return message

        try:
            if pyautogui:
                if x is not None and y is not None:
                    pyautogui.click(x=int(x), y=int(y))
                else:
                    pyautogui.click()
                return "Primary click"

            # Fallback for Windows when pyautogui is unavailable.
            user32 = ctypes.windll.user32
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return "Primary click"
        except Exception as exc:
            return f"Click failed: {exc}"
