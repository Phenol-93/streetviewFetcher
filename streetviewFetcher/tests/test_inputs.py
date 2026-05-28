"""Input reader tests."""

import json
from pathlib import Path

import pandas as pd
import pytest

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import InputReadError, read_input, read_points
from cn_streetview_fetcher.services import InputService


def test_csv_reader_generates_stable_id_and_defaults_coord_sys(tmp_path: Path) -> None:
    """CSV input is normalized into PointRecord values."""
    path = tmp_path / "points.csv"
    path.write_text("lng,lat,provider,tag\n116.3,39.9,tencent,test\n", encoding="utf-8")

    first = read_points(path, "wgs84")
    second = read_points(path, "wgs84")

    assert len(first) == 1
    assert first[0].point_id == second[0].point_id
    assert first[0].coord_sys == "wgs84"
    assert first[0].provider == "tencent"


def test_excel_reader_supports_required_fields(tmp_path: Path) -> None:
    """Excel input is supported through pandas."""
    path = tmp_path / "points.xlsx"
    pd.DataFrame([{"id": "p1", "lng": 116.3, "lat": 39.9, "heading": 90}]).to_excel(path, index=False)

    points = read_points(path, "gcj02")

    assert points[0].point_id == "p1"
    assert points[0].coord_sys == "gcj02"
    assert points[0].heading == 90


def test_invalid_coordinate_has_clear_error(tmp_path: Path) -> None:
    """Invalid coordinate values raise a readable input error."""
    path = tmp_path / "bad.csv"
    path.write_text("id,lng,lat\nbad,181,39.9\n", encoding="utf-8")

    with pytest.raises(InputReadError, match="Invalid longitude"):
        read_points(path, "wgs84")


def test_bbox_sampling_returns_points() -> None:
    """bbox sampling supports meter spacing."""
    result = read_input(None, "wgs84", input_type="bbox", bbox=(116.0, 39.0, 116.001, 39.001), spacing_meters=80)

    assert result.points
    assert result.stats.total_points == len(result.points)


def test_polygon_sampling_keeps_points_inside() -> None:
    """polygon sampling filters sampled points to the polygon interior."""
    polygon = [(116.0, 39.0), (116.002, 39.0), (116.002, 39.002), (116.0, 39.002)]
    result = read_input(None, "wgs84", input_type="polygon", polygon=polygon, spacing_meters=80)

    assert result.points
    assert all(116.0 <= point.lng <= 116.002 and 39.0 <= point.lat <= 39.002 for point in result.points)


def test_geojson_point_line_polygon(tmp_path: Path) -> None:
    """GeoJSON point, line, and polygon geometries are supported."""
    path = tmp_path / "input.geojson"
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": "pt"}, "geometry": {"type": "Point", "coordinates": [116.0, 39.0]}},
            {
                "type": "Feature",
                "properties": {"id": "line"},
                "geometry": {"type": "LineString", "coordinates": [[116.0, 39.0], [116.001, 39.0]]},
            },
            {
                "type": "Feature",
                "properties": {"id": "poly"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[116.0, 39.0], [116.001, 39.0], [116.001, 39.001], [116.0, 39.001], [116.0, 39.0]]],
                },
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_input(path, "wgs84", input_type="geojson", spacing_meters=80)

    assert len(result.points) >= 3


def test_geojson_point_reading(tmp_path: Path) -> None:
    """GeoJSON Point input is read into a single PointRecord."""
    path = tmp_path / "point.geojson"
    payload = {
        "type": "Feature",
        "properties": {"id": "geo-point", "tag": "poi"},
        "geometry": {"type": "Point", "coordinates": [116.0, 39.0]},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_input(path, "wgs84", input_type="geojson")

    assert len(result.points) == 1
    assert result.points[0].lng == 116.0
    assert result.points[0].lat == 39.0
    assert result.points[0].tag == "poi"


def test_input_service_preview_limits_rows(tmp_path: Path) -> None:
    """InputService preview returns only the requested rows plus stats."""
    path = tmp_path / "points.csv"
    path.write_text("id,lng,lat\np1,116.3,39.9\np2,116.4,39.8\n", encoding="utf-8")
    config = AppConfig(input_path=path, ui={"preview_rows": 1})

    preview = InputService(config).preview()

    assert len(preview.rows) == 1
    assert preview.total_points == 2
    assert preview.stats.total_points == 2
