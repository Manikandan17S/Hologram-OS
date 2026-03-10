import unittest

from logic.depth_controller import DepthController


def depth_landmarks(z):
    landmarks = [[idx, 100, 100, z] for idx in range(21)]
    landmarks[0] = [0, 100, 100, z]
    landmarks[5] = [5, 140, 80, z]
    landmarks[8] = [8, 180, 70, z]
    landmarks[9] = [9, 140, 100, z]
    landmarks[13] = [13, 140, 120, z]
    landmarks[17] = [17, 140, 140, z]
    return landmarks


class DepthControllerTests(unittest.TestCase):
    def test_normalized_depth_and_ui_scale_range(self):
        controller = DepthController()
        controller.compute_hand_depth(depth_landmarks(-0.02))
        controller.compute_hand_depth(depth_landmarks(-0.10))
        controller.compute_hand_depth(depth_landmarks(-0.18))
        state = controller.get_state()
        self.assertGreaterEqual(state["normalized_depth"], 0.0)
        self.assertLessEqual(state["normalized_depth"], 1.0)
        self.assertGreaterEqual(state["ui_scale"], 0.86)
        self.assertLessEqual(state["ui_scale"], 1.24)

    def test_detect_push_gesture(self):
        controller = DepthController()
        for z in (-0.03, -0.07, -0.12, -0.18, -0.24):
            controller.compute_hand_depth(depth_landmarks(z))
        self.assertTrue(controller.detect_push_gesture())

    def test_detect_pull_gesture(self):
        controller = DepthController()
        for z in (-0.24, -0.20, -0.14, -0.09, -0.05):
            controller.compute_hand_depth(depth_landmarks(z))
        self.assertTrue(controller.detect_pull_gesture())


if __name__ == "__main__":
    unittest.main()
