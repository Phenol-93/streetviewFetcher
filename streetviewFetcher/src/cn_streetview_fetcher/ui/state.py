"""Shared Streamlit UI state and service helpers."""

from dataclasses import asdict, is_dataclass
from datetime import datetime
import csv
from io import StringIO
import json
from pathlib import Path
from typing import Any

from cn_streetview_fetcher.config import AppConfig, create_default_config
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.tasks import PlanSummary, StreetViewTask
from cn_streetview_fetcher.services import ConfigService, PlanService
from cn_streetview_fetcher.storage import MetadataStore


COMPLIANCE_NOTICE = (
    "本工具只封装百度和腾讯官方 API，不支持网页爬虫、逆向接口、私有接口、"
    "绕过配额或绕过鉴权。请在官方控制台确认 API 权限、配额、计费和授权范围。"
)


def setup_page(title: str) -> Any:
    """Configure a Streamlit page and render the shared sidebar."""
    import streamlit as st

    st.set_page_config(page_title=f"{title} - cn-streetview-fetcher", layout="wide")
    st.sidebar.title("cnsv")
    project_dir_text = st.sidebar.text_input("项目目录", value=str(current_project_dir()))
    project_dir = Path(project_dir_text).expanduser()
    if st.sidebar.button("使用此项目目录"):
        st.session_state["project_dir"] = str(project_dir)
        st.rerun()
    st.sidebar.caption(f"配置文件：{config_path()}")
    st.sidebar.warning(COMPLIANCE_NOTICE)
    st.title(title)
    return st


def current_project_dir() -> Path:
    """Return the selected project directory."""
    import streamlit as st

    return Path(st.session_state.get("project_dir", ".")).expanduser()


def config_path() -> Path:
    """Return the selected config path."""
    return current_project_dir() / "config.yaml"


def config_service() -> ConfigService:
    """Return a ConfigService for the selected project."""
    return ConfigService(config_path())


def load_config() -> AppConfig:
    """Load config or return defaults when config.yaml does not exist."""
    path = config_path()
    if path.exists():
        return ConfigService(path).load()
    return create_default_config()


def save_config(config: AppConfig) -> None:
    """Save config to the selected project config.yaml."""
    ConfigService(config_path()).save(config)


def save_uploaded_file(uploaded_file: Any, subdir: str = "inputs") -> Path:
    """Save a Streamlit uploaded file inside the project directory."""
    target_dir = current_project_dir() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / uploaded_file.name
    target_path.write_bytes(uploaded_file.getbuffer())
    return target_path


def parse_float_list(text: str, field_name: str) -> list[float]:
    """Parse a comma-separated float list."""
    values: list[float] = []
    for part in text.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            values.append(float(cleaned))
        except ValueError as exc:
            raise ValueError(f"{field_name} 包含非数字值：{cleaned}") from exc
    if not values:
        raise ValueError(f"{field_name} 不能为空。")
    return values


def parse_bbox(text: str) -> tuple[float, float, float, float] | None:
    """Parse bbox text in min_lng,min_lat,max_lng,max_lat format."""
    if not text.strip():
        return None
    values = parse_float_list(text, "bbox")
    if len(values) != 4:
        raise ValueError("bbox 必须正好包含 4 个数字：min_lng,min_lat,max_lng,max_lat。")
    return values[0], values[1], values[2], values[3]


def write_points_jsonl(points: list[PointRecord], path: Path) -> Path:
    """Write normalized points as JSONL in the project directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for point in points:
            handle.write(json.dumps(dataclass_to_dict(point), ensure_ascii=False))
            handle.write("\n")
    return path


def write_tasks_jsonl(tasks: list[StreetViewTask], path: Path) -> Path:
    """Write planned tasks as JSONL in the project directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(dataclass_to_dict(task), ensure_ascii=False, default=str))
            handle.write("\n")
    return path


def write_plan_summary(summary: PlanSummary, path: Path) -> Path:
    """Write plan summary as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataclass_to_dict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fetch_progress_snapshot(config: AppConfig, recent_errors_limit: int = 10) -> dict[str, Any]:
    """Build a UI progress snapshot from task plan and metadata."""
    plan = PlanService(config).create_plan()
    latest = MetadataStore(config.metadata_path).latest_by_task_id()
    total = len(plan.tasks)
    success = failed = no_pano = skipped = 0
    completed_records: list[dict[str, Any]] = []
    recent_errors: list[dict[str, Any]] = []
    for task in plan.tasks:
        record = latest.get(task.task_id)
        if not record:
            continue
        status = str(record.get("status", ""))
        if status == "success":
            success += 1
        elif status == "failed":
            failed += 1
            recent_errors.append(_public_error_record(record))
        elif status == "no_pano":
            no_pano += 1
        elif status == "skipped":
            skipped += 1
        if status in {"success", "failed", "no_pano", "skipped"}:
            completed_records.append(record)
    completed = success + failed + no_pano + skipped
    return {
        "total": total,
        "completed": completed,
        "progress": completed / total if total else 0.0,
        "success": success,
        "failed": failed,
        "no_pano": no_pano,
        "skipped": skipped,
        "speed_per_second": _records_per_second(completed_records),
        "recent_errors": recent_errors[-recent_errors_limit:],
        "metadata_path": str(config.metadata_path),
    }


def filter_metadata_records(
    records: list[dict[str, Any]],
    providers: list[str] | None = None,
    statuses: list[str] | None = None,
    headings: list[str] | None = None,
    pitches: list[str] | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter metadata records for UI browsing."""
    filtered = records
    if providers:
        filtered = [record for record in filtered if str(record.get("provider")) in providers]
    if statuses:
        filtered = [record for record in filtered if str(record.get("status")) in statuses]
    if headings:
        filtered = [record for record in filtered if str(record.get("heading")) in headings]
    if pitches:
        filtered = [record for record in filtered if str(record.get("pitch")) in pitches]
    if tags:
        filtered = [record for record in filtered if str(record.get("tag")) in tags]
    return filtered


