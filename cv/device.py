"""PyTorch device selection shared by CV training and inference entry points."""

from __future__ import annotations

import torch


def get_torch_device() -> torch.device:
    """Select the fastest available PyTorch backend."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def resolve_torch_device(device: str | torch.device | None = None) -> torch.device:
    """Resolve ``auto``/unset while honoring an explicitly requested device."""
    if device is None or str(device) == "auto":
        return get_torch_device()
    return torch.device(device)
