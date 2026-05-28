"""Resume service placeholder."""

from dataclasses import dataclass

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.download import Downloader
from cn_streetview_fetcher.services.plan_service import PlanService
from cn_streetview_fetcher.storage import MetadataStore


@dataclass(slots=True)
class ResumeResult:
    """Resume or retry-failed selection result."""

    message: str
    selected_tasks: int
    task_ids: list[str]
    success: int = 0
    failed: int = 0
    skipped: int = 0


class ResumeService:
    """Recover unfinished or failed tasks."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def pending_task_ids(self) -> list[str]:
        """Return task IDs that still need work."""
        plan = PlanService(self.config).create_plan()
        completed = MetadataStore(self.config.metadata_path).successful_task_ids()
        return [task.task_id for task in plan.tasks if task.task_id not in completed]

    def failed_task_ids(self) -> list[str]:
        """Return task IDs whose latest metadata status is failed."""
        return list(MetadataStore(self.config.metadata_path).failed_task_ids())

    def resume(self, run: bool = False) -> ResumeResult:
        """Select unfinished tasks for a later fetch run."""
        plan = PlanService(self.config).create_plan()
        pending = set(self.pending_task_ids())
        task_ids = [task.task_id for task in plan.tasks if task.task_id in pending]
        if run and not self.config.dry_run:
            result = Downloader(self.config).run([task for task in plan.tasks if task.task_id in pending], resume=False)
            return ResumeResult(
                message=result.message,
                selected_tasks=len(task_ids),
                task_ids=task_ids,
                success=result.success,
                failed=result.failed,
                skipped=result.skipped,
            )
        return ResumeResult(
            message=f"Selected {len(task_ids)} pending tasks for resume.",
            selected_tasks=len(task_ids),
            task_ids=task_ids,
        )

    def retry_failed(self, run: bool = False) -> ResumeResult:
        """Select failed tasks for a later retry run."""
        plan = PlanService(self.config).create_plan()
        failed = set(self.failed_task_ids())
        task_ids = [task.task_id for task in plan.tasks if task.task_id in failed]
        if run and not self.config.dry_run:
            result = Downloader(self.config).run([task for task in plan.tasks if task.task_id in failed], retry_failed=True, resume=False)
            return ResumeResult(
                message=result.message,
                selected_tasks=len(task_ids),
                task_ids=task_ids,
                success=result.success,
                failed=result.failed,
                skipped=result.skipped,
            )
        return ResumeResult(
            message=f"Selected {len(task_ids)} failed tasks for retry.",
            selected_tasks=len(task_ids),
            task_ids=task_ids,
        )
