from __future__ import annotations

import math

from backend.app.locations.schemas import CoordinateSystem


_PI = math.pi
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(latitude: float, longitude: float) -> bool:
    return longitude < 72.004 or longitude > 137.8347 or latitude < 0.8293 or latitude > 55.8271


def _transform_latitude(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_longitude(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(latitude: float, longitude: float) -> tuple[float, float]:
    if _out_of_china(latitude, longitude):
        return latitude, longitude

    d_lat = _transform_latitude(longitude - 105.0, latitude - 35.0)
    d_lon = _transform_longitude(longitude - 105.0, latitude - 35.0)
    rad_lat = latitude / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    d_lon = (d_lon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * _PI)
    return latitude + d_lat, longitude + d_lon


def gcj02_to_wgs84(latitude: float, longitude: float) -> tuple[float, float]:
    if _out_of_china(latitude, longitude):
        return latitude, longitude

    gcj_latitude, gcj_longitude = wgs84_to_gcj02(latitude, longitude)
    return latitude * 2 - gcj_latitude, longitude * 2 - gcj_longitude


def convert_coordinate(
    *,
    latitude: float,
    longitude: float,
    source: CoordinateSystem,
    target: CoordinateSystem,
) -> tuple[float, float]:
    if source == target:
        return latitude, longitude
    if source == "wgs84" and target == "gcj02":
        return wgs84_to_gcj02(latitude, longitude)
    if source == "gcj02" and target == "wgs84":
        return gcj02_to_wgs84(latitude, longitude)
    return latitude, longitude
