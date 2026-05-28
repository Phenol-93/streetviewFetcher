"""Report service placeholder."""

import csv
import json
from pathlib import Path

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.services.inspect_service import InspectService
from cn_streetview_fetcher.storage import MetadataStore


class ReportService:
    """Generate summary and error reports."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def write_summary(self, output_path: Path) -> Path:
        """Write a JSON summary report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = InspectService(self.config).inspect()
        payload = {
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "no_pano": result.no_pano,
            "skipped": result.skipped,
            "provider_counts": result.provider_counts or {},
            "heading_counts": result.heading_counts or {},
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    def write_errors(self, output_path: Path) -> Path:
        """Write failed and no_pano metadata records as CSV."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            record
            for record in MetadataStore(self.config.metadata_path).read_all()
            if record.get("status") in {"failed", "no_pano"}
        ]
        fieldnames = ["task_id", "provider", "status", "error_type", "error_code", "error_message"]
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow({field: record.get(field, "") for field in fieldnames})
        return output_path
