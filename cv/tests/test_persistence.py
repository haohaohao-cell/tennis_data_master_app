import tempfile
import unittest
from pathlib import Path

from cv.persistence.repository import TennisAnalysisRepository
from cv.scripts.db_operations import TennisAnalysisRepository as PublicRepository


class RepositoryTest(unittest.TestCase):
    def test_public_repository_path_and_bundle_round_trip(self) -> None:
        self.assertIs(PublicRepository, TennisAnalysisRepository)

        with tempfile.TemporaryDirectory() as directory:
            repository = TennisAnalysisRepository(Path(directory) / "analysis.sqlite")
            bundle = repository.save_upload_analysis_bundle(
                upload_row={
                    "upload_id": "upload_1",
                    "user_id": "user_1",
                    "original_filename": "match.mp4",
                    "stored_path": "cv/data/output/match.mp4",
                    "status": "completed",
                },
                points_payload={
                    "points": [
                        {
                            "point_id": "point_1",
                            "upload_id": "upload_1",
                            "point_index": 1,
                            "start_frame": 0,
                            "end_frame": 20,
                            "start_time": 0.0,
                            "end_time": 2.0,
                            "duration_sec": 2.0,
                        }
                    ]
                },
                shots_payload={
                    "shots": [
                        {
                            "shot_id": "shot_1",
                            "point_id": "point_1",
                            "shot_index": 1,
                            "contact_frame": 5,
                            "contact_time": 0.5,
                            "point_ending": 0,
                        }
                    ]
                },
            )

            self.assertEqual(bundle["upload"]["upload_id"], "upload_1")
            self.assertEqual([row["point_id"] for row in bundle["points"]], ["point_1"])
            self.assertEqual([row["shot_id"] for row in bundle["shots"]], ["shot_1"])


if __name__ == "__main__":
    unittest.main()
