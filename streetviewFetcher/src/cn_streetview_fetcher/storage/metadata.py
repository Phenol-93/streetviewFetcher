"""Metadata storage placeholders."""

import csv
import json
from pathlib import Path
from typing import Any


class MetadataStore:
    """Append-only metadata store placeholder."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: dict[str, Any]) -> None:
        """Append one metadata record."""
        if self.path.suffix.lower() == ".csv":
            self._append_csv(record)
            return
        self._append_jsonl(record)

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        """Append one metadata record as JSONL."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str))
            handle.write("\n")

    def _append_csv(self, record: dict[str, Any]) -> None:
        """Append one metadata record as CSV."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        fieldnames = sorted(record.keys())
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({key: record.get(key, "") for key in fieldnames})

    def read_all(self) -> list[dict[str, Any]]:
        """Read all metadata records."""
        if not self.path.exists():
            return []
        if self.path.suffix.lower() == ".csv":
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records

    def latest_by_task_id(self) -> dict[str, dict[str, Any]]:
        """Return the latest metadata record for each task id."""
        latest: dict[str, dict[str, Any]] = {}
        for record in self.read_all():
            task_id = record.get("task_id")
            if task_id:
                latest[str(task_id)] = record
        return latest

    def successful_task_ids(self) -> set[str]:
        """Return task ids whose latest status is success."""
        return {
            task_id
            for task_id, record in self.latest_by_task_id().items()
            if record.get("status") == "success"
        }

    def failed_task_ids(self) -> set[str]:
        """Return task ids whose latest status is failed."""
        return {
            task_id
            for task_id, record in self.latest_by_task_id().items()
            if record.get("status") == "failed"
        }
