from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request


def _has_shapely() -> bool:
    try:
        import shapely  # noqa: F401
    except ImportError:
        return False
    return True


def _write_boundary_fixture(path: Path) -> None:
    def polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
        return (
            f"{min_lon} {min_lat},{max_lon} {min_lat},{max_lon} {max_lat},"
            f"{min_lon} {max_lat},{min_lon} {min_lat}"
        )

    rows = [
        "id,pid,deep,name,ext_path,polygon",
        f'310000,0,0,上海市,上海市,"{polygon(120.0, 30.0, 122.0, 32.0)}"',
        f'310100,310000,1,上海市,上海市 上海市,"{polygon(120.5, 30.5, 121.5, 31.5)}"',
        f'310101,310100,2,黄浦区,上海市 上海市 黄浦区,"{polygon(120.9, 30.9, 121.1, 31.1)}"',
    ]
    path.write_text("\n".join(rows), encoding="utf-8")


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        boundary_path = temp_path / "area_city_ok_geo.csv"
        _write_boundary_fixture(boundary_path)

        os.environ["TENNIS_DB_PATH"] = str(temp_path / "location_api_smoke.sqlite3")
        os.environ["TENNIS_AREA_CITY_BOUNDARY_PATH"] = str(boundary_path)
        os.environ["TENNIS_AREA_CITY_COORDINATE_SYSTEM"] = "wgs84"

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        resolved = await asgi_request(
            app,
            "POST",
            "/api/v1/locations/resolve",
            {"latitude": 31.0, "longitude": 121.0, "coordinate_system": "wgs84"},
        )
        assert resolved.status == 200, resolved
        if _has_shapely():
            assert resolved.json_body["resolved"] is True, resolved
            assert resolved.json_body["source"] == "area_city_boundary"
            assert resolved.json_body["region"] == "上海市"
            assert resolved.json_body["city"] == "上海市"
            assert resolved.json_body["district"] == "黄浦区"
            assert resolved.json_body["matched_level"] == "district"
        else:
            assert resolved.json_body["resolved"] is False, resolved
            assert resolved.json_body["source"] == "unavailable"

        approximate = await asgi_request(
            app,
            "POST",
            "/api/v1/locations/resolve",
            {"latitude": 31.7, "longitude": 121.7, "coordinate_system": "wgs84"},
        )
        assert approximate.status == 200, approximate
        if _has_shapely():
            assert approximate.json_body["resolved"] is True, approximate
            assert approximate.json_body["source"] == "area_city_boundary"
            assert approximate.json_body["region"] == "上海市"
            assert approximate.json_body["city"] == "上海市"
            assert approximate.json_body["district"] is not None
            assert approximate.json_body["message"] == "已返回最近的 AreaCity 行政区近似结果。"
        else:
            assert approximate.json_body["resolved"] is False, approximate
            assert approximate.json_body["source"] == "unavailable"

        invalid = await asgi_request(
            app,
            "POST",
            "/api/v1/locations/resolve",
            {"latitude": 91, "longitude": 121.0, "coordinate_system": "wgs84"},
        )
        assert invalid.status == 422, invalid

        print("Location API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
