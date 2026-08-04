from .detector import NetHitConfig, NetHitEvent, detect_net_hits, make_horizontal_net_line

__all__ = [
    "NetHitConfig",
    "NetHitEvent",
    "detect_net_hits",
    "make_horizontal_net_line",
    "CurvedNetHitConfig",
    "CurvedNetHitEvent",
    "NetBandConfig",
    "NetBandModel",
    "detect_curved_net_hits",
    "fit_net_band_from_samples",
    "run_curved_net_hit_detection",
]


def __getattr__(name: str):
    """Load curved-net dependencies only for callers that request them."""

    if name in {"CurvedNetHitConfig", "CurvedNetHitEvent", "detect_curved_net_hits"}:
        from . import curved_detector

        return getattr(curved_detector, name)
    if name in {"NetBandConfig", "NetBandModel", "fit_net_band_from_samples"}:
        from . import curved_geometry

        return getattr(curved_geometry, name)
    if name == "run_curved_net_hit_detection":
        from .curved_video import run_curved_net_hit_detection

        return run_curved_net_hit_detection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
