"""Fetch service placeholders."""

from dataclasses import dataclass

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.download import Downloader
from cn_streetview_fetcher.services.plan_service import PlanService


@dataclass(slots=True)
class FetchResult:
    """Fetch command result."""

    message: str
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    dry_run: bool = True


class FetchService:
    """Run fetch, resume, and retry-failed workflows."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def fetch(self) -> FetchResult:
        """Run fetch workflow."""
        plan = PlanService(self.config).create_plan()
        if self.config.dry_run:
            return FetchResult(
                message="Dry-run complete; no real API requests were made.",
                total=len(plan.tasks),
                skipped=len(plan.tasks),
                dry_run=True,
            )

        result = Downloader(self.config).run(plan.tasks, retry_failed=False, resume=self.config.resume)
        return FetchResult(
            message=result.message,
            total=result.total,
            success=result.success,
            failed=result.failed,
            skipped=result.skipped,
            dry_run=False,
        )

    def resume(self) -> FetchResult:
        """Run a placeholder resume workflow."""
        from cn_streetview_fetcher.services.resume_service import ResumeService

        result = ResumeService(self.config).resume(run=True)
        return FetchResult(
            message=result.message,
            total=result.selected_tasks,
            success=result.success,
            failed=result.failed,
            skipped=result.skipped,
            dry_run=self.config.dry_run,
        )

    def retry_failed(self) -> FetchResult:
        """Run a placeholder retry-failed workflow."""
        from cn_streetview_fetcher.services.resume_service import ResumeService

        result = ResumeService(self.config).retry_failed(run=True)
        return FetchResult(
            message=result.message,
            total=result.selected_tasks,
            success=result.success,
            failed=result.failed,
            skipped=result.skipped,
            dry_run=self.config.dry_run,
        )
