import unittest

import numpy as np

from cv.court.stability import select_stable_court_matrix


def translated_homography(x: float, y: float) -> np.ndarray:
    return np.array([[1.0, 0.0, x], [0.0, 1.0, y], [0.0, 0.0, 1.0]])


class CourtStabilityTest(unittest.TestCase):
    def test_selects_medoid_from_largest_stable_group(self) -> None:
        candidates = [
            (0, translated_homography(0, 0)),
            (10, translated_homography(2, 1)),
            (20, translated_homography(3, 2)),
            (30, translated_homography(50, 50)),
            (40, None),
        ]

        result = select_stable_court_matrix(
            candidates,
            max_deviation_px=5,
            min_consensus_size=3,
        )

        self.assertEqual(result.frame_index, 10)
        self.assertEqual(result.consensus_frame_indices, (0, 10, 20))
        np.testing.assert_array_equal(result.matrix, candidates[1][1])

    def test_rejects_candidates_without_consensus(self) -> None:
        candidates = [
            (0, translated_homography(0, 0)),
            (10, translated_homography(100, 0)),
            (20, translated_homography(0, 100)),
        ]

        with self.assertRaisesRegex(RuntimeError, "did not form a stable consensus"):
            select_stable_court_matrix(
                candidates,
                max_deviation_px=5,
                min_consensus_size=2,
            )


if __name__ == "__main__":
    unittest.main()
