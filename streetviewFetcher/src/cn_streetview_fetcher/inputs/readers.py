"""Input loading and lightweight geospatial sampling."""

from collections import Counter
import hashlib
import json
from math import cos, radians
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from cn_streetview_fetcher.inputs.models import InputReadError, InputReadResult, InputStats, PointRecord

CoordPair = tuple[float, float]
BBox = tuple[float, float, float, float]

_SUPPORTED_TABLE_SUFFIXES = {".csv", ".xls", ".xlsx"}
_SUPPORTED_COORD_SYS = {"wgs84", "gcj02", "bd09"}
_SUPPORTED_PROVIDERS = {"baidu", "tencent", "both", "from_table"}


def read_points(
    path: Path | None,
    coord_sys: str,
    input_type: str = "table",
    spacing_meters: float = 50.0,
    bbox: BBox | None = None,
    polygon: list[CoordPair] | None = None,
) -> list[PointRecord]:
    """Read input data and return normalized points."""
    return read_input(path, coord_sys, input_type, spacing_meters, bbox, polygon).points


def read_input(
    path: Path | None,
    coord_sys: str,
    input_type: str = "table",
    spacing_meters: float = 50.0,
    bbox: BBox | None = None,
    polygon: list[CoordPair] | None = None,
) -> InputReadResult:
    """Read supported input formats and return records, warnings, and stats."""
    _validate_coord_sys(coord_sys, "global coord_sys")
    if spacing_meters <= 0:
        raise InputReadError("spacing_meters must be greater than 0.")

    warnings: list[str] = []
    if input_type == "table":
        points = _read_table(path, coord_sys)
    elif input_type == "geojson":
        points = _read_geojson(path, coord_sys, spacing_meters)
    elif input_type == "bbox":
        resolved_bbox = bbox or _read_bbox_file(path)
        points = sample_bbox(resolved_bbox, spacing_meters, coord_sys)
    elif input_type == "polygon":
        resolved_polygon = polygon or _read_polygon_file(path)
        points = sample_polygon(resolved_polygon, spacing_meters, coord_sys)
    else:
        raise InputReadError(f"Unsupported input_type: {input_type}")

    return InputReadResult(points=points, warnings=warnings, stats=_build_stats(points))


def sample_bbox(bbox: BBox, spacing_meters: float, coord_sys: str) -> list[PointRecord]:
    """Sample points inside a bbox in ``min_lng,min_lat,max_lng,max_lat`` order."""
    min_lng, min_lat, max_lng, max_lat = _validate_bbox(bbox)
    lng_step, lat_step = _meter_steps(spacing_meters, (min_lat + max_lat) / 2)
    points: list[PointRecord] = []
    lat = min_lat
    while lat <= max_lat + 1e-12:
        lng = min_lng
        while lng <= max_lng + 1e-12:
            normalized_lng = min(round(lng, 8), max_lng)
            normalized_lat = min(round(lat, 8), max_lat)
            point_id = _stable_id("bbox", normalized_lng, normalized_lat, coord_sys, spacing_meters)
            points.append(PointRecord(point_id=point_id, lng=normalized_lng, lat=normalized_lat, coord_sys=coord_sys))
            lng += lng_step
        lat += lat_step
    return points


def sample_polygon(polygon: Sequence[CoordPair], spacing_meters: float, coord_sys: str) -> list[PointRecord]:
    """Sample points inside a polygon and keep only points within the polygon."""
    normalized_polygon = _validate_polygon(polygon)
    min_lng = min(lng for lng, _lat in normalized_polygon)
    max_lng = max(lng for lng, _lat in normalized_polygon)
    min_lat = min(lat for _lng, lat in normalized_polygon)
    max_lat = max(lat for _lng, lat in normalized_polygon)
    candidates = sample_bbox((min_lng, min_lat, max_lng, max_lat), spacing_meters, coord_sys)
    points: list[PointRecord] = []
    for candidate in candidates:
        if _point_in_polygon((candidate.lng, candidate.lat), normalized_polygon):
            point_id = _stable_id("polygon", candidate.lng, candidate.lat, coord_sys, spacing_meters)
            points.append(
                PointRecord(point_id=point_id, lng=candidate.lng, lat=candidate.lat, coord_sys=coord_sys)
            )
    return points


