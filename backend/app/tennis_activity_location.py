from __future__ import annotations

import sqlite3
from typing import Any

from backend.app.uploads.schemas import ActivityLocation


ACTIVITY_LOCATION_COLUMNS = (
    "location_source",
    "location_latitude",
    "location_longitude",
    "location_accuracy_m",
    "location_captured_at",
    "location_country_code",
    "location_region",
    "location_city",
    "location_district",
    "location_address_label",
    "location_coordinate_system",
)


def _row_value(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def _coarse_label(*, city: str | None, district: str | None, region: str | None) -> str | None:
    parts = [part for part in (city, district) if part]
    if parts:
        return " ".join(parts)
    return region


def activity_location_display_name(location: object | None, legacy_name: str | None = None) -> str | None:
    if legacy_name:
        return legacy_name[:120]
    if location is None:
        return None

    city = getattr(location, "city", None)
    district = getattr(location, "district", None)
    region = getattr(location, "region", None)
    address_label = getattr(location, "address_label", None)
    source = getattr(location, "source", None)
    if source in {"device_gps", "video_metadata"}:
        label = _coarse_label(city=city, district=district, region=region)
        return label[:120] if label else None
    if source == "manual_legacy" and address_label:
        return address_label[:120]
    return None


def activity_location_from_row(
    row: sqlite3.Row,
    *,
    include_exact: bool,
) -> ActivityLocation | None:
    source = _row_value(row, "location_source")
    legacy_name = _row_value(row, "location_name")
    if source is None:
        source = "manual_legacy" if legacy_name else "unavailable"

    city = _row_value(row, "location_city")
    district = _row_value(row, "location_district")
    region = _row_value(row, "location_region")
    address_label = _row_value(row, "location_address_label")
    if not include_exact:
        address_label = _coarse_label(city=city, district=district, region=region)

    if (
        source == "unavailable"
        and not any(
            _row_value(row, column)
            for column in ACTIVITY_LOCATION_COLUMNS
            if column != "location_source"
        )
        and not legacy_name
    ):
        return ActivityLocation(source="unavailable")

    return ActivityLocation(
        source=source,
        latitude=_row_value(row, "location_latitude") if include_exact else None,
        longitude=_row_value(row, "location_longitude") if include_exact else None,
        accuracy_m=_row_value(row, "location_accuracy_m") if include_exact else None,
        captured_at=_row_value(row, "location_captured_at") if include_exact else None,
        country_code=_row_value(row, "location_country_code"),
        region=region,
        city=city,
        district=district,
        address_label=address_label,
        coordinate_system=_row_value(row, "location_coordinate_system") if include_exact else None,
    )
