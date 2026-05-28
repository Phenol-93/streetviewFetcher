"""任务维护页面。"""

from cn_streetview_fetcher.services import ReportService, ResumeService
from cn_streetview_fetcher.ui.state import load_config, setup_page

st = setup_page("任务维护")
config = load_config()
resume = ResumeService(config)

pending = resume.pending_task_ids()
failed = resume.failed_task_ids()
cols = st.columns(2)
cols[0].metric("待完成任务", len(pending))
cols[1].metric("失败任务", len(failed))

if st.button("写入 summary 报告"):
    path = ReportService(config).write_summary(config.output_dir / "summary.json")
    st.success(f"已写入：{path}")

if st.button("写入 errors 报告"):
    path = ReportService(config).write_errors(config.output_dir / "errors.csv")
    st.success(f"已写入：{path}")

st.subheader("待完成")
st.dataframe([{"task_id": task_id} for task_id in pending[: config.ui.max_preview_points]])
st.subheader("失败")
st.dataframe([{"task_id": task_id} for task_id in failed[: config.ui.max_preview_points]])
