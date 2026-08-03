from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CoordinateSystem = Literal["wgs84", "gcj02"]
AdministrativeLevel = Literal["province", "city", "district"]
LocationResolveSource = Literal["area_city_boundary", "unavailable"]


class LocationResolveRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    coordinate_system: CoordinateSystem = "wgs84"


class LocationResolveResponse(BaseModel):
    resolved: bool
    source: LocationResolveSource
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    district: str | None = None
    address_label: str | None = None
    matched_level: AdministrativeLevel | None = None
    coordinate_system: CoordinateSystem
    boundary_coordinate_system: CoordinateSystem | None = None
    message: str | None = None
