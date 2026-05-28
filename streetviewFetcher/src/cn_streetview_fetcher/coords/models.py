"""Coordinate primitives and audited transformations."""

from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, pi, radians, sin, sqrt

from cn_streetview_fetcher.config import AppConfig


class CoordTransformError(ValueError):
    """Raised when a coordinate transformation cannot be performed safely."""


class CoordSys(str, Enum):
    """Supported coordinate systems."""

    WGS84 = "wgs84"
    GCJ02 = "gcj02"
    BD09 = "bd09"


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A longitude/latitude coordinate with an explicit coordinate system."""

    lng: float
    lat: float
    coord_sys: CoordSys


@dataclass(frozen=True, slots=True)
class CoordinateTransform:
    """Source and provider request coordinates kept together for auditing."""

    source: Coordinate
    request: Coordinate
    provider: str


_AXIS = 6378245.0
_EE = 0.00669342162296594323
_X_PI = pi * 3000.0 / 180.0


def transform_coordinate(coordinate: Coordinate, target: CoordSys) -> Coordinate:
    """Transform a coordinate to the target coordinate system."""
    _validate_coordinate(coordinate)
    if coordinate.coord_sys == target:
        return coordinate

    if _outside_china(coordinate.lng, coordinate.lat):
        if CoordSys.WGS84 in {coordinate.coord_sys, target}:
            raise CoordTransformError(
                f"Refusing {coordinate.coord_sys.value}->{target.value} transform outside mainland China coverage."
            )

    if coordinate.coord_sys == CoordSys.WGS84 and target == CoordSys.GCJ02:
        return _wgs84_to_gcj02(coordinate)
    if coordinate.coord_sys == CoordSys.GCJ02 and target == CoordSys.WGS84:
        return _gcj02_to_wgs84(coordinate)
    if coordinate.coord_sys == CoordSys.GCJ02 and target == CoordSys.BD09:
        return _gcj02_to_bd09(coordinate)
    if coordinate.coord_sys == CoordSys.BD09 and target == CoordSys.GCJ02:
        return _bd09_to_gcj02(coordinate)
    if coordinate.coord_sys == CoordSys.WGS84 and target == CoordSys.BD09:
        return _gcj02_to_bd09(_wgs84_to_gcj02(coordinate))
    if coordinate.coord_sys == CoordSys.BD09 and target == CoordSys.WGS84:
        return _gcj02_to_wgs84(_bd09_to_gcj02(coordinate))

    raise CoordTransformError(f"Unsupported coordinate transform {coordinate.coord_sys.value}->{target.value}.")


def request_coord_sys_for_provider(provider: str, config: AppConfig) -> CoordSys:
    """Resolve the request coordinate system required by a provider."""
    if provider == "tencent":
        return CoordSys.GCJ02
    if provider == "baidu":
        if config.baidu.coordtype == "wgs84ll":
            return CoordSys.WGS84
        if config.baidu.coordtype == "bd09ll":
            return CoordSys.BD09
        raise CoordTransformError(f"Unsupported Baidu coordtype: {config.baidu.coordtype}")
    raise CoordTransformError(f"Unsupported provider for coordinate request: {provider}")


def transform_for_provider(coordinate: Coordinate, provider: str, config: AppConfig) -> CoordinateTransform:
    """Transform a source coordinate to the provider request coordinate system."""
    target = request_coord_sys_for_provider(provider, config)
    request = transform_coordinate(coordinate, target)
    return CoordinateTransform(source=coordinate, request=request, provider=provider)


def parse_coord_sys(value: str | CoordSys) -> CoordSys:
    """Parse a coordinate system value into CoordSys."""
    if isinstance(value, CoordSys):
        return value
    try:
        return CoordSys(value)
    except ValueError as exc:
        raise CoordTransformError(f"Unsupported coordinate system: {value}") from exc


def _validate_coordinate(coordinate: Coordinate) -> None:
    """Validate longitude and latitude ranges."""
    if coordinate.lng < -180 or coordinate.lng > 180:
        raise CoordTransformError(f"Invalid longitude: {coordinate.lng}. Expected -180..180.")
    if coordinate.lat < -90 or coordinate.lat > 90:
        raise CoordTransformError(f"Invalid latitude: {coordinate.lat}. Expected -90..90.")


def _outside_china(lng: float, lat: float) -> bool:
    """Return whether a coordinate is outside the usual mainland China transform area."""
    return lng < 72.004 or lng > 137.8347 or lat < 0.8293 or lat > 55.8271


def _wgs84_to_gcj02(coordinate: Coordinate) -> Coordinate:
    """Convert WGS84 to GCJ-02."""
    lng = coordinate.lng
    lat = coordinate.lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = radians(lat)
    magic = sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = sqrt(magic)
    dlat = (dlat * 180.0) / ((_AXIS * (1 - _EE)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (_AXIS / sqrtmagic * cos(radlat) * pi)
    return Coordinate(lng=lng + dlng, lat=lat + dlat, coord_sys=CoordSys.GCJ02)


def _gcj02_to_wgs84(coordinate: Coordinate) -> Coordinate:
    """Convert GCJ-02 to WGS84 using one-step inverse approximation."""
    gcj = coordinate
    wgs_probe = Coordinate(lng=gcj.lng, lat=gcj.lat, coord_sys=CoordSys.WGS84)
    converted = _wgs84_to_gcj02(wgs_probe)
    return Coordinate(
        lng=gcj.lng * 2 - converted.lng,
        lat=gcj.lat * 2 - converted.lat,
        coord_sys=CoordSys.WGS84,
    )


def _gcj02_to_bd09(coordinate: Coordinate) -> Coordinate:
    """Convert GCJ-02 to BD-09."""
    x = coordinate.lng
    y = coordinate.lat
    z = sqrt(x * x + y * y) + 0.00002 * sin(y * _X_PI)
    theta = atan2(y, x) + 0.000003 * cos(x * _X_PI)
    return Coordinate(lng=z * cos(theta) + 0.0065, lat=z * sin(theta) + 0.006, coord_sys=CoordSys.BD09)


def _bd09_to_gcj02(coordinate: Coordinate) -> Coordinate:
    """Convert BD-09 to GCJ-02."""
    x = coordinate.lng - 0.0065
    y = coordinate.lat - 0.006
    z = sqrt(x * x + y * y) - 0.00002 * sin(y * _X_PI)
    theta = atan2(y, x) - 0.000003 * cos(x * _X_PI)
    return Coordinate(lng=z * cos(theta), lat=z * sin(theta), coord_sys=CoordSys.GCJ02)


def _transform_lat(lng: float, lat: float) -> float:
    """Internal latitude offset transform."""
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * sqrt(abs(lng))
    ret += (20.0 * sin(6.0 * lng * pi) + 20.0 * sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * sin(lat * pi) + 40.0 * sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * sin(lat / 12.0 * pi) + 320 * sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    """Internal longitude offset transform."""
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * sqrt(abs(lng))
    ret += (20.0 * sin(6.0 * lng * pi) + 20.0 * sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * sin(lng * pi) + 40.0 * sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * sin(lng / 12.0 * pi) + 300.0 * sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret
