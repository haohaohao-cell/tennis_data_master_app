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

        self.assertEqual(result["diagnostics"][7]["status"], "raw_kept")
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

    def test_freezes_a_contaminated_run_and_preserves_its_boundary(self):
        # Frames 6-8 are a coherent but wrong branch.  They must not enter the
        # left anchor, while frame 9 is a real branch boundary and stays raw.
        coords = [(100.0 + 2.0 * index, 300.0 + 5.0 * index) for index in range(6)]
        coords.extend([(900.0, 900.0), (880.0, 880.0), (860.0, 860.0)])
        coords.extend([(118.0 - 2.0 * index, 360.0 - 3.0 * index) for index in range(6)])

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        for index, expected in zip((6, 7, 8), ([112.0, 330.0], [114.0, 335.0], [116.0, 340.0])):
            self.assertEqual(result["diagnostics"][index]["status"], "frozen_left_ransac_corrected")
            self.assertEqual(result["diagnostics"][index]["frozen_range"], [6, 8])
            np.testing.assert_allclose(result["optimized"][index], expected, atol=1.0)

        self.assertEqual(result["diagnostics"][9]["status"], "boundary_raw_kept")
        self.assertEqual(result["optimized"][9], [118.0, 360.0])

        evidence = result["diagnostics"][9]
        self.assertTrue(evidence["h1_event_accepted"])
        self.assertGreaterEqual(evidence["h1_residual_improvement_px"], self.config.min_h1_improvement_px)
        self.assertGreaterEqual(evidence["event_persistence_points"], self.config.min_event_persistence_points)

    def test_isolated_spike_does_not_win_h1(self):
        coords = [(100.0 + 2.0 * index, 300.0 + index) for index in range(15)]
        coords[7] = (900.0, 900.0)

        result = optimize_trajectory(coords, frame_height=1080, config=self.config)

        evidence = result["diagnostics"][7]
        self.assertFalse(evidence["h1_event_accepted"])
        self.assertNotEqual(result["diagnostics"][8]["status"], "boundary_raw_kept")


if __name__ == "__main__":
    unittest.main()
