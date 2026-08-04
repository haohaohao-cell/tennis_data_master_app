import json
import tempfile
import unittest
from pathlib import Path

from cv.experiments.render_pipeline_overlay import load_pipeline_results


class RenderPipelineOverlayTest(unittest.TestCase):
    def test_indexes_pipeline_frames_and_net_hits(self) -> None:
        frames_payload = {
            "metadata": {"video_width": 1920, "video_height": 1080},
            "frames": [
                {"frame_index": 1, "events": {"is_hit": True}},
                {"frame_index": 0, "events": {"is_bounce": True}},
            ],
        }
        tactics_payload = {"net_hits": [{"frame": 1, "confidence": 0.8}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            frames_path = directory / "match_frames_v2.json"
            tactics_path = directory / "match_tactics_v2.json"
            frames_path.write_text(json.dumps(frames_payload), encoding="utf-8")
            tactics_path.write_text(json.dumps(tactics_payload), encoding="utf-8")
            metadata, frames, net_hits = load_pipeline_results(frames_path, tactics_path)

        self.assertEqual(metadata["video_width"], 1920)
        self.assertTrue(frames[1]["events"]["is_hit"])
        self.assertTrue(frames[0]["events"]["is_bounce"])
        self.assertEqual(net_hits[1]["confidence"], 0.8)


if __name__ == "__main__":
    unittest.main()
