"""Task planning placeholders."""

from collections import Counter
from collections.abc import Iterable
import hashlib

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.coords import Coordinate, parse_coord_sys, transform_for_provider
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.tasks.models import PlanSummary, StreetViewTask, TaskPlan

_SUPPORTED_TASK_PROVIDERS = {"baidu", "tencent", "both", "from_table"}


def _providers_for_point(point: PointRecord, config: AppConfig) -> list[str]:
    """Resolve providers for a point and global config."""
    provider = point.provider or config.provider
    if provider not in _SUPPORTED_TASK_PROVIDERS:
        raise ValueError(f"Unsupported provider for point {point.point_id}: {provider}")
    if provider == "both":
        return ["baidu", "tencent"]
    if provider == "from_table":
        return [point.provider or "baidu"]
    return [provider]


def _value_list(row_value: float | None, global_values: Iterable[float]) -> list[float]:
    """Use a row-level value when present, otherwise global values."""
    if row_value is not None:
        return [row_value]
    return list(global_values)


def _task_id(parts: list[object]) -> str:
    """Build a stable task id from deterministic task fields."""
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"task_{digest}"


def build_tasks(points: list[PointRecord], config: AppConfig) -> list[StreetViewTask]:
    """Build fetch tasks from normalized points and configuration."""
    return build_task_plan(points, config).tasks


def build_task_plan(points: list[PointRecord], config: AppConfig) -> TaskPlan:
    """Build fetch tasks and a plan summary without real API requests."""
    candidate_tasks = _build_task_candidates(points, config)
    tasks = _dedupe_tasks(candidate_tasks) if config.dedupe else candidate_tasks
    summary = summarize_tasks(
        input_points=len(points),
        candidate_tasks=candidate_tasks,
        tasks=tasks,
        warnings=config.warnings(),
    )
    return TaskPlan(tasks=tasks, summary=summary)


def summarize_tasks(
    input_points: int,
    candidate_tasks: list[StreetViewTask],
    tasks: list[StreetViewTask],
    warnings: list[str] | None = None,
) -> PlanSummary:
    """Create plan summary statistics for CLI and UI display."""
    provider_counts = Counter(task.provider for task in tasks)
    heading_counts = Counter(str(task.heading) for task in tasks)
    pitch_counts = Counter(str(task.pitch) for task in tasks)
    tencent_tasks = provider_counts.get("tencent", 0)
    return PlanSummary(
        input_points=input_points,
        planned_tasks=len(candidate_tasks),
        deduped_tasks=len(tasks),
        provider_counts=dict(provider_counts),
        heading_counts=dict(heading_counts),
        pitch_counts=dict(pitch_counts),
        estimated_getpano_requests=tencent_tasks,
        estimated_image_requests=len(tasks),
        warnings=warnings or [],
    )


def _build_task_candidates(points: list[PointRecord], config: AppConfig) -> list[StreetViewTask]:
    """Build all task candidates before optional dedupe."""
    tasks: list[StreetViewTask] = []

    for point in points:
        providers = _providers_for_point(point, config)
        headings = _value_list(point.heading, config.headings)
        pitches = _value_list(point.pitch, config.pitches)
        fov = point.fov if point.fov is not None else config.baidu.fov
        source_coordinate = Coordinate(point.lng, point.lat, parse_coord_sys(point.coord_sys))

        for provider in providers:
            coordinate_transform = transform_for_provider(source_coordinate, provider, config)
            for heading in headings:
                for pitch in pitches:
                    task_id = _task_id(
                        [
                            provider,
                            point.point_id,
                            point.lng,
                            point.lat,
                            point.coord_sys,
                            coordinate_transform.request.lng,
                            coordinate_transform.request.lat,
                            coordinate_transform.request.coord_sys.value,
                            heading,
                            pitch,
                            fov,
                        ]
                    )
                    tasks.append(
                        StreetViewTask(
                            task_id=task_id,
                            provider=provider,
                            point_id=point.point_id,
                            source_lng=point.lng,
                            source_lat=point.lat,
                            source_coord_sys=point.coord_sys,
                            request_lng=coordinate_transform.request.lng,
                            request_lat=coordinate_transform.request.lat,
                            request_coord_sys=coordinate_transform.request.coord_sys.value,
                            heading=heading,
                            pitch=pitch,
                            fov=fov,
                            width=config.baidu.width if provider == "baidu" else None,
                            height=config.baidu.height if provider == "baidu" else None,
                            size=config.tencent.size if provider == "tencent" else None,
                            radius=config.tencent.radius if provider == "tencent" else None,
                            panoid_input=point.panoid,
                        )
                    )
    return tasks


def _dedupe_tasks(tasks: list[StreetViewTask]) -> list[StreetViewTask]:
    """Dedupe tasks by stable task ID while preserving order."""
    seen: set[str] = set()
    deduped: list[StreetViewTask] = []
    for task in tasks:
        if task.task_id in seen:
            continue
        seen.add(task.task_id)
        deduped.append(task)
    return deduped
