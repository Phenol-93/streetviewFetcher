"""Downloader, storage, resume, and retry-failed tests."""

from pathlib import Path
from typing import Any

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.download import Downloader
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.providers import BaiduProvider, MockHttpClient, ProviderResult, ProviderStatus
from cn_streetview_fetcher.services import ResumeService
from cn_streetview_fetcher.storage import MetadataStore
from cn_streetview_fetcher.tasks import build_tasks


class FakeSuccessProvider:
    """Provider that always returns image bytes."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def fetch_image(self, task: Any) -> ProviderResult:
        """Return a successful image result."""
        self.calls.append(task.task_id)
        return ProviderResult(
            status=ProviderStatus.SUCCESS,
            provider=task.provider,
            image_bytes=f"image-{task.task_id}".encode("utf-8"),
            metadata={"request": {"params": {"ak": "***"}}},
            message="ok",
        )


class FakeFailedProvider:
    """Provider that always fails."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def fetch_image(self, task: Any) -> ProviderResult:
        """Return a failed provider result."""
        self.calls.append(task.task_id)
        return ProviderResult(
            status=ProviderStatus.SERVER_ERROR,
            provider=task.provider,
            message="server failed",
        )


def _config(tmp_path: Path) -> AppConfig:
    """Create a non-dry-run config for downloader tests."""
    input_path = tmp_path / "points.csv"
    input_path.write_text("id,lng,lat\np0,116.3,39.9\np1,116.301,39.9\n", encoding="utf-8")
    return AppConfig(
        provider="baidu",
        dry_run=False,
        resume=True,
        input_path=input_path,
        output_dir=tmp_path / "output",
        metadata_path=tmp_path / "metadata.jsonl",
        concurrency=2,
        rate_limit=1000,
    )


def _tasks(config: AppConfig, count: int = 2) -> list[Any]:
    """Build deterministic test tasks."""
    points = [
        PointRecord(point_id=f"p{index}", lng=116.3 + index * 0.001, lat=39.9, coord_sys="wgs84")
        for index in range(count)
    ]
    return build_tasks(points, config)


def test_downloader_saves_images_and_metadata(tmp_path: Path) -> None:
    """Downloader stores images with MD5, size, and JSONL metadata."""
    config = _config(tmp_path)
    calls: list[str] = []
    downloader = Downloader(config, provider_factory=lambda _provider: FakeSuccessProvider(calls))
    tasks = _tasks(config, count=2)

    result = downloader.run(tasks)

    assert result.success == 2
    assert len(calls) == 2
    records = MetadataStore(config.metadata_path).read_all()
    assert len(records) == 2
    for record in records:
        assert record["status"] == "success"
        assert Path(record["image_path"]).exists()
        assert Path(record["image_path"]).name.startswith("116.")
        assert "_39.9_wgs84_h0_p0_" in Path(record["image_path"]).name
        assert record["image_md5"]
        assert record["image_size_bytes"] > 0
        assert record["provider_metadata"]["request"]["params"]["ak"] == "***"


def test_resume_skips_successful_tasks_with_existing_images(tmp_path: Path) -> None:
    """A second resume run skips already successful tasks."""
    config = _config(tmp_path)
    calls: list[str] = []
    tasks = _tasks(config, count=2)
    downloader = Downloader(config, provider_factory=lambda _provider: FakeSuccessProvider(calls))

    first = downloader.run(tasks)
    second = Downloader(config, provider_factory=lambda _provider: FakeSuccessProvider(calls)).run(tasks, resume=True)

    assert first.success == 2
    assert second.success == 0
    assert second.skipped == 2
    assert len(calls) == 2
    assert ResumeService(config).pending_task_ids() == []


def test_retry_failed_selects_only_failed_tasks(tmp_path: Path) -> None:
    """retry-failed retries failed tasks and leaves successful tasks alone."""
    config = _config(tmp_path)
    tasks = _tasks(config, count=2)
    success_calls: list[str] = []
    failed_calls: list[str] = []

    success_provider = FakeSuccessProvider(success_calls)
    failed_provider = FakeFailedProvider(failed_calls)

    # First task succeeds, second fails.
    class MixedProvider:
        def fetch_image(self, task: Any) -> ProviderResult:
            if task.task_id == tasks[0].task_id:
                return success_provider.fetch_image(task)
            return failed_provider.fetch_image(task)

    first = Downloader(config, provider_factory=lambda _provider: MixedProvider()).run(tasks)
    assert first.success == 1
    assert first.failed == 1
    assert ResumeService(config).failed_task_ids() == [tasks[1].task_id]

    retry_calls: list[str] = []
    retry = Downloader(config, provider_factory=lambda _provider: FakeSuccessProvider(retry_calls)).run(
        tasks,
        retry_failed=True,
        resume=False,
    )

    assert retry.success == 1
    assert retry_calls == [tasks[1].task_id]
    assert ResumeService(config).failed_task_ids() == []


def test_csv_metadata_append_and_read(tmp_path: Path) -> None:
    """MetadataStore also supports CSV metadata."""
    path = tmp_path / "metadata.csv"
    store = MetadataStore(path)
    store.append({"task_id": "t1", "status": "success"})
    store.append({"task_id": "t2", "status": "failed"})

    records = store.read_all()

    assert records[0]["task_id"] == "t1"
    assert store.successful_task_ids() == {"t1"}
    assert store.failed_task_ids() == {"t2"}


def test_provider_metadata_is_redacted_when_persisted(tmp_path: Path, monkeypatch) -> None:
    """Downloader persists provider metadata without raw API credentials."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    monkeypatch.setenv("BAIDU_MAP_SN", "baidu-sn")
    config = _config(tmp_path)
    tasks = _tasks(config, count=1)

    result = Downloader(
        config,
        provider_factory=lambda _provider: BaiduProvider(config.baidu, http_client=MockHttpClient()),
    ).run(tasks)

    assert result.success == 1
    metadata_text = config.metadata_path.read_text(encoding="utf-8")
    assert "baidu-secret" not in metadata_text
    assert "baidu-sn" not in metadata_text
    assert '"ak": "***"' in metadata_text