def records_to_csv_bytes(records: list[dict[str, Any]]) -> bytes:
    """Serialize metadata records to CSV bytes."""
    output = StringIO()
    fieldnames = sorted({key for record in records for key in record.keys()})
    if not fieldnames:
        fieldnames = ["task_id", "status"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow({key: _csv_cell(record.get(key)) for key in fieldnames})
    return output.getvalue().encode("utf-8-sig")


def error_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return failed and no_pano records for errors.csv."""
    return [record for record in records if record.get("status") in {"failed", "no_pano"}]


def image_health(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Find missing, empty, and duplicate image files referenced by metadata."""
    missing: list[dict[str, Any]] = []
    empty: list[dict[str, Any]] = []
    by_md5: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record.get("status") != "success":
            continue
        image_path = record.get("image_path")
        if not image_path:
            missing.append(_image_issue(record, "缺少 image_path"))
            continue
        path = Path(str(image_path))
        if not path.exists():
            missing.append(_image_issue(record, "文件不存在"))
            continue
        if path.stat().st_size == 0:
            empty.append(_image_issue(record, "空文件"))
        md5 = str(record.get("image_md5") or "")
        if md5:
            by_md5.setdefault(md5, []).append(record)
    duplicates = [
        {"image_md5": md5, "task_ids": [record.get("task_id") for record in grouped]}
        for md5, grouped in by_md5.items()
        if len(grouped) > 1
    ]
    return {"missing": missing, "empty": empty, "duplicates": duplicates}


def _csv_cell(value: Any) -> Any:
    """Convert nested metadata values to CSV cells."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _image_issue(record: dict[str, Any], issue: str) -> dict[str, Any]:
    """Return a compact image health issue record."""
    return {
        "task_id": record.get("task_id"),
        "provider": record.get("provider"),
        "image_path": record.get("image_path"),
        "issue": issue,
    }


def _public_error_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return an error record safe for UI display."""
    return {
        "task_id": record.get("task_id"),
        "provider": record.get("provider"),
        "status": record.get("status"),
        "error_type": record.get("error_type"),
        "error_code": record.get("error_code"),
        "error_message": record.get("error_message") or record.get("message"),
        "completed_at": record.get("completed_at"),
    }


def _records_per_second(records: list[dict[str, Any]]) -> float:
    """Estimate processing speed from completed_at timestamps."""
    times: list[datetime] = []
    for record in records:
        completed_at = record.get("completed_at")
        if not completed_at:
            continue
        try:
            times.append(datetime.fromisoformat(str(completed_at)))
        except ValueError:
            continue
    if len(times) < 2:
        return 0.0
    elapsed = (max(times) - min(times)).total_seconds()
    if elapsed <= 0:
        return 0.0
    return len(times) / elapsed


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    """Convert dataclass values to dicts for Streamlit display."""
    if is_dataclass(value):
        return asdict(value)
    return dict(value)


def show_validation(check_api: bool = False) -> None:
    """Display config validation result."""
    import streamlit as st

    result = config_service().validate(check_api=check_api)
    if result.ok:
        st.success(_zh_message(result.message))
    else:
        st.error(_zh_message(result.message))
    cols = st.columns(2)
    cols[0].metric("输入点数", result.input_points)
    cols[1].metric("计划任务数", result.planned_tasks)
    st.json({"密钥状态": result.credential_status or {}})
    if result.warnings:
        st.warning("\n".join(_zh_message(warning) for warning in result.warnings))
    if result.errors:
        st.error("\n".join(_zh_message(error) for error in result.errors))


def _zh_message(message: str) -> str:
    """Translate common service messages for the Streamlit UI."""
    replacements = {
        "Config is valid.": "配置有效。",
        "Config validation failed.": "配置校验失败。",
        "Config is invalid.": "配置无效。",
        "dry_run is enabled; no real API requests will be made.": "dry_run 已开启：不会发起真实 API 请求。",
        "API connectivity check is limited to local credential/config checks; no image request was sent.": (
            "API 连通性检查目前只做本地凭证和配置检查，不会请求图片。"
        ),
        "Baidu AK env var is not set": "百度 AK 环境变量未设置",
        "Tencent key env var is not set": "腾讯 Key 环境变量未设置",
    }
    translated = message
    for source, target in replacements.items():
        translated = translated.replace(source, target)
    return translated
