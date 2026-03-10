import unittest

from core.hand_tracker import adaptive_smoothing_factor, estimate_landmark_velocity, smooth_landmarks


class HandTrackerSmoothingTests(unittest.TestCase):
    def test_smooth_landmarks_dict_points(self):
        prev = [
            {"x": 0.0, "y": 10.0, "z": -0.2},
            {"x": 10.0, "y": 20.0, "z": -0.4},
        ]
        current = [
            {"x": 10.0, "y": 20.0, "z": -0.6},
            {"x": 20.0, "y": 30.0, "z": -0.8},
        ]
        smoothed = smooth_landmarks(prev, current, smoothing_factor=0.7)

        self.assertAlmostEqual(smoothed[0]["x"], 3.0)
        self.assertAlmostEqual(smoothed[0]["y"], 13.0)
        self.assertAlmostEqual(smoothed[0]["z"], -0.32)
        self.assertAlmostEqual(smoothed[1]["x"], 13.0)
        self.assertAlmostEqual(smoothed[1]["y"], 23.0)
        self.assertAlmostEqual(smoothed[1]["z"], -0.52)

    def test_smooth_landmarks_list_points(self):
        prev = [
            [0, 0.0, 10.0, -0.2],
            [1, 10.0, 20.0, -0.4],
        ]
        current = [
            [0, 10.0, 20.0, -0.6],
            [1, 20.0, 30.0, -0.8],
        ]
        smoothed = smooth_landmarks(prev, current, smoothing_factor=0.7)

        self.assertEqual(smoothed[0][0], 0)
        self.assertAlmostEqual(smoothed[0][1], 3.0)
        self.assertAlmostEqual(smoothed[0][2], 13.0)
        self.assertAlmostEqual(smoothed[0][3], -0.32)
        self.assertEqual(smoothed[1][0], 1)
        self.assertAlmostEqual(smoothed[1][1], 13.0)
        self.assertAlmostEqual(smoothed[1][2], 23.0)
        self.assertAlmostEqual(smoothed[1][3], -0.52)

    def test_adaptive_smoothing_factor_drops_when_velocity_high(self):
        low_velocity_factor = adaptive_smoothing_factor(0.7, velocity=2.0)
        high_velocity_factor = adaptive_smoothing_factor(0.7, velocity=60.0)
        self.assertGreater(low_velocity_factor, high_velocity_factor)

    def test_estimate_landmark_velocity(self):
        prev = [[idx, 100.0, 100.0, -0.1] for idx in range(21)]
        current = [[idx, 100.0, 100.0, -0.1] for idx in range(21)]
        current[8][1] = 124.0
        current[8][2] = 112.0
        velocity = estimate_landmark_velocity(prev, current, sample_ids=(8,))
        self.assertAlmostEqual(velocity, (24.0**2 + 12.0**2) ** 0.5, places=3)


if __name__ == "__main__":
    unittest.main()
