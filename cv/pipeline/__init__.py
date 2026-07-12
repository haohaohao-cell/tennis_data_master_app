"""End-to-end CV pipeline orchestration."""

from __future__ import annotations

from typing import Any


def run_inference_v2(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    from .inference import run_inference_v2 as _run_inference_v2

    return _run_inference_v2(*args, **kwargs)

__all__ = ["run_inference_v2"]
