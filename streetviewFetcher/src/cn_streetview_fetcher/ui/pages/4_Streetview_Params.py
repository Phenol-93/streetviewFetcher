"""街景参数配置页面。"""

from pydantic import ValidationError

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.ui.state import load_config, parse_float_list, save_config, setup_page

st = setup_page("街景参数配置")
config = load_config()

headings_text = st.text_input("朝向 headings", value=",".join(str(v) for v in config.headings))
pitches_text = st.text_input("俯仰 pitches", value=",".join(str(v) for v in config.pitches))

st.subheader("百度")
baidu_width = st.number_input("百度 width", min_value=1, max_value=1024, value=config.baidu.width)
baidu_height = st.number_input("百度 height", min_value=1, max_value=512, value=config.baidu.height)
baidu_fov = st.number_input("百度 fov", min_value=10, max_value=120, value=config.baidu.fov)
coordtypes = ["wgs84ll", "bd09ll"]
baidu_coordtype = st.selectbox("百度 coordtype", coordtypes, index=coordtypes.index(config.baidu.coordtype))
use_panoid = st.checkbox("有 panoid 时优先使用 panoid", value=config.baidu.use_panoid)

st.subheader("腾讯")
tencent_size = st.text_input("腾讯 size", value=config.tencent.size)
tencent_radius = st.number_input("腾讯 radius", min_value=1, max_value=200, value=config.tencent.radius)

st.subheader("执行参数")
concurrency = st.number_input("并发数", min_value=1, value=config.concurrency)
rate_limit = st.number_input("限速：请求/秒", min_value=0.1, value=float(config.rate_limit))
retry_times = st.number_input("重试次数", min_value=0, value=config.retry_times)
dry_run = st.checkbox("dry_run 试运行", value=config.dry_run)
resume = st.checkbox("resume 断点续跑", value=config.resume)

if st.button("保存街景参数"):
    try:
        updated = config.model_copy(
            update={
                "headings": parse_float_list(headings_text, "headings"),
                "pitches": parse_float_list(pitches_text, "pitches"),
                "concurrency": int(concurrency),
                "rate_limit": float(rate_limit),
                "retry_times": int(retry_times),
                "dry_run": dry_run,
                "resume": resume,
                "baidu": config.baidu.model_copy(
                    update={
                        "width": int(baidu_width),
                        "height": int(baidu_height),
                        "fov": int(baidu_fov),
                        "coordtype": baidu_coordtype,
                        "use_panoid": use_panoid,
                    }
                ),
                "tencent": config.tencent.model_copy(update={"size": tencent_size, "radius": int(tencent_radius)}),
            }
        )
        save_config(AppConfig.model_validate(updated.model_dump()))
        st.success("已保存 config.yaml")
    except (ValueError, ValidationError) as exc:
        st.error(str(exc))

st.subheader("当前提醒")
warnings = config.warnings()
if warnings:
    st.warning("\n".join(warnings))
else:
    st.success("暂无提醒。")
