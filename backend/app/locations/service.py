from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import sys
from typing import Any

from backend.app.core.config import settings
from backend.app.locations.coordinate_system import convert_coordinate
from backend.app.locations.schemas import (
    CoordinateSystem,
    LocationResolveRequest,
    LocationResolveResponse,
)


try:
    from shapely.geometry import MultiPolygon, Point, Polygon, shape
    from shapely.strtree import STRtree
except ImportError:  # pragma: no cover - exercised in environments without optional spatial deps.
    MultiPolygon = None  # type: ignore[assignment]
    Point = None  # type: ignore[assignment]
    Polygon = None  # type: ignore[assignment]
    STRtree = None  # type: ignore[assignment]
    shape = None  # type: ignore[assignment]


LEVEL_PRIORITY = {"province": 1, "city": 2, "district": 3}
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}


@dataclass(frozen=True)
class BoundaryFeature:
    geometry: Any
    level: str
    name: str
    adcode: str | None
    parent_adcode: str | None
    region: str | None
    city: str | None
    district: str | None


@dataclass(frozen=True)
class AdministrativeAreaMatch:
    country_code: str
    region: str | None
    city: str | None
    district: str | None
    address_label: str | None
    matched_level: str


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _prop(properties: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = properties.get(key)
        if value is not None:
            return _text(value)
    return None


def _parent_adcode(properties: dict[str, Any]) -> str | None:
    parent = properties.get("parent")
    if isinstance(parent, dict):
        return _prop(parent, ("adcode", "code", "id"))
    return _prop(
        properties,
        (
            "parent_adcode",
            "parentAdcode",
            "parent_code",
            "parentCode",
            "parent_id",
            "pid",
        ),
    )


def _normalize_level(properties: dict[str, Any]) -> str | None:
    raw_level = _prop(properties, ("level", "type", "admin_level", "adminLevel"))
    if not raw_level:
        return None
    normalized = raw_level.lower()
    if normalized in {"province", "sheng", "省", "自治区", "直辖市"}:
        return "province"
    if normalized in {"city", "shi", "市", "地级市"}:
        return "city"
    if normalized in {"district", "county", "xian", "区", "县", "县级市"}:
        return "district"
    return None


def _feature_collection(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        features = payload.get("features")
        return features if isinstance(features, list) else []
    if isinstance(payload, list):
        return [feature for feature in payload if isinstance(feature, dict)]
    return []


def _level_from_areacity_deep(value: str | None) -> str | None:
    if value == "0":
        return "province"
    if value == "1":
        return "city"
    if value == "2":
        return "district"
    return None


def _closed_ring(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return []
    if points[0] != points[-1]:
        return [*points, points[0]]
    return points


def _parse_areacity_ring(raw_value: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for point_value in raw_value.split(","):
        coordinates = point_value.strip().split()
        if len(coordinates) != 2:
            continue
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except ValueError:
            continue
        points.append((longitude, latitude))
    return _closed_ring(points)


def _parse_areacity_polygon(raw_value: str) -> Any | None:
    if Polygon is None or MultiPolygon is None:
        return None
    if not raw_value or raw_value == "EMPTY":
        return None

    polygons = []
    for polygon_value in raw_value.split(";"):
        ring_values = [value.strip() for value in polygon_value.split("~") if value.strip()]
        if not ring_values:
            continue
        exterior = _parse_areacity_ring(ring_values[0])
        if not exterior:
            continue
        holes = [ring for ring in (_parse_areacity_ring(value) for value in ring_values[1:]) if ring]
        polygon = Polygon(exterior, holes)
        if polygon.is_valid and not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _compact_label(values: list[str | None]) -> str | None:
    parts: list[str] = []
    for value in values:
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts) if parts else None


class AreaCityBoundaryResolver:
    def __init__(self, *, path: Path, coordinate_system: CoordinateSystem) -> None:
        self.coordinate_system = coordinate_system
        self.path = path
        self.unavailable_reason: str | None = None
        self._boundaries: list[BoundaryFeature] = []
        self._by_adcode: dict[str, BoundaryFeature] = {}
        self._geometry_map: dict[int, BoundaryFeature] = {}
        self._level_boundaries: dict[str, list[BoundaryFeature]] = {}
        self._level_geometry_maps: dict[str, dict[int, BoundaryFeature]] = {}
        self._level_trees: dict[str, Any] = {}
        self._tree: Any = None
        self._load()

    @property
    def available(self) -> bool:
        return self._tree is not None and bool(self._boundaries)

    def _load(self) -> None:
        if Point is None or STRtree is None or shape is None:
            self.unavailable_reason = "Shapely is not installed."
            return
        if not self.path.exists():
            self.unavailable_reason = f"AreaCity boundary data was not found: {self.path}"
            return

        try:
            if self.path.suffix.lower() == ".csv":
                self._load_areacity_csv()
            else:
                self._load_geojson()
        except PermissionError:
            self.unavailable_reason = f"AreaCity boundary data permission denied: {self.path}"
            return
        except OSError as exc:
            self.unavailable_reason = f"AreaCity boundary data could not be read: {exc}"
            return

        if not self._boundaries:
            self.unavailable_reason = "AreaCity boundary data contains no usable features."
            return

        geometries = [boundary.geometry for boundary in self._boundaries]
        self._tree = STRtree(geometries)
        self._geometry_map = {id(boundary.geometry): boundary for boundary in self._boundaries}
        for level in ("district", "city", "province"):
            level_boundaries = [boundary for boundary in self._boundaries if boundary.level == level]
            if not level_boundaries:
                continue
            self._level_boundaries[level] = level_boundaries
            self._level_trees[level] = STRtree([boundary.geometry for boundary in level_boundaries])
            self._level_geometry_maps[level] = {id(boundary.geometry): boundary for boundary in level_boundaries}

    def _load_geojson(self) -> None:
        with self.path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)

        for feature in _feature_collection(payload):
            properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
            geometry_payload = feature.get("geometry")
            level = _normalize_level(properties)
            name = _prop(properties, ("name", "fullname", "full_name", "label"))
            if not geometry_payload or not level or not name:
                continue

            geometry = shape(geometry_payload)
            if geometry.is_empty:
                continue

            boundary = BoundaryFeature(
                geometry=geometry,
                level=level,
                name=name,
                adcode=_prop(properties, ("adcode", "code", "id")),
                parent_adcode=_parent_adcode(properties),
                region=_prop(properties, ("province", "province_name", "provinceName", "pname", "region")),
                city=_prop(properties, ("city", "city_name", "cityName", "cname")),
                district=_prop(properties, ("district", "district_name", "districtName", "county", "county_name")),
            )
            self._boundaries.append(boundary)
            if boundary.adcode:
                self._by_adcode[boundary.adcode] = boundary

    def _load_areacity_csv(self) -> None:
        csv.field_size_limit(min(sys.maxsize, 1024 * 1024 * 1024))
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                geometry = _parse_areacity_polygon(row.get("polygon") or "")
                if geometry is None or geometry.is_empty:
                    continue
                ext_path = (row.get("ext_path") or "").split()
                level = _level_from_areacity_deep(row.get("deep"))
                name = _text(row.get("name"))
                if not level or not name:
                    continue
                boundary = BoundaryFeature(
                    geometry=geometry,
                    level=level,
                    name=name,
                    adcode=_text(row.get("id")),
                    parent_adcode=_text(row.get("pid")),
                    region=ext_path[0] if len(ext_path) >= 1 else None,
                    city=ext_path[1] if len(ext_path) >= 2 else None,
                    district=ext_path[2] if len(ext_path) >= 3 else None,
                )
                self._boundaries.append(boundary)
                if boundary.adcode:
                    self._by_adcode[boundary.adcode] = boundary

    def _boundary_from_query_item(self, item: Any) -> BoundaryFeature | None:
        try:
            index = item.__index__()
        except (AttributeError, TypeError):
            return self._geometry_map.get(id(item))
        return self._boundaries[index] if 0 <= index < len(self._boundaries) else None

    def _level_boundary_from_query_item(self, level: str, item: Any) -> BoundaryFeature | None:
        level_boundaries = self._level_boundaries.get(level, [])
        try:
            index = item.__index__()
        except (AttributeError, TypeError):
            return self._level_geometry_maps.get(level, {}).get(id(item))
        return level_boundaries[index] if 0 <= index < len(level_boundaries) else None

    def _ancestors(self, boundary: BoundaryFeature) -> list[BoundaryFeature]:
        ancestors: list[BoundaryFeature] = []
        seen: set[str] = set()
        parent_adcode = boundary.parent_adcode
        while parent_adcode and parent_adcode not in seen:
            seen.add(parent_adcode)
            parent = self._by_adcode.get(parent_adcode)
            if parent is None:
                break
            ancestors.append(parent)
            parent_adcode = parent.parent_adcode
        return ancestors

    def _build_match(self, candidates: list[BoundaryFeature]) -> AdministrativeAreaMatch | None:
        if not candidates:
            return None

        region: str | None = None
        city: str | None = None
        district: str | None = None
        matched_level = candidates[0].level

        def apply_boundary(boundary: BoundaryFeature) -> None:
            nonlocal region, city, district
            region = region or boundary.region
            city = city or boundary.city
            district = district or boundary.district
            if boundary.level == "province":
                region = region or boundary.name
            if boundary.level == "city":
                city = city or boundary.name
            if boundary.level == "district":
                district = district or boundary.name

        for candidate in candidates:
            apply_boundary(candidate)
            for ancestor in self._ancestors(candidate):
                apply_boundary(ancestor)

        if region in MUNICIPALITIES and not city:
            city = region
        if city in MUNICIPALITIES and not region:
            region = city
        if region in MUNICIPALITIES and district and not city:
            city = region

        return AdministrativeAreaMatch(
            country_code="CN",
            region=region,
            city=city,
            district=district,
            address_label=_compact_label([region if region != city else None, city, district]),
            matched_level=matched_level,
        )

    def resolve(self, *, latitude: float, longitude: float) -> AdministrativeAreaMatch | None:
        if not self.available:
            return None

        point = Point(longitude, latitude)
        candidates: list[BoundaryFeature] = []
        for item in self._tree.query(point):
            boundary = self._boundary_from_query_item(item)
            if boundary is not None and boundary.geometry.covers(point):
                candidates.append(boundary)

        candidates.sort(key=lambda boundary: (-LEVEL_PRIORITY[boundary.level], boundary.geometry.area))
        return self._build_match(candidates)

    def resolve_nearest(self, *, latitude: float, longitude: float) -> AdministrativeAreaMatch | None:
        if not self.available:
            return None

        point = Point(longitude, latitude)
        for level in ("district", "city", "province"):
            tree = self._level_trees.get(level)
            if tree is None:
                continue
            item = tree.nearest(point)
            boundary = self._level_boundary_from_query_item(level, item)
            if boundary is not None:
                return self._build_match([boundary])
        return None


def _boundary_file_cache_key(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return 0, 0
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=8)
def _resolver(
    path: str,
    coordinate_system: CoordinateSystem,
    mtime_ns: int,
    size_bytes: int,
) -> AreaCityBoundaryResolver:
    _ = (mtime_ns, size_bytes)
    return AreaCityBoundaryResolver(path=Path(path), coordinate_system=coordinate_system)


def _boundary_coordinate_system() -> CoordinateSystem:
    raw_value = settings.area_city_boundary_coordinate_system.strip().lower()
    if raw_value == "wgs84":
        return "wgs84"
    return "gcj02"


def warm_location_resolver_cache() -> None:
    boundary_coordinate_system = _boundary_coordinate_system()
    mtime_ns, size_bytes = _boundary_file_cache_key(settings.area_city_boundary_path)
    _resolver(
        str(settings.area_city_boundary_path),
        boundary_coordinate_system,
        mtime_ns,
        size_bytes,
    )


def resolve_administrative_location(payload: LocationResolveRequest) -> LocationResolveResponse:
    boundary_coordinate_system = _boundary_coordinate_system()
    mtime_ns, size_bytes = _boundary_file_cache_key(settings.area_city_boundary_path)
    resolver = _resolver(
        str(settings.area_city_boundary_path),
        boundary_coordinate_system,
        mtime_ns,
        size_bytes,
    )
    lookup_latitude, lookup_longitude = convert_coordinate(
        latitude=payload.latitude,
        longitude=payload.longitude,
        source=payload.coordinate_system,
        target=boundary_coordinate_system,
    )
    strict_match = resolver.resolve(latitude=lookup_latitude, longitude=lookup_longitude)
    nearest_match = None
    if strict_match is None or strict_match.district is None:
        nearest_match = resolver.resolve_nearest(latitude=lookup_latitude, longitude=lookup_longitude)

    match = nearest_match or strict_match
    approximate = nearest_match is not None
    if match is None:
        return LocationResolveResponse(
            resolved=False,
            source="unavailable",
            coordinate_system=payload.coordinate_system,
            boundary_coordinate_system=boundary_coordinate_system,
            message=resolver.unavailable_reason or "AreaCity boundary data did not provide a usable administrative area.",
        )

    return LocationResolveResponse(
        resolved=True,
        source="area_city_boundary",
        country_code=match.country_code,
        region=match.region,
        city=match.city,
        district=match.district,
        address_label=match.address_label,
        matched_level=match.matched_level,  # type: ignore[arg-type]
        coordinate_system=payload.coordinate_system,
        boundary_coordinate_system=boundary_coordinate_system,
        message="已返回最近的 AreaCity 行政区近似结果。" if approximate else None,
    )
