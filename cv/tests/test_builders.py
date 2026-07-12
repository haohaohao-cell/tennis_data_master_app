import unittest

from cv.builders.match import build_metadata, build_shots_and_points_payloads
from cv.scripts.split_video_by_point import build_metadata as compatibility_build_metadata


class PayloadBuilderTest(unittest.TestCase):
    def test_metadata_compatibility_export(self) -> None:
        expected = build_metadata(25.0, 1920, 1080, 250)
        self.assertEqual(compatibility_build_metadata(25.0, 1920, 1080, 250), expected)
        self.assertEqual(expected["version"], "2.0.0")

    def test_empty_point_payload_keeps_contract(self) -> None:
        frames_payload = {
            "metadata": {"fps": 10.0},
            "frames": [
                {
                    "frame_index": 0,
                    "time_sec": 0.0,
                    "ball": None,
                    "players": [],
                    "events": {"is_hit": False, "is_bounce": False, "is_net_hit": False},
                }
            ],
        }
        points_index = {
            "source_video": "match.mp4",
            "segments": [
                {
                    "segment_id": 1,
                    "start_frame": 0,
                    "end_frame": 0,
                    "duration_frames": 1,
                    "start_time_sec": 0.0,
                    "end_time_sec": 0.1,
                    "duration_sec": 0.1,
                }
            ],
        }

        _, shots, points = build_shots_and_points_payloads(
            frames_payload,
            points_index,
            {"net_hits": []},
            "upload_1",
        )

        self.assertEqual(shots["metadata"]["shot_count"], 0)
        self.assertEqual(points["metadata"]["point_count"], 1)
        self.assertEqual(points["points"][0]["point_id"], "upload_1_point_001")


if __name__ == "__main__":
    unittest.main()
