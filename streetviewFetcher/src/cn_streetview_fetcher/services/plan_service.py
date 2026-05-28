"""Planning service."""

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.services.input_service import InputService
from cn_streetview_fetcher.tasks import PlanSummary, TaskPlan, build_task_plan


class PlanService:
    """Generate task plans from config and inputs."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def create_plan(self) -> TaskPlan:
        """Create a task plan without real API requests."""
        points = InputService(self.config).load_points()
        return build_task_plan(points, self.config)

    def plan(self) -> PlanSummary:
        """Return task plan summary for CLI compatibility."""
        return self.create_plan().summary
