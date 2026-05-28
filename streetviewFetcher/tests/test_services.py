"""Core service layer tests."""

from pathlib import Path

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.services import InspectService, PlanService, ReportService, ResumeService
from cn_streetview_fetcher.storage import MetadataStore
from cn_streetview_fetcher.tasks import build_tasks


def test_plan_service_generates_mock_statistics() -> None:
    """PlanService can summarize generated tasks without provider requests."""
    config = AppConfig(provider="both", headings=[0, 90], pitches=[0])
    point = PointRecord(point_id="p1", lng=116.3, lat=39.9, coord_sys="wgs84")
    tasks = build_tasks([point], config)
    assert len(tasks) == 4
    assert {task.provider for task in tasks} == {"baidu", "tencent"}


def test_fetch_inspect_resume_and_reports(tmp_path: Path) -> None:
    """Core services share metadata state in a mock workflow."""
    metadata_path = tmp_path / "metadata.jsonl"
    input_path = tmp_path / "points.csv"
    input_path.write_text("id,lng,lat\np1,116.3,39.9\n", encoding="utf-8")
    config = AppConfig(input_path=input_path, metadata_path=metadata_path, output_dir=tmp_path)
    task_id = PlanService(config).create_plan().tasks[0].task_id

    store = MetadataStore(metadata_path)
    store.append({"task_id": "success-1", "provider": "baidu", "status": "success", "heading": 0})
    store.append({"task_id": task_id, "provider": "baidu", "status": "failed", "heading": 0})
    store.append({"task_id": "no-pano-1", "provider": "tencent", "status": "no_pano", "heading": 90})

    inspect = InspectService(config).inspect()
    assert inspect.total == 3
    assert inspect.success == 1
    assert inspect.failed == 1
    assert inspect.no_pano == 1

    retry = ResumeService(config).retry_failed()
    assert retry.task_ids == [task_id]

    summary_path = ReportService(config).write_summary(tmp_path / "summary.json")
    errors_path = ReportService(config).write_errors(tmp_path / "errors.csv")
    assert summary_path.exists()
    assert errors_path.exists()
