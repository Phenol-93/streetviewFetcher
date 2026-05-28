"""任务执行页面。"""

from cn_streetview_fetcher.services import FetchService, ResumeService
from cn_streetview_fetcher.ui.state import dataclass_to_dict, fetch_progress_snapshot, load_config, setup_page

st = setup_page("任务执行")
config = load_config()

st.warning("下载只会调用官方 API。确认权限和配额前，请保持 dry_run 开启。")

try:
    snapshot = fetch_progress_snapshot(config)
    st.progress(snapshot["progress"])
    cols = st.columns(6)
    cols[0].metric("总数", snapshot["total"])
    cols[1].metric("已完成", snapshot["completed"])
    cols[2].metric("成功", snapshot["success"])
    cols[3].metric("失败", snapshot["failed"])
    cols[4].metric("无街景", snapshot["no_pano"])
    cols[5].metric("已跳过", snapshot["skipped"])
    st.metric("当前速度", f"{snapshot['speed_per_second']:.2f} 任务/秒")
    st.caption(f"状态来源：{snapshot['metadata_path']}")

    st.subheader("操作")
    col_a, col_b, col_c = st.columns(3)
    if col_a.button("开始下载"):
        result = FetchService(config).fetch()
        st.json(dataclass_to_dict(result))
        st.rerun()

    if col_b.button("继续未完成任务"):
        result = FetchService(config).resume()
        st.json(dataclass_to_dict(result))
        st.rerun()

    if col_c.button("重试失败任务"):
        result = FetchService(config).retry_failed()
        st.json(dataclass_to_dict(result))
        st.rerun()

    st.subheader("续跑 / 重试范围")
    resume_service = ResumeService(config)
    pending = resume_service.pending_task_ids()
    failed = resume_service.failed_task_ids()
    sel_cols = st.columns(2)
    sel_cols[0].metric("可续跑任务", len(pending))
    sel_cols[1].metric("可重试失败任务", len(failed))

    st.subheader("最近错误")
    if snapshot["recent_errors"]:
        st.dataframe(snapshot["recent_errors"], use_container_width=True)
    else:
        st.info("暂无最近错误。")

    st.subheader("运行说明")
    st.write(
        "下载器会在每个任务完成后立即追加 metadata。页面刷新后会从 metadata 重新计算进度，"
        "因此成功任务可以被安全跳过并继续执行剩余任务。"
    )
    st.caption("本页面不会显示 API Key 原文。")
except Exception as exc:
    st.error(str(exc))
    st.info("请先修正输入或配置问题，再回到本页面执行任务。")
