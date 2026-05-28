"""Normalized input models."""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PointRecord:
    """A normalized input point."""

    point_id: str
    lng: float
    lat: float
    coord_sys: str
    provider: str | None = None
    panoid: str | None = None
    heading: float | None = None
    pitch: float | None = None
    fov: float | None = None
    tag: str | None = None


@dataclass(slots=True)
class InputStats:
    """Summary statistics for normalized input records."""

    total_points: int
    coord_sys_counts: dict[str, int]
    provider_counts: dict[str, int]
    tag_counts: dict[str, int]


@dataclass(slots=True)
class InputReadResult:
    """Input records plus warnings and statistics."""

    points: list[PointRecord]
    warnings: list[str]
    stats: InputStats


class InputReadError(ValueError):
    """Raised when input data cannot be normalized into PointRecord values."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.context = context or {}
        super().__init__(message)
