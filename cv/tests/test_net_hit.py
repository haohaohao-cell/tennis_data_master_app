import unittest

from cv.events.net_hit.detector import (
    interpolate_short_gaps,
    make_horizontal_net_line,
    signed_distance_to_line,
)


class NetHitGeometryTest(unittest.TestCase):
    def test_horizontal_net_distance_and_gap_interpolation(self) -> None:
        line = make_horizontal_net_line(100.0, 200.0)
        self.assertEqual(abs(signed_distance_to_line((50.0, 110.0), line)), 10.0)

        track = [(0.0, 0.0), None, (2.0, 2.0)]
        self.assertEqual(interpolate_short_gaps(track, max_gap_frames=1)[1], (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