def _read_table(path: Path | None, default_coord_sys: str) -> list[PointRecord]:
    """Read a CSV or Excel coordinate table."""
    input_path = _require_path(path)
    suffix = input_path.suffix.lower()
    if suffix not in _SUPPORTED_TABLE_SUFFIXES:
        raise InputReadError(f"Unsupported table file extension: {suffix}")
    frame = pd.read_csv(input_path) if suffix == ".csv" else pd.read_excel(input_path)
    columns = {_normalize_column(column): column for column in frame.columns}
    if "lng" not in columns or "lat" not in columns:
        raise InputReadError("Coordinate table must contain lng and lat columns.")

    points: list[PointRecord] = []
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        lng = _to_float(row[columns["lng"]], "lng", row_number)
        lat = _to_float(row[columns["lat"]], "lat", row_number)
        _validate_lng_lat(lng, lat, f"row {row_number}")
        row_coord_sys = _optional_str(row, columns, "coord_sys") or default_coord_sys
        _validate_coord_sys(row_coord_sys, f"row {row_number} coord_sys")
        provider = _optional_str(row, columns, "provider")
        if provider is not None and provider not in _SUPPORTED_PROVIDERS:
            raise InputReadError(f"Unsupported provider '{provider}' at row {row_number}.")
        panoid = _optional_str(row, columns, "panoid")
        heading = _optional_float(row, columns, "heading", row_number)
        pitch = _optional_float(row, columns, "pitch", row_number)
        fov = _optional_float(row, columns, "fov", row_number)
        tag = _optional_str(row, columns, "tag")
        raw_id = _optional_str(row, columns, "id")
        point_id = raw_id or _stable_id("table", lng, lat, row_coord_sys, provider, panoid, heading, pitch, fov, tag)
        points.append(
            PointRecord(
                point_id=point_id,
                lng=lng,
                lat=lat,
                coord_sys=row_coord_sys,
                provider=provider,
                panoid=panoid,
                heading=heading,
                pitch=pitch,
                fov=fov,
                tag=tag,
            )
        )
    return points


def _read_geojson(path: Path | None, default_coord_sys: str, spacing_meters: float) -> list[PointRecord]:
    """Read GeoJSON point, line, and polygon geometries."""
    input_path = _require_path(path)
    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    features = _geojson_features(data)
    points: list[PointRecord] = []
    for index, feature in enumerate(features, start=1):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        coord_sys = str(properties.get("coord_sys") or default_coord_sys)
        _validate_coord_sys(coord_sys, f"feature {index} coord_sys")
        provider = _clean_optional(properties.get("provider"))
        tag = _clean_optional(properties.get("tag"))
        prefix = _clean_optional(properties.get("id")) or f"feature_{index}"
        generated = _points_from_geometry(geometry, spacing_meters, coord_sys, prefix, provider, tag)
        points.extend(generated)
    return points


def _points_from_geometry(
    geometry: dict[str, Any], spacing_meters: float, coord_sys: str, prefix: str, provider: str | None, tag: str | None
) -> list[PointRecord]:
    """Convert a GeoJSON geometry into sampled points."""
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        lng, lat = _coord_pair(coordinates, "GeoJSON Point")
        point_id = _stable_id("geojson", prefix, lng, lat, coord_sys)
        return [PointRecord(point_id=point_id, lng=lng, lat=lat, coord_sys=coord_sys, provider=provider, tag=tag)]
    if geometry_type == "MultiPoint":
        return [
            PointRecord(
                point_id=_stable_id("geojson", prefix, lng, lat, coord_sys),
                lng=lng,
                lat=lat,
                coord_sys=coord_sys,
                provider=provider,
                tag=tag,
            )
            for lng, lat in (_coord_pair(value, "GeoJSON MultiPoint") for value in coordinates)
        ]
    if geometry_type == "LineString":
        return _sample_line(coordinates, spacing_meters, coord_sys, prefix, provider, tag)
    if geometry_type == "MultiLineString":
        points: list[PointRecord] = []
        for line_index, line in enumerate(coordinates):
            points.extend(_sample_line(line, spacing_meters, coord_sys, f"{prefix}_line_{line_index}", provider, tag))
        return points
    if geometry_type == "Polygon":
        polygon = [_coord_pair(value, "GeoJSON Polygon") for value in coordinates[0]]
        sampled = sample_polygon(polygon, spacing_meters, coord_sys)
        return [_with_meta(point, _stable_id("geojson", prefix, point.lng, point.lat, coord_sys), provider, tag) for point in sampled]
    if geometry_type == "MultiPolygon":
        points = []
        for polygon_index, polygon_group in enumerate(coordinates):
            polygon = [_coord_pair(value, "GeoJSON MultiPolygon") for value in polygon_group[0]]
            sampled = sample_polygon(polygon, spacing_meters, coord_sys)
            points.extend(
                _with_meta(point, _stable_id("geojson", prefix, polygon_index, point.lng, point.lat, coord_sys), provider, tag)
                for point in sampled
            )
        return points
    raise InputReadError(f"Unsupported GeoJSON geometry type: {geometry_type}")


