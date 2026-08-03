# Backend Boundary Data

Administrative-area lookup reads AreaCity boundary data from. If strict point-in-polygon matching fails, the backend returns the nearest AreaCity boundary as an approximate result for prototype usability:

```text
backend/data/area_city_ok_geo.csv
```

The default CSV is large and is not committed to Git. Download and extract it to the correct path with:

```text
conda run -n tennis python scripts/download_area_city_data.py
```

Override the path with:

```text
TENNIS_AREA_CITY_BOUNDARY_PATH=/absolute/path/to/ok_geo.csv
```

The default coordinate system is `gcj02`, matching AreaCity `ok_geo.csv` boundaries. Override only when the boundary file has already been converted:

```text
TENNIS_AREA_CITY_COORDINATE_SYSTEM=wgs84
```

Run the script again with `--force` to overwrite the existing CSV:

```text
conda run -n tennis python scripts/download_area_city_data.py --force
```


The backend supports:

- AreaCity raw `ok_geo.csv` with `id`, `pid`, `deep`, `name`, `ext_path`, and `polygon`.
- GeoJSON / JSON FeatureCollection files with `province`, `city`, `district`, `adcode`, `parent`, `level`, and `geometry`-style properties.

Do not commit large downloaded boundary files unless the product owner explicitly approves storing that data in this repository.
