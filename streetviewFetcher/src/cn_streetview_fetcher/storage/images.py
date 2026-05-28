"""Image storage helpers."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from cn_streetview_fetcher.tasks import StreetViewTask

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _format_float(value: float) -> str:
    """Format numeric path parts without filesystem-unfriendly characters."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _safe_path_part(value: object) -> str:
    """Return a compact filesystem-safe path component."""
    cleaned = _SAFE_FILENAME_RE.sub("_", str(value)).strip("._")
    return cleaned or "unknown"


@dataclass(frozen=True, slots=True)
class StoredImage:
    """Stored image file metadata."""

    path: Path
    md5: str
    size_bytes: int


class ImageStore:
    """Save provider image bytes to deterministic file paths."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def path_for_task(self, task: StreetViewTask) -> Path:
        """Return the stable image path for a task."""
        filename = "_".join(
            [
                _format_float(task.source_lng),
                _format_float(task.source_lat),
                _safe_path_part(task.source_coord_sys),
                f"h{_format_float(task.heading)}",
                f"p{_format_float(task.pitch)}",
                task.task_id[-8:],
            ]
        )
        return self.output_dir / "images" / task.provider / f"{filename}.jpg"

    def save(self, task: StreetViewTask, image_bytes: bytes) -> StoredImage:
        """Save image bytes and return file metadata."""
        path = self.path_for_task(task)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        return self.inspect(path)

    def inspect(self, path: Path) -> StoredImage:
        """Return MD5 and size for an existing image file."""
        data = path.read_bytes()
        return StoredImage(path=path, md5=hashlib.md5(data).hexdigest(), size_bytes=len(data))
