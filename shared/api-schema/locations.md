# Locations API Schema

Location utility endpoints live under `/api/v1`. They are stateless helpers: location endpoints do not create user records and do not persist submitted or estimated coordinates.

## Resolve Administrative Area

```text
POST /locations/resolve
```

Resolves a phone GPS coordinate to province/city/district using backend administrative boundary data. The backend implementation uses AreaCity three-level administrative boundary data, Python Shapely geometry checks, and an STRtree spatial index. It supports AreaCity raw `ok_geo.csv` with `polygon` boundaries and GeoJSON/JSON boundary files. PostGIS is not required for this stage. When boundary data is available, a coordinate that does not strictly match a polygon returns the nearest administrative area as an approximate result.

Request:

```json
{
  "latitude": 31.2304,
  "longitude": 121.4737,
  "coordinate_system": "wgs84"
}
```

Response when matched:

```json
{
  "resolved": true,
  "source": "area_city_boundary",
  "country_code": "CN",
  "region": "上海市",
  "city": "上海市",
  "district": "黄浦区",
  "address_label": "上海市 黄浦区",
  "matched_level": "district",
  "coordinate_system": "wgs84",
  "boundary_coordinate_system": "gcj02",
  "message": null
}
```

Response when boundary data or Shapely is unavailable:

```json
{
  "resolved": false,
  "source": "unavailable",
  "country_code": null,
  "region": null,
  "city": null,
  "district": null,
  "address_label": null,
  "matched_level": null,
  "coordinate_system": "wgs84",
  "boundary_coordinate_system": "gcj02",
  "message": "AreaCity boundary data was not found: backend/data/area_city_ok_geo.csv"
}
```

Rules:

- App phone coordinates are submitted as `wgs84`.
- The App maintains a foreground in-memory location cache: refresh once on app open/resume and every 3 minutes while foregrounded; feature flows should prefer the latest cached coordinate instead of blocking on a new phone-location request every time.
- Video upload and video post flows first try to read the selected media asset's embedded WGS84 location; when present, that coordinate is submitted with Activity `location.source = video_metadata` before falling back to the foreground cache.
- Boundary data path is configured by `TENNIS_AREA_CITY_BOUNDARY_PATH`; default is `backend/data/area_city_ok_geo.csv`.
- Backend boundary data coordinate system is configured by `TENNIS_AREA_CITY_COORDINATE_SYSTEM`; default is `gcj02`.
- The backend converts the submitted coordinate to the boundary coordinate system before point-in-polygon matching.
- The backend warms the boundary index during API startup so normal phone requests do not pay the first-lookup parse cost.
- If strict point-in-polygon matching misses but boundary data is loaded, this endpoint returns `resolved = true` with the nearest province/city/district and a message that the result is approximate.
- If this endpoint returns `resolved = false`, callers must still preserve any successfully captured latitude/longitude. This state means the resolver dependency or boundary data is unavailable.
- Only latitude/longitude acquisition failure should produce an Activity `location.source = unavailable`.
- No IP/network-location fallback endpoint is provided. If the phone or video file cannot provide latitude/longitude, clients must submit `location.source = unavailable`.
