"""Task model and task generation tests."""

from dataclasses import fields

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.tasks import StreetViewTask, build_task_plan, build_tasks


def test_task_model_contains_required_fields() -> None:
    """StreetViewTask exposes every required task field."""
    names = {field.name for field in fields(StreetViewTask)}
    assert {
        "task_id",
        "provider",
        "point_id",
        "source_lng",
        "source_lat",
        "source_coord_sys",
        "request_lng",
        "request_lat",
        "request_coord_sys",
        "heading",
        "pitch",
        "fov",
        "width",
        "height",
        "size",
        "radius",
        "panoid_input",
        "pano_id",
        "status",
        "image_path",
        "error_type",
        "error_code",
        "error_message",
    }.issubset(names)


def test_heading_pitch_cartesian_product_and_both_provider() -> None:
    """Task generation expands provider, heading, and pitch combinations."""
    points = [PointRecord(point_id="p1", lng=116.3, lat=39.9, coord_sys="wgs84")]
    config = AppConfig(provider="both", headings=[0, 90], pitches=[-10, 0])

    tasks = build_tasks(points, config)

    assert len(tasks) == 8
    assert {task.provider for task in tasks} == {"baidu", "tencent"}
    assert {task.heading for task in tasks} == {0, 90}
    assert {task.pitch for task in tasks} == {-10, 0}


def test_row_level_overrides_global_provider_heading_pitch_fov() -> None:
    """Row-level provider, heading, pitch, and fov override global config."""
    points = [
        PointRecord(
            point_id="p1",
            lng=116.3,
            lat=39.9,
            coord_sys="wgs84",
            provider="tencent",
            heading=180,
            pitch=5,
            fov=80,
        )
    ]
    config = AppConfig(provider="baidu", headings=[0, 90], pitches=[0], baidu={"fov": 100})

    tasks = build_tasks(points, config)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.provider == "tencent"
    assert task.heading == 180
    assert task.pitch == 5
    assert task.fov == 80
    assert task.size == config.tencent.size
    assert task.width is None


def test_task_id_is_stable_for_same_input() -> None:
    """Identical input generates identical task IDs."""
    points = [PointRecord(point_id="p1", lng=116.3, lat=39.9, coord_sys="wgs84")]
    config = AppConfig(provider="baidu", headings=[0], pitches=[0])

    first = build_tasks(points, config)
    second = build_tasks(points, config)

    assert [task.task_id for task in first] == [task.task_id for task in second]


def test_task_dedupe_and_plan_summary_counts() -> None:
    """Plan summary reports candidate and deduped task counts."""
    point = PointRecord(point_id="same", lng=116.3, lat=39.9, coord_sys="wgs84")
    config = AppConfig(provider="baidu", headings=[0], pitches=[0], dedupe=True)

    plan = build_task_plan([point, point], config)

    assert plan.summary.input_points == 2
    assert plan.summary.planned_tasks == 2
    assert plan.summary.deduped_tasks == 1
    assert len(plan.tasks) == 1
    assert plan.summary.estimated_image_requests == 1


def test_provider_dedupe_keeps_one_task_per_unique_provider() -> None:
    """Duplicate provider-expanded tasks are deduped by stable task id."""
    point = PointRecord(point_id="same", lng=116.3, lat=39.9, coord_sys="wgs84", provider="both")
    config = AppConfig(provider="from_table", headings=[0], pitches=[0], dedupe=True)

    plan = build_task_plan([point, point], config)

    assert plan.summary.planned_tasks == 4
    assert plan.summary.deduped_tasks == 2
    assert {task.provider for task in plan.tasks} == {"baidu", "tencent"}
