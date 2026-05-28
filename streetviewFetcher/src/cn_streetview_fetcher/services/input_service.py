"""Input service."""

from dataclasses import dataclass

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import InputReadResult, InputStats, PointRecord, read_input


@dataclass(slots=True)
class InputPreview:
    """Small input preview for UI and CLI display."""

    rows: list[PointRecord]
    total_points: int
    stats: InputStats
    warnings: list[str]


class InputService:
    """Read and normalize input records."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def load_points(self) -> list[PointRecord]:
        """Load normalized points from the configured input path."""
        return self.read().points

    def read(self) -> InputReadResult:
        """Read configured input and return records, warnings, and stats."""
        return read_input(
            path=self.config.input_path,
            coord_sys=self.config.coord_sys,
            input_type=self.config.input_type,
            spacing_meters=self.config.spacing_meters,
            bbox=self.config.bbox,
            polygon=self.config.polygon,
        )

    def preview(self, limit: int | None = None) -> InputPreview:
        """Return a limited input preview and basic warnings."""
        result = self.read()
        points = result.points
        row_limit = limit or self.config.ui.preview_rows
        warnings = list(result.warnings)
        if self.config.input_path is None:
            if self.config.input_type in {"table", "geojson"}:
                warnings.append("No input_path configured.")
        elif not self.config.input_path.exists():
            warnings.append(f"Input file does not exist yet: {self.config.input_path}")
        return InputPreview(rows=points[:row_limit], total_points=len(points), stats=result.stats, warnings=warnings)
