import unittest

from cv.segmentation.points import (
    SegmentationConfig,
    detect_segments_with_court_visibility,
    filter_segments,
    summarize_segments_with_court_visibility,
)


def frame(*, ball: bool = True, players: bool = True, court: bool = True) -> dict:
    return {
        "ball": {"pixel": [100, 100]} if ball else None,
        "players": [{"id": 1}, {"id": 2}] if players else [],
        "court_visible": court,
        "events": {"is_hit": False, "is_bounce": False},
    }


class PointSegmentationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fps = 10.0
        self.config = SegmentationConfig(
            ball_break_sec=0.3,
            ball_break_sec_with_players=0.3,
            players_break_sec=0.3,
            court_break_sec=0.3,
            min_segment_sec=0.2,
            start_ball_ratio=0.1,
            start_players_ratio=0.1,
            start_court_ratio=0.1,
            min_ball_frames=1,
            min_player_frames=1,
            min_court_frames=1,
            min_both_players_ratio=0.5,
            min_both_players_total_sec=0.2,
        )

    def test_detects_supported_segment_and_summarizes_signals(self) -> None:
        frames = [frame() for _ in range(10)]
        segments = detect_segments_with_court_visibility(frames, self.fps, self.config)

        self.assertEqual(len(segments), 1)
        summary = summarize_segments_with_court_visibility(frames, self.fps, segments[0])
        self.assertEqual(summary["tracknet_ratio"], 1.0)
        self.assertEqual(summary["both_players_ratio"], 1.0)
        self.assertEqual(summary["court_signal_ratio"], 1.0)
        self.assertEqual(len(filter_segments([summary], self.fps, self.config)), 1)

    def test_filter_rejects_segment_without_both_players(self) -> None:
        frames = [frame(players=False) for _ in range(10)]
        segment = {"segment_id": 1, "start_frame": 0, "end_frame": 9, "duration_frames": 10, "end_reasons": ["video_end"]}
        summary = summarize_segments_with_court_visibility(frames, self.fps, segment)

        self.assertEqual(filter_segments([summary], self.fps, self.config), [])


if __name__ == "__main__":
    unittest.main()
