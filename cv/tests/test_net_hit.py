import json
import tempfile
import unittest
from pathlib import Path

from cv.events.net_hit.detector import (
    interpolate_short_gaps,
    make_horizontal_net_line,
    signed_distance_to_line,
)
from cv.events.net_hit.track_io import load_track_from_json


class NetHitGeometryTest(unittest.TestCase):
    def test_horizontal_net_distance_and_gap_interpolation(self) -> None:
        line = make_horizontal_net_line(100.0, 200.0)
        self.assertEqual(abs(signed_distance_to_line((50.0, 110.0), line)), 10.0)

        track = [(0.0, 0.0), None, (2.0, 2.0)]
        self.assertEqual(interpolate_short_gaps(track, max_gap_frames=1)[1], (1.0, 1.0))

    def test_loads_gridtracknet_ball_coords_json(self) -> None:
        payload = {
            "metadata": {"fps": 30.0, "video_width": 1920},
            "ball_coords": [
                {"frame_index": 1, "pixel": [20, 30]},
                {"frame_index": 0, "pixel": [10, 15]},
                {"frame_index": 3, "pixel": None},
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "track.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            track, fps, frame_width = load_track_from_json(str(path))

        self.assertEqual(track, [(10.0, 15.0), (20.0, 30.0), None, None])
        self.assertEqual(fps, 30.0)
        self.assertEqual(frame_width, 1920)


if __name__ == "__main__":
    unittest.main()
