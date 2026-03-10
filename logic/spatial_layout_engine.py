from config import (
    SPATIAL_BASE_Z,
    SPATIAL_FOCUS_Z,
    SPATIAL_PARENT_Z,
    SPATIAL_SMOOTHING_FACTOR,
)


def _clamp(value, low, high):
    return max(low, min(high, value))


class SpatialLayoutEngine:
    def __init__(
        self,
        base_z=SPATIAL_BASE_Z,
        parent_layer_z=SPATIAL_PARENT_Z,
        focus_layer_z=SPATIAL_FOCUS_Z,
        smoothing_factor=SPATIAL_SMOOTHING_FACTOR,
    ):
        self.base_z = float(base_z)
        self.parent_layer_z = float(parent_layer_z)
        self.focus_layer_z = float(focus_layer_z)
        self.smoothing_factor = float(smoothing_factor)
        self.objects = []
        self.focus_object = None

    def bind_objects(self, objects):
        self.objects = list(objects or [])
        self.focus_object = None
        for obj in self.objects:
            obj.z = self.base_z
            obj.target_z = self.base_z
            obj.depth_state = "default"

    def has_focus(self):
        return self.focus_object is not None

    def animate_depth_transition(self, obj, target_z, depth_state):
        if obj is None:
            return
        obj.target_z = float(target_z)
        obj.depth_state = depth_state

    def set_focus_layer(self, focus_obj):
        if focus_obj is None or focus_obj not in self.objects:
            return False

        self.focus_object = focus_obj
        for obj in self.objects:
            if obj is focus_obj:
                self.animate_depth_transition(obj, self.focus_layer_z, "focus")
            else:
                self.animate_depth_transition(obj, self.parent_layer_z, "parent")
        return True

    def return_to_parent(self):
        self.focus_object = None
        for obj in self.objects:
            self.animate_depth_transition(obj, self.base_z, "default")

    def update(self, dt):
        if not self.objects:
            return

        dt = max(0.0, float(dt))
        # Keep smoothing stable across variable FPS.
        frame_scaled = _clamp(dt * 60.0, 0.25, 2.0)
        smooth = _clamp(self.smoothing_factor * frame_scaled, 0.02, 0.65)

        for obj in self.objects:
            current_z = float(getattr(obj, "z", self.base_z))
            target_z = float(getattr(obj, "target_z", current_z))
            current_z += (target_z - current_z) * smooth
            if abs(current_z - target_z) < 0.001:
                current_z = target_z
            obj.z = current_z
