"""Download scheduling, image storage, and task state persistence."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.providers import BaiduProvider, ProviderResult, ProviderStatus, TencentProvider
from cn_streetview_fetcher.storage import ImageStore, MetadataStore
from cn_streetview_fetcher.tasks import StreetViewTask

ProviderFactory = Callable[[str], Any]


@dataclass(slots=True)
class DownloadResult:
    """Result of a download run."""

    total: int
    success: int
    failed: int
    skipped: int
    no_pano: int
    message: str


class RateLimiter:
    """Simple process-local rate limiter."""

    def __init__(self, requests_per_second: float) -> None:
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        """Block until the next request slot is available."""
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._next_at = now + self.min_interval


class Downloader:
    """Coordinates task execution across providers."""

    def __init__(self, config: AppConfig, provider_factory: ProviderFactory | None = None) -> None:
        self.config = config
        self.metadata_store = MetadataStore(config.metadata_path)
        self.image_store = ImageStore(config.output_dir)
        self.rate_limiter = RateLimiter(config.rate_limit)
        self.provider_factory = provider_factory or self._default_provider_factory
        self._metadata_lock = threading.Lock()

    def run(self, tasks: list[StreetViewTask], retry_failed: bool = False, resume: bool = True) -> DownloadResult:
        """Run download tasks with concurrency and per-task metadata flushing."""
        selected_tasks = self._select_tasks(tasks, retry_failed=retry_failed, resume=resume)
        counters = {"success": 0, "failed": 0, "skipped": len(tasks) - len(selected_tasks), "no_pano": 0}

        if not selected_tasks:
            return DownloadResult(
                total=len(tasks),
                success=0,
                failed=0,
                skipped=counters["skipped"],
                no_pano=0,
                message="No tasks selected for download.",
            )

        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = [executor.submit(self._run_one, task) for task in selected_tasks]
            for future in as_completed(futures):
                record = future.result()
                status = record.get("status")
                if status == "success":
                    counters["success"] += 1
                elif status == "no_pano":
                    counters["no_pano"] += 1
                elif status == "skipped":
                    counters["skipped"] += 1
                else:
                    counters["failed"] += 1

        return DownloadResult(
            total=len(tasks),
            success=counters["success"],
            failed=counters["failed"],
            skipped=counters["skipped"],
            no_pano=counters["no_pano"],
            message="Download run complete.",
        )

    def _select_tasks(self, tasks: list[StreetViewTask], retry_failed: bool, resume: bool) -> list[StreetViewTask]:
        """Select tasks based on resume and retry-failed rules."""
        latest = self.metadata_store.latest_by_task_id()
        selected: list[StreetViewTask] = []
        failed_ids = {task_id for task_id, record in latest.items() if record.get("status") == "failed"}
        for task in tasks:
            latest_record = latest.get(task.task_id)
            if retry_failed:
                if task.task_id in failed_ids:
                    selected.append(task)
                continue
            if resume and latest_record and latest_record.get("status") == "success":
                image_path = latest_record.get("image_path")
                if image_path and self._path_exists(str(image_path)):
                    continue
                if not image_path:
                    continue
            selected.append(task)
        return selected

    def _run_one(self, task: StreetViewTask) -> dict[str, Any]:
        """Run one task and append metadata immediately."""
        latest = self.metadata_store.latest_by_task_id().get(task.task_id)
        if latest and latest.get("status") == "success":
            image_path = latest.get("image_path")
            if image_path and self._path_exists(str(image_path)):
                return self._append_record(task, {"status": "skipped", "message": "Existing successful image skipped."})

        self.rate_limiter.wait()
        provider = self.provider_factory(task.provider)
        result: ProviderResult = provider.fetch_image(task)
        record = self._record_from_result(task, result)
        return self._append_record(task, record)

    def _record_from_result(self, task: StreetViewTask, result: ProviderResult) -> dict[str, Any]:
        """Build a metadata record from provider result and saved image."""
        record: dict[str, Any] = {
            **asdict(task),
            "status": result.status.value,
            "message": result.message,
            "provider_metadata": result.metadata,
            "debug_info": result.debug_info,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if result.status == ProviderStatus.SUCCESS and result.image_bytes:
            stored = self.image_store.save(task, result.image_bytes)
            record.update(
                {
                    "image_path": str(stored.path),
                    "image_md5": stored.md5,
                    "image_size_bytes": stored.size_bytes,
                }
            )
        elif result.status == ProviderStatus.NO_PANO:
            record["status"] = "no_pano"
        elif result.status != ProviderStatus.SUCCESS:
            record["status"] = "failed"
            record["error_type"] = result.status.value
            record["error_message"] = result.message
        return record

    def _append_record(self, task: StreetViewTask, record: dict[str, Any]) -> dict[str, Any]:
        """Append metadata with a lock so JSONL remains line-consistent."""
        record.setdefault("task_id", task.task_id)
        with self._metadata_lock:
            self.metadata_store.append(record)
        return record

    def _default_provider_factory(self, provider: str) -> Any:
        """Create a provider for the requested provider name."""
        if provider == "baidu":
            return BaiduProvider(self.config.baidu)
        if provider == "tencent":
            return TencentProvider(self.config.tencent)
        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def _path_exists(path: str) -> bool:
        """Return whether a stored image path exists."""
        from pathlib import Path

        return Path(path).exists()
