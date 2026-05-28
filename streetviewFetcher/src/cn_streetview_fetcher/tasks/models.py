"""Task models."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class StreetViewTask:
    """One planned street-view image fetch task."""

    task_id: str
    provider: str
    point_id: str
    source_lng: float
    source_lat: float
    source_coord_sys: str
    request_lng: float
    request_lat: float
    request_coord_sys: str
    heading: float
    pitch: float
    fov: float | None = None
    width: int | None = None
    height: int | None = None
    size: str | None = None
    radius: int | None = None
    panoid_input: str | None = None
    pano_id: str | None = None
    status: str = "planned"
    image_path: Path | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class PlanSummary:
    """Summary of a planned fetch job."""

    input_points: int = 0
    planned_tasks: int = 0
    deduped_tasks: int = 0
    provider_counts: dict[str, int] = field(default_factory=dict)
    heading_counts: dict[str, int] = field(default_factory=dict)
    pitch_counts: dict[str, int] = field(default_factory=dict)
    estimated_getpano_requests: int = 0
    estimated_image_requests: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Format the summary for CLI output."""
        warnings = self.warnings or []
        lines = [
            f"Input points: {self.input_points}",
            f"Planned tasks: {self.planned_tasks}",
            f"Deduped tasks: {self.deduped_tasks}",
            f"Estimated getpano requests: {self.estimated_getpano_requests}",
            f"Estimated image requests: {self.estimated_image_requests}",
        ]
        if self.provider_counts:
            lines.append(f"Provider counts: {self.provider_counts}")
        lines.extend(f"Warning: {warning}" for warning in warnings)
        return "\n".join(lines)


@dataclass(slots=True)
class TaskPlan:
    """A full task plan with tasks and summary statistics."""

    tasks: list[StreetViewTask]
    summary: PlanSummary
