"""Coordinate transformation tests."""

import pytest

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.coords import (
    Coordinate,
    CoordSys,
    CoordTransformError,
    request_coord_sys_for_provider,
    transform_coordinate,
    transform_for_provider,
)
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.tasks import build_tasks


def assert_close(actual: float, expected: float, tolerance: float = 1e-5) -> None:
    """Assert two floats are close enough for coordinate tests."""
    assert abs(actual - expected) <= tolerance


def test_identity_transform_keeps_coordinate() -> None:
    """Identity transforms do not modify coordinates."""
    coordinate = Coordinate(116.397389, 39.908722, CoordSys.WGS84)
    transformed = transform_coordinate(coordinate, CoordSys.WGS84)
    assert transformed == coordinate


def test_wgs84_gcj02_roundtrip_path() -> None:
    """WGS84 -> GCJ-02 -> WGS84 is available and approximately reversible."""
    source = Coordinate(116.397389, 39.908722, CoordSys.WGS84)
    gcj02 = transform_coordinate(source, CoordSys.GCJ02)
    restored = transform_coordinate(gcj02, CoordSys.WGS84)

    assert gcj02.coord_sys == CoordSys.GCJ02
    assert_close(restored.lng, source.lng, tolerance=2e-5)
    assert_close(restored.lat, source.lat, tolerance=2e-5)


def test_gcj02_bd09_roundtrip_path() -> None:
    """GCJ-02 -> BD-09 -> GCJ-02 is available and approximately reversible."""
    source = Coordinate(116.403633, 39.910943, CoordSys.GCJ02)
    bd09 = transform_coordinate(source, CoordSys.BD09)
    restored = transform_coordinate(bd09, CoordSys.GCJ02)

    assert bd09.coord_sys == CoordSys.BD09
    assert_close(restored.lng, source.lng, tolerance=1e-5)
    assert_close(restored.lat, source.lat, tolerance=1e-5)


def test_wgs84_bd09_roundtrip_path() -> None:
    """WGS84 -> BD-09 and BD-09 -> WGS84 are available."""
    source = Coordinate(116.397389, 39.908722, CoordSys.WGS84)
    bd09 = transform_coordinate(source, CoordSys.BD09)
    restored = transform_coordinate(bd09, CoordSys.WGS84)

    assert bd09.coord_sys == CoordSys.BD09
    assert_close(restored.lng, source.lng, tolerance=3e-5)
    assert_close(restored.lat, source.lat, tolerance=3e-5)


def test_outside_china_transform_refuses_unsafe_offset() -> None:
    """Transforms involving WGS84 outside China raise an explicit error."""
    source = Coordinate(-122.4194, 37.7749, CoordSys.WGS84)
    with pytest.raises(CoordTransformError, match="outside mainland China"):
        transform_coordinate(source, CoordSys.GCJ02)


def test_provider_request_coord_system_selection() -> None:
    """Provider request coordinate systems follow provider API expectations."""
    tencent_config = AppConfig(provider="tencent")
    baidu_wgs_config = AppConfig(provider="baidu", baidu={"coordtype": "wgs84ll"})
    baidu_bd_config = AppConfig(provider="baidu", baidu={"coordtype": "bd09ll"})

    assert request_coord_sys_for_provider("tencent", tencent_config) == CoordSys.GCJ02
    assert request_coord_sys_for_provider("baidu", baidu_wgs_config) == CoordSys.WGS84
    assert request_coord_sys_for_provider("baidu", baidu_bd_config) == CoordSys.BD09


def test_transform_for_provider_preserves_source_and_request() -> None:
    """Provider transforms keep source and request coordinates together."""
    config = AppConfig(provider="tencent")
    source = Coordinate(116.397389, 39.908722, CoordSys.WGS84)
    result = transform_for_provider(source, "tencent", config)

    assert result.source == source
    assert result.request.coord_sys == CoordSys.GCJ02
    assert result.request != source


def test_task_builder_stores_source_and_request_coordinates() -> None:
    """Task generation stores original and provider request coordinates."""
    point = PointRecord(point_id="p1", lng=116.397389, lat=39.908722, coord_sys="wgs84")
    config = AppConfig(provider="both", baidu={"coordtype": "bd09ll"})

    tasks = build_tasks([point], config)
    by_provider = {task.provider: task for task in tasks}

    assert by_provider["tencent"].source_coord_sys == "wgs84"
    assert by_provider["tencent"].request_coord_sys == "gcj02"
    assert by_provider["baidu"].source_coord_sys == "wgs84"
    assert by_provider["baidu"].request_coord_sys == "bd09"
