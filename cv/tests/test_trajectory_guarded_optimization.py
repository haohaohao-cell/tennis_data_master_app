import unittest

import numpy as np

from cv.experiments.trajectory_guarded_optimization import GuardedTrajectoryConfig, optimize_trajectory


class GuardedTrajectoryOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.config = GuardedTrajectoryConfig(
            context_half=4,
            min_side_points=3,
            base_threshold_px=4.0,
            far_threshold_scale=1.0,
            near_threshold_scale=1.0,
        )

    def test_corrects_only_an_isolated_spike(self):
        coords = [(100.0 + 2.0 * index, 300.0 + index) for index in range(15)]
        coords[7] = (900.0, 900.0)

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        self.assertEqual(result["diagnostics"][7]["status"], "isolated_spike_corrected")
        np.testing.assert_allclose(result["optimized"][7], [114.0, 307.0], atol=1.0)

    def test_keeps_a_real_direction_change(self):
        coords = []
        for index in range(15):
            x = 100.0 + 6.0 * index if index <= 7 else 142.0 - 6.0 * (index - 7)
            coords.append((x, 400.0))

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        self.assertEqual(result["diagnostics"][7]["status"], "event_raw_kept")
        self.assertEqual(result["optimized"][7], [142.0, 400.0])

    def test_only_fills_a_short_bilateral_gap(self):
        coords = [(100.0 + 2.0 * index, 300.0 + index) for index in range(15)]
        coords[7] = None
        coords[8] = None

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        self.assertEqual(result["diagnostics"][7]["status"], "short_gap_filled")
        self.assertEqual(result["diagnostics"][8]["status"], "short_gap_filled")
        self.assertEqual(result["optimized"][7], [114.0, 307.0])
        self.assertEqual(result["optimized"][8], [116.0, 308.0])

    def test_never_drops_an_observed_point_without_proof(self):
        coords = [(100.0 + 2.0 * index, 300.0 + index) for index in range(15)]
        coords[0] = (900.0, 900.0)

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        self.assertEqual(result["diagnostics"][0]["status"], "raw_kept_insufficient_context")
        self.assertEqual(result["optimized"][0], [900.0, 900.0])


if __name__ == "__main__":
    unittest.main()
