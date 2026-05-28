"""任务计划页面。"""

from cn_streetview_fetcher.services import InputService, PlanService
from cn_streetview_fetcher.ui.state import (
    current_project_dir,
    dataclass_to_dict,
    load_config,
    setup_page,
    write_plan_summary,
    write_tasks_jsonl,
)

st = setup_page("任务计划")
config = load_config()

st.info("本页面只调用 PlanService，不会请求百度或腾讯图片；用于 dry-run 规划是安全的。")

try:
    input_preview = InputService(config).preview(limit=config.ui.preview_rows)
    plan = PlanService(config).create_plan()
    summary = plan.summary

    st.subheader("数量统计")
    cols = st.columns(6)
    cols[0].metric("原始点数", input_preview.stats.total_points)
    cols[1].metric("标准化点数", summary.input_points)
    cols[2].metric("去重前任务数", summary.planned_tasks)
    cols[3].metric("去重后任务数", summary.deduped_tasks)
    cols[4].metric("预计 getpano 请求", summary.estimated_getpano_requests)
    cols[5].metric("预计图片请求", summary.estimated_image_requests)

    st.subheader("分布")
    dcols = st.columns(3)
    dcols[0].json(summary.provider_counts)
    dcols[0].caption("地图服务分布")
    dcols[1].json(summary.heading_counts)
    dcols[1].caption("heading 分布")
    dcols[2].json(summary.pitch_counts)
    dcols[2].caption("pitch 分布")

    st.subheader("配额和费用风险")
    st.warning(
        "预计请求可能消耗官方 API 配额或产生费用。将 dry_run 设为 false 前，请先在百度/腾讯控制台确认当前价格、"
        "配额、商业授权和每日限制。"
    )
    if summary.estimated_image_requests > 1000:
        st.warning("任务量较大：图片请求超过 1,000 次。建议降低采样密度或减少 heading 数量。")
    if summary.estimated_getpano_requests:
        st.info("腾讯任务通常每个任务需要一次 getpano 请求和一次 image 请求。")

    st.subheader("提醒和参数冲突")
    warnings = list(summary.warnings)
    if summary.provider_counts.get("tencent") and any(task.fov is not None for task in plan.tasks if task.provider == "tencent"):
        warnings.append("腾讯图片接口不支持 fov。fov 会保留在任务 metadata 中，但腾讯请求会忽略它。")
    if warnings:
        st.warning("\n".join(warnings))
    else:
        st.success("暂无提醒。")

    st.subheader("任务预览")
    st.dataframe([dataclass_to_dict(task) for task in plan.tasks[: config.ui.max_preview_points]], use_container_width=True)

    st.subheader("导出")
    export_dir = current_project_dir()
    col_a, col_b = st.columns(2)
    if col_a.button("导出 tasks.jsonl"):
        path = write_tasks_jsonl(plan.tasks, export_dir / "tasks.jsonl")
        st.success(f"已写入 {len(plan.tasks)} 个任务到 {path}")
    if col_b.button("导出 plan_summary.json"):
        path = write_plan_summary(summary, export_dir / "plan_summary.json")
        st.success(f"已写入摘要到 {path}")

except Exception as exc:
    st.error(str(exc))
    st.info("请修正输入数据或配置后，再重新生成任务计划。")
