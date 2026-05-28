"""Streamlit UI skeleton tests."""

from pathlib import Path
import ast

from cn_streetview_fetcher.ui.app import app_path
from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.storage import MetadataStore
from cn_streetview_fetcher.tasks import PlanSummary, StreetViewTask
from cn_streetview_fetcher.ui.state import (
    COMPLIANCE_NOTICE,
    error_records,
    fetch_progress_snapshot,
    filter_metadata_records,
    image_health,
    parse_bbox,
    parse_float_list,
    records_to_csv_bytes,
    write_plan_summary,
    write_points_jsonl,
    write_tasks_jsonl,
)


def test_ui_app_path_exists() -> None:
    """UI app path points to the Streamlit entry file."""
    assert app_path().exists()


def test_ui_pages_exist() -> None:
    """Expected multipage Streamlit page files exist."""
    pages_dir = Path("src/cn_streetview_fetcher/ui/pages")
    expected = {
        "1_Dashboard.py",
        "2_Input_Data.py",
        "3_Provider_Config.py",
        "4_Streetview_Params.py",
        "5_Task_Plan.py",
        "6_Fetch.py",
        "7_Results.py",
        "8_Maintenance.py",
    }
    assert expected.issubset({path.name for path in pages_dir.glob("*.py")})


def test_compliance_notice_mentions_official_api_scope() -> None:
    """UI compliance notice states the official API scope."""
    assert "官方 API" in COMPLIANCE_NOTICE
    assert "网页爬虫" in COMPLIANCE_NOTICE
    assert "配额" in COMPLIANCE_NOTICE


def test_ui_input_helpers(tmp_path: Path) -> None:
    """UI helper functions parse inputs and export normalized points."""
    assert parse_float_list("0, 90,180", "headings") == [0.0, 90.0, 180.0]
    assert parse_bbox("116,39,117,40") == (116.0, 39.0, 117.0, 40.0)
    output = write_points_jsonl(
        [PointRecord(point_id="p1", lng=116.3, lat=39.9, coord_sys="wgs84")],
        tmp_path / "normalized_points.jsonl",
    )
    assert output.read_text(encoding="utf-8").strip()


def test_ui_plan_export_helpers(tmp_path: Path) -> None:
    """Plan export helpers write tasks and summary files."""
    task = StreetViewTask(
        task_id="t1",
        provider="baidu",
        point_id="p1",
        source_lng=116.3,
        source_lat=39.9,
        source_coord_sys="wgs84",
        request_lng=116.3,
        request_lat=39.9,
        request_coord_sys="wgs84",
        heading=0,
        pitch=0,
    )
    tasks_path = write_tasks_jsonl([task], tmp_path / "tasks.jsonl")
    summary_path = write_plan_summary(PlanSummary(input_points=1, planned_tasks=1, deduped_tasks=1), tmp_path / "plan_summary.json")

    assert "t1" in tasks_path.read_text(encoding="utf-8")
    assert "deduped_tasks" in summary_path.read_text(encoding="utf-8")


def test_fetch_progress_snapshot_reads_metadata(tmp_path: Path) -> None:
    """Fetch progress snapshot is reconstructed from metadata."""
    input_path = tmp_path / "points.csv"
    input_path.write_text("id,lng,lat\np1,116.3,39.9\np2,116.301,39.9\n", encoding="utf-8")
    metadata_path = tmp_path / "metadata.jsonl"
    config = AppConfig(
        input_path=input_path,
        metadata_path=metadata_path,
        output_dir=tmp_path / "output",
        headings=[0],
        pitches=[0],
    )
    from cn_streetview_fetcher.tasks import build_tasks

    tasks = build_tasks(
        [
            PointRecord(point_id="p1", lng=116.3, lat=39.9, coord_sys="wgs84"),
            PointRecord(point_id="p2", lng=116.301, lat=39.9, coord_sys="wgs84"),
        ],
        config,
    )
    store = MetadataStore(metadata_path)
    store.append({"task_id": tasks[0].task_id, "status": "success", "completed_at": "2026-01-01T00:00:00+00:00"})
    store.append(
        {
            "task_id": tasks[1].task_id,
            "status": "failed",
            "provider": "baidu",
            "error_type": "server_error",
            "error_message": "server failed",
            "completed_at": "2026-01-01T00:00:02+00:00",
            "debug_info": {"request": {"params": {"ak": "should-not-be-used"}}},
        }
    )

    snapshot = fetch_progress_snapshot(config)

    assert snapshot["total"] == 2
    assert snapshot["completed"] == 2
    assert snapshot["success"] == 1
    assert snapshot["failed"] == 1
    assert snapshot["recent_errors"][0]["error_message"] == "server failed"
    assert "debug_info" not in snapshot["recent_errors"][0]


def test_result_browser_helpers(tmp_path: Path) -> None:
    """Result browser helpers filter records, export CSV, and inspect image health."""
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    empty = tmp_path / "empty.jpg"
    image_a.write_bytes(b"same")
    image_b.write_bytes(b"same")
    empty.write_bytes(b"")
    records = [
        {
            "task_id": "a",
            "provider": "baidu",
            "status": "success",
            "heading": 0,
            "pitch": 0,
            "tag": "x",
            "image_path": str(image_a),
            "image_md5": "same-md5",
        },
        {
            "task_id": "b",
            "provider": "baidu",
            "status": "success",
            "heading": 90,
            "pitch": 0,
            "tag": "y",
            "image_path": str(image_b),
            "image_md5": "same-md5",
        },
        {
            "task_id": "c",
            "provider": "tencent",
            "status": "failed",
            "heading": 0,
            "pitch": -10,
            "tag": "x",
            "error_message": "failed",
        },
        {"task_id": "d", "provider": "baidu", "status": "success", "image_path": str(empty), "image_md5": "empty-md5"},
        {"task_id": "e", "provider": "baidu", "status": "success", "image_path": str(tmp_path / "missing.jpg")},
    ]

    filtered = filter_metadata_records(records, providers=["tencent"], statuses=["failed"], headings=["0"], pitches=["-10"], tags=["x"])
    assert [record["task_id"] for record in filtered] == ["c"]
    assert error_records(records)[0]["task_id"] == "c"
    assert b"task_id" in records_to_csv_bytes(records)

    health = image_health(records)
    assert len(health["missing"]) == 1
    assert len(health["empty"]) == 1
    assert len(health["duplicates"]) == 1


def test_ui_pages_do_not_import_provider_layer() -> None:
    """UI pages use services/storage helpers instead of provider private logic."""
    ui_root = Path("src/cn_streetview_fetcher/ui")
    for path in ui_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("cn_streetview_fetcher.providers"), path
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("cn_streetview_fetcher.providers"), path
