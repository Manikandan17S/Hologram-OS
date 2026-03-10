# Hologram OS v1 Manual Test Checklist

## Setup
- Install dependencies: `pip install -r requirements.txt`
- Run app: `python main.py`
- Use a well-lit room and keep both hands inside camera frame.

## Gesture Reliability
- Right hand `FIST start` on an item should grab once.
- Right hand `FIST hold` should drag smoothly without re-grab flicker.
- Right hand `OPEN_PALM start` should release dragged item.
- Right hand `DOUBLE_TAP start` should open hovered item in file mode.
- Right hand `EXPAND start` should open hovered folder/file once per cooldown.
- Right hand `DOUBLE_TAP start` should confirm radial menu selection in desktop mode.
- Right hand `SWIPE_LEFT/RIGHT` should trigger desktop window switch in desktop mode.
- Right hand `SWIPE_LEFT_TWO start` should navigate back in file mode and switch previous window in desktop mode.
- Left hand `FIST start` should navigate up once per cooldown.
- Hold both hands `OPEN_PALM` for ~3 seconds to toggle between `FILE_MODE` and `DESKTOP_MODE`.

## Safe Delete Flow
- Drag an item onto trash area.
- Keep `FIST hold` until delete progress bar fills.
- Release with `OPEN_PALM start`.
- Verify item is moved to Recycle Bin.
- Try delete without full hold and verify item is only dropped, not deleted.

## Safety Guards
- Attempt deleting protected paths and verify blocked status message.
- Verify drive roots cannot be deleted.
- While dragging, remove right hand from frame and verify drag is cancelled safely.

## Visual/HUD
- Confirm subtle vignette + corner brackets + faint scanlines are visible.
- Confirm cursor trail and gesture labels update for both hands.
- Confirm status text, mode badge, path, FPS, and quality profile appear in HUD.
- In desktop mode, confirm radial menu segments and highlight follow index direction.
- Confirm push gesture triggers short pulse animation.
- Confirm two-hand hold timer circle fills while holding both palms open.
- Confirm double tap triggers a short flash effect.
- Confirm mode switch animation appears when mode changes.
- Confirm bottom-center gesture popup appears with gesture/action text after actions.

## Performance
- Observe average FPS in HUD; target is >= 30 FPS at 1280x720.
- Confirm quality profile switches to medium/low if FPS drops heavily.
