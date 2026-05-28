"""结果浏览页面。"""

from pathlib import Path

from cn_streetview_fetcher.services import InspectService, ReportService
from cn_streetview_fetcher.storage import MetadataStore
from cn_streetview_fetcher.ui.state import (
    error_records,
    filter_metadata_records,
    image_health,
    load_config,
    records_to_csv_bytes,
    setup_page,
)

st = setup_page("结果浏览")
config = load_config()
inspect = InspectService(config).inspect()

cols = st.columns(4)
cols[0].metric("成功", inspect.success)
cols[1].metric("失败", inspect.failed)
cols[2].metric("无街景", inspect.no_pano)
cols[3].metric("已跳过", inspect.skipped)
st.json({"provider_counts": inspect.provider_counts or {}, "heading_counts": inspect.heading_counts or {}})

records = MetadataStore(config.metadata_path).read_all()
st.caption(f"Metadata 来源：{config.metadata_path}")

st.subheader("筛选")
providers = sorted({str(record.get("provider")) for record in records if record.get("provider")})
statuses = sorted({str(record.get("status")) for record in records if record.get("status")})
headings = sorted({str(record.get("heading")) for record in records if record.get("heading") is not None})
pitches = sorted({str(record.get("pitch")) for record in records if record.get("pitch") is not None})
tags = sorted({str(record.get("tag")) for record in records if record.get("tag")})

filter_cols = st.columns(5)
provider_filter = filter_cols[0].multiselect("地图服务", providers)
status_filter = filter_cols[1].multiselect("状态", statuses)
heading_filter = filter_cols[2].multiselect("朝向 heading", headings)
pitch_filter = filter_cols[3].multiselect("俯仰 pitch", pitches)
tag_filter = filter_cols[4].multiselect("标签 tag", tags)

filtered_records = filter_metadata_records(
    records,
    providers=provider_filter,
    statuses=status_filter,
    headings=heading_filter,
    pitches=pitch_filter,
    tags=tag_filter,
)

st.subheader("Metadata")
st.write(f"显示 {len(filtered_records)} / {len(records)} 条记录")
st.dataframe(filtered_records, use_container_width=True)

st.subheader("图片缩略图")
success_records = [record for record in filtered_records if record.get("status") == "success" and record.get("image_path")]
if success_records:
    gallery_cols = st.columns(4)
    for index, record in enumerate(success_records[: config.ui.max_preview_points]):
        path = Path(str(record.get("image_path")))
        with gallery_cols[index % 4]:
            if path.exists() and path.stat().st_size > 0:
                st.image(str(path), caption=str(record.get("task_id")), use_container_width=True)
            else:
                st.warning(f"图片缺失：{record.get('task_id')}")
            with st.expander("Metadata 详情"):
                st.json(record)
else:
    st.info("暂无可预览的成功图片记录。")

st.subheader("下载")
st.download_button(
    "下载 metadata.csv",
    data=records_to_csv_bytes(filtered_records),
    file_name="metadata.csv",
    mime="text/csv",
)
st.download_button(
    "下载 errors.csv",
    data=records_to_csv_bytes(error_records(filtered_records)),
    file_name="errors.csv",
    mime="text/csv",
)

st.subheader("图片健康检查")
health = image_health(records)
health_cols = st.columns(3)
health_cols[0].metric("图片缺失", len(health["missing"]))
health_cols[1].metric("空文件", len(health["empty"]))
health_cols[2].metric("重复 MD5", len(health["duplicates"]))
if health["missing"]:
    with st.expander("图片缺失"):
        st.dataframe(health["missing"], use_container_width=True)
if health["empty"]:
    with st.expander("空文件"):
        st.dataframe(health["empty"], use_container_width=True)
if health["duplicates"]:
    with st.expander("重复文件"):
        st.dataframe(health["duplicates"], use_container_width=True)

st.subheader("报告")
if st.button("生成 summary 报告"):
    path = ReportService(config).write_summary(config.output_dir / "summary.json")
    st.success(f"已写入：{path}")
if st.button("生成 errors 报告"):
    path = ReportService(config).write_errors(config.output_dir / "errors.csv")
    st.success(f"已写入：{path}")
