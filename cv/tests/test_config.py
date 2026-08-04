import unittest

from cv import config


class ConfigPathsTest(unittest.TestCase):
    def test_runtime_paths_are_rooted_under_cv(self) -> None:
        self.assertTrue(config.CV_ROOT.is_absolute())
        self.assertEqual(config.INPUT_DIR, config.CV_ROOT / "data" / "input")
        self.assertEqual(config.OUTPUT_DIR, config.CV_ROOT / "data" / "output")
        self.assertEqual(config.DEFAULT_BALL_MODEL_PATH, config.CV_ROOT / "models" / "weights" / "model_best.pt")
        self.assertEqual(
            config.DEFAULT_GRIDTRACKNET_MODEL_PATH,
            config.CV_ROOT / "models" / "weights" / "model_weights.h5",
        )


if __name__ == "__main__":
    unittest.main()
