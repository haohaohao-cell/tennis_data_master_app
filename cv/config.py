"""Central filesystem locations for the CV package."""

import os
from pathlib import Path


CV_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CV_ROOT.parent
DATA_ROOT = CV_ROOT / "data"
INPUT_DIR = DATA_ROOT / "input"
OUTPUT_DIR = DATA_ROOT / "output"
SAMPLES_DIR = DATA_ROOT / "samples"
MODELS_DIR = CV_ROOT / "models"
WEIGHTS_DIR = MODELS_DIR / "weights"
EXPERIMENTS_DIR = CV_ROOT / "experiments"

DEFAULT_BALL_MODEL_PATH = WEIGHTS_DIR / "model_best.pt"
DEFAULT_GRIDTRACKNET_MODEL_PATH = Path(
    os.environ.get("GRIDTRACKNET_MODEL_PATH", WEIGHTS_DIR / "model_weights.h5")
)
DEFAULT_PLAYER_MODEL_PATH = WEIGHTS_DIR / "yolov8m.pt"
DEFAULT_COURT_MODEL_PATH = WEIGHTS_DIR / "model_tennis_court_det.pt"
# Kept as a source-compatible placeholder for repository constructors. CV
# persistence now uses PostgreSQL and never opens this path.
DEFAULT_DB_PATH = OUTPUT_DIR / "match_analysis.postgres"


def ensure_runtime_directories() -> None:
    """Create local runtime directories without touching tracked samples."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
