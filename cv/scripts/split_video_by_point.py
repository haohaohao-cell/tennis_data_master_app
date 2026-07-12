"""Compatibility CLI for point segmentation and video splitting."""

from cv.segmentation.video import *  # noqa: F401,F403
from cv.segmentation.video import main

_BUILDER_EXPORTS = {
    "build_match_frames_payload",
    "build_match_tactics_payload",
    "build_metadata",
    "build_points_index_payload",
    "build_shots_and_points_payloads",
}


def __getattr__(name: str):
    if name in _BUILDER_EXPORTS:
        from cv.builders import match

        return getattr(match, name)
    raise AttributeError(name)

if __name__ == "__main__":
    raise SystemExit(main())
