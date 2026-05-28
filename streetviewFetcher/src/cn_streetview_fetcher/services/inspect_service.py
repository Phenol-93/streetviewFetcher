"""Metadata inspection service placeholder."""

from dataclasses import dataclass

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.storage import MetadataStore


@dataclass(slots=True)
class InspectResult:
    """Inspection summary."""

    total: int = 0
    success: int = 0
    failed: int = 0
    no_pano: int = 0
    skipped: int = 0
    provider_counts: dict[str, int] | None = None
    heading_counts: dict[str, int] | None = None

    def to_text(self) -> str:
        """Format inspection output for CLI."""
        return "\n".join(
            [
                f"Total: {self.total}",
                f"Success: {self.success}",
                f"Failed: {self.failed}",
                f"No pano: {self.no_pano}",
                f"Skipped: {self.skipped}",
                f"Provider counts: {self.provider_counts or {}}",
                f"Heading counts: {self.heading_counts or {}}",
            ]
        )


class InspectService:
    """Inspect metadata and task state."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def inspect(self) -> InspectResult:
        """Read metadata and return summary statistics."""
        records = MetadataStore(self.config.metadata_path).read_all()
        provider_counts: dict[str, int] = {}
        heading_counts: dict[str, int] = {}
        success = failed = no_pano = skipped = 0
        for record in records:
            status = str(record.get("status", ""))
            provider = record.get("provider")
            heading = record.get("heading")
            if status == "success":
                success += 1
            elif status == "failed":
                failed += 1
            elif status == "no_pano":
                no_pano += 1
            elif status == "skipped":
                skipped += 1
            if provider:
                provider_counts[str(provider)] = provider_counts.get(str(provider), 0) + 1
            if heading is not None:
                heading_key = str(heading)
                heading_counts[heading_key] = heading_counts.get(heading_key, 0) + 1
        return InspectResult(
            total=len(records),
            success=success,
            failed=failed,
            no_pano=no_pano,
            skipped=skipped,
            provider_counts=provider_counts,
            heading_counts=heading_counts,
        )
