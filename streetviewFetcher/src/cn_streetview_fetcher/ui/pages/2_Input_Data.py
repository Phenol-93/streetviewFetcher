"""输入数据页面。"""

from pathlib import Path

from pydantic import ValidationError

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.services import InputService
from cn_streetview_fetcher.ui.state import (
    current_project_dir,
    dataclass_to_dict,
    load_config,
    parse_bbox,
    save_config,
    save_uploaded_file,
    setup_page,
    write_points_jsonl,
)

st = setup_page("输入数据")
config = load_config()

st.subheader("上传文件")
table_file = st.file_uploader("上传 CSV 或 Excel", type=["csv", "xls", "xlsx"])
geojson_file = st.file_uploader("上传 GeoJSON", type=["geojson", "json"])

saved_path: Path | None = None
if table_file is not None and st.button("保存上传的表格"):
    saved_path = save_uploaded_file(table_file)
    st.success(f"已保存：{saved_path}")
if geojson_file is not None and st.button("保存上传的 GeoJSON"):
    saved_path = save_uploaded_file(geojson_file)
    st.success(f"已保存：{saved_path}")

st.subheader("输入配置")
input_types = ["table", "bbox", "geojson", "polygon"]
input_type = st.selectbox("输入类型", input_types, index=input_types.index(config.input_type))
default_path = saved_path or config.input_path
input_path = st.text_input("输入文件路径", value=str(default_path or ""))
coord_systems = ["wgs84", "gcj02", "bd09"]
coord_sys = st.selectbox("默认坐标系", coord_systems, index=coord_systems.index(config.coord_sys))
spacing_meters = st.number_input("采样间距 spacing_meters", min_value=1.0, value=float(config.spacing_meters))
bbox_text = st.text_input(
    "bbox: min_lng,min_lat,max_lng,max_lat",
    value=",".join(str(v) for v in config.bbox) if config.bbox else "",
)
preview_rows = st.number_input("预览行数", min_value=1, value=int(config.ui.preview_rows))

if st.button("保存输入配置"):
    try:
        bbox = parse_bbox(bbox_text)
        updated = config.model_copy(
            update={
                "input_type": input_type,
                "input_path": Path(input_path) if input_path else None,
                "coord_sys": coord_sys,
                "spacing_meters": spacing_meters,
                "bbox": bbox,
                "ui": config.ui.model_copy(update={"preview_rows": int(preview_rows)}),
            }
        )
        save_config(AppConfig.model_validate(updated.model_dump()))
        st.success("已保存 config.yaml")
    except (ValueError, ValidationError) as exc:
        st.error(str(exc))

st.subheader("预览与校验")
try:
    preview_config = AppConfig.model_validate(
        config.model_copy(
            update={
                "input_type": input_type,
                "input_path": Path(input_path) if input_path else None,
                "coord_sys": coord_sys,
                "spacing_meters": spacing_meters,
                "bbox": parse_bbox(bbox_text),
                "ui": config.ui.model_copy(update={"preview_rows": int(preview_rows)}),
            }
        ).model_dump()
    )
    preview = InputService(preview_config).preview(limit=int(preview_rows))
    st.write(f"总点数：{preview.total_points}")
    st.dataframe([dataclass_to_dict(row) for row in preview.rows], use_container_width=True)
    st.json(dataclass_to_dict(preview.stats))
    if preview.warnings:
        st.warning("\n".join(preview.warnings))
    if st.button("保存标准化点位到项目目录"):
        points = InputService(preview_config).load_points()
        output_path = write_points_jsonl(points, current_project_dir() / "normalized_points.jsonl")
        st.success(f"已保存 {len(points)} 个标准化点位到 {output_path}")
except Exception as exc:
    st.error(str(exc))
    st.info("请检查必填字段：表格至少需要 lng 和 lat；坐标必须在合法经纬度范围内。")