def _sample_line(
    coordinates: Sequence[Any],
    spacing_meters: float,
    coord_sys: str,
    prefix: str,
    provider: str | None,
    tag: str | None,
) -> list[PointRecord]:
    """Sample points along a GeoJSON line."""
    pairs = [_coord_pair(value, "GeoJSON LineString") for value in coordinates]
    if len(pairs) < 2:
        raise InputReadError("GeoJSON LineString must contain at least two coordinates.")
    points: list[PointRecord] = []
    for segment_index, (start, end) in enumerate(zip(pairs, pairs[1:])):
        distance = _distance_meters(start, end)
        steps = max(1, int(distance // spacing_meters))
        for step in range(steps + 1):
            ratio = step / steps
            lng = round(start[0] + (end[0] - start[0]) * ratio, 8)
            lat = round(start[1] + (end[1] - start[1]) * ratio, 8)
            point_id = _stable_id("geojson-line", prefix, segment_index, lng, lat, coord_sys)
            points.append(PointRecord(point_id=point_id, lng=lng, lat=lat, coord_sys=coord_sys, provider=provider, tag=tag))
    return _dedupe_points(points)


def _read_bbox_file(path: Path | None) -> BBox:
    """Read bbox from a simple JSON or GeoJSON file."""
    input_path = _require_path(path)
    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and "bbox" in data:
        bbox = data["bbox"]
        return _validate_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
    features = _geojson_features(data)
    pairs: list[CoordPair] = []
    for feature in features:
        pairs.extend(_flatten_geojson_coordinates(feature.get("geometry", {}).get("coordinates")))
    if not pairs:
        raise InputReadError("Could not derive bbox from input file.")
    return _validate_bbox((min(lng for lng, _ in pairs), min(lat for _, lat in pairs), max(lng for lng, _ in pairs), max(lat for _, lat in pairs)))


def _read_polygon_file(path: Path | None) -> list[CoordPair]:
    """Read a polygon from JSON or GeoJSON."""
    input_path = _require_path(path)
    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and "polygon" in data:
        return _validate_polygon([_coord_pair(value, "polygon") for value in data["polygon"]])
    features = _geojson_features(data)
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Polygon":
            return _validate_polygon([_coord_pair(value, "GeoJSON Polygon") for value in geometry["coordinates"][0]])
        if geometry.get("type") == "MultiPolygon":
            return _validate_polygon([_coord_pair(value, "GeoJSON MultiPolygon") for value in geometry["coordinates"][0][0]])
    raise InputReadError("No polygon geometry found in input file.")


def _build_stats(points: list[PointRecord]) -> InputStats:
    """Build input statistics for UI previews."""
    return InputStats(
        total_points=len(points),
        coord_sys_counts=dict(Counter(point.coord_sys for point in points)),
        provider_counts=dict(Counter(point.provider or "" for point in points if point.provider)),
        tag_counts=dict(Counter(point.tag or "" for point in points if point.tag)),
    )


def _require_path(path: Path | None) -> Path:
    """Return an existing path or raise a clear input error."""
    if path is None:
        raise InputReadError("input_path is required for this input type.")
    if not path.exists():
        raise InputReadError(f"Input file does not exist: {path}")
    return path


def _normalize_column(column: Any) -> str:
    """Normalize table column names."""
    return str(column).strip().lower()


def _clean_optional(value: Any) -> str | None:
    """Convert an optional scalar to a cleaned string."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _optional_str(row: Any, columns: dict[str, Any], name: str) -> str | None:
    """Read an optional string column from a row."""
    if name not in columns:
        return None
    return _clean_optional(row[columns[name]])


def _optional_float(row: Any, columns: dict[str, Any], name: str, row_number: int) -> float | None:
    """Read an optional float column from a row."""
    if name not in columns:
        return None
    value = row[columns[name]]
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return _to_float(value, name, row_number)


def _to_float(value: Any, field_name: str, row_number: int) -> float:
    """Convert a table value to float with row context."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InputReadError(f"Invalid {field_name} at row {row_number}: {value!r}") from exc


def _validate_lng_lat(lng: float, lat: float, context: str) -> None:
    """Validate longitude and latitude ranges."""
    if lng < -180 or lng > 180:
        raise InputReadError(f"Invalid longitude at {context}: {lng}. Expected -180..180.")
    if lat < -90 or lat > 90:
        raise InputReadError(f"Invalid latitude at {context}: {lat}. Expected -90..90.")


def _validate_coord_sys(coord_sys: str, context: str) -> None:
    """Validate coordinate system names."""
    if coord_sys not in _SUPPORTED_COORD_SYS:
        raise InputReadError(f"Unsupported {context}: {coord_sys}. Expected one of {sorted(_SUPPORTED_COORD_SYS)}.")


def _validate_bbox(bbox: BBox) -> BBox:
    """Validate a bbox and return it."""
    min_lng, min_lat, max_lng, max_lat = bbox
    _validate_lng_lat(min_lng, min_lat, "bbox min")
    _validate_lng_lat(max_lng, max_lat, "bbox max")
    if min_lng >= max_lng or min_lat >= max_lat:
        raise InputReadError("bbox must be in min_lng,min_lat,max_lng,max_lat order.")
    return bbox


def _validate_polygon(polygon: Sequence[CoordPair]) -> list[CoordPair]:
    """Validate polygon coordinates and close the ring if needed."""
    if len(polygon) < 3:
        raise InputReadError("polygon must contain at least three coordinates.")
    normalized = [(float(lng), float(lat)) for lng, lat in polygon]
    for lng, lat in normalized:
        _validate_lng_lat(lng, lat, "polygon")
    if normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return normalized


def _meter_steps(spacing_meters: float, latitude: float) -> tuple[float, float]:
    """Return approximate longitude and latitude degree steps for meter spacing."""
    lat_step = spacing_meters / 111_320.0
    lng_scale = max(cos(radians(latitude)), 0.01)
    lng_step = spacing_meters / (111_320.0 * lng_scale)
    return lng_step, lat_step


def _distance_meters(start: CoordPair, end: CoordPair) -> float:
    """Approximate distance between two lon/lat pairs in meters."""
    mid_lat = (start[1] + end[1]) / 2
    lng_scale = 111_320.0 * max(cos(radians(mid_lat)), 0.01)
    dx = (end[0] - start[0]) * lng_scale
    dy = (end[1] - start[1]) * 111_320.0
    return (dx * dx + dy * dy) ** 0.5


def _point_in_polygon(point: CoordPair, polygon: Sequence[CoordPair]) -> bool:
    """Return whether a point is inside a polygon using ray casting."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:]):
        if _point_on_segment(point, (x1, y1), (x2, y2)):
            return True
        intersects = (y1 > y) != (y2 > y)
        if intersects:
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= x_intersect:
                inside = not inside
    return inside


def _point_on_segment(point: CoordPair, start: CoordPair, end: CoordPair) -> bool:
    """Return whether a point lies on a line segment."""
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (y - y1) * (x2 - x1) - (x - x1) * (y2 - y1)
    if abs(cross) > 1e-10:
        return False
    return min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10


def _geojson_features(data: Any) -> list[dict[str, Any]]:
    """Return feature dictionaries from common GeoJSON roots."""
    if not isinstance(data, dict):
        raise InputReadError("GeoJSON root must be an object.")
    data_type = data.get("type")
    if data_type == "FeatureCollection":
        return list(data.get("features") or [])
    if data_type == "Feature":
        return [data]
    if data_type in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        return [{"type": "Feature", "geometry": data, "properties": {}}]
    raise InputReadError(f"Unsupported GeoJSON root type: {data_type}")


def _coord_pair(value: Any, context: str) -> CoordPair:
    """Parse one GeoJSON coordinate pair."""
    if not isinstance(value, Sequence) or len(value) < 2:
        raise InputReadError(f"{context} coordinate must contain lng and lat.")
    lng = float(value[0])
    lat = float(value[1])
    _validate_lng_lat(lng, lat, context)
    return lng, lat


def _flatten_geojson_coordinates(value: Any) -> list[CoordPair]:
    """Flatten arbitrary GeoJSON coordinate arrays into lon/lat pairs."""
    if not isinstance(value, list):
        return []
    if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        return [_coord_pair(value, "GeoJSON coordinates")]
    pairs: list[CoordPair] = []
    for item in value:
        pairs.extend(_flatten_geojson_coordinates(item))
    return pairs


def _with_meta(point: PointRecord, point_id: str, provider: str | None, tag: str | None) -> PointRecord:
    """Return a sampled point with GeoJSON feature metadata."""
    return PointRecord(
        point_id=point_id,
        lng=point.lng,
        lat=point.lat,
        coord_sys=point.coord_sys,
        provider=provider,
        tag=tag,
    )


def _dedupe_points(points: Iterable[PointRecord]) -> list[PointRecord]:
    """Dedupe sampled points by coordinate and point id."""
    seen: set[tuple[str, float, float]] = set()
    deduped: list[PointRecord] = []
    for point in points:
        key = (point.point_id, point.lng, point.lat)
        if key not in seen:
            seen.add(key)
            deduped.append(point)
    return deduped


def _stable_id(*parts: Any) -> str:
    """Create a stable point id from deterministic parts."""
    raw = "|".join("" if part is None else str(part) for part in parts)
    return f"point_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"
