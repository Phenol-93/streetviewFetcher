"""服务配置页面。"""

from pydantic import ValidationError

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.ui.state import dataclass_to_dict, load_config, save_config, setup_page, show_validation

st = setup_page("服务配置")
config = load_config()

providers = ["baidu", "tencent", "both", "from_table"]
provider = st.selectbox("地图服务选择", providers, index=providers.index(config.provider))
baidu_ak_env = st.text_input("百度 AK 环境变量名", value=config.baidu.ak_env)
baidu_sn_env = st.text_input("百度 SN 环境变量名", value=config.baidu.sn_env or "")
tencent_key_env = st.text_input("腾讯 Key 环境变量名", value=config.tencent.key_env)

st.subheader("密钥状态")
credential_status = dataclass_to_dict(config.credential_status())
cols = st.columns(3)
cols[0].metric("百度 AK", "存在" if credential_status["baidu_ak_available"] else "未设置")
cols[1].metric("百度 SN", "存在" if credential_status["baidu_sn_available"] else "未设置")
cols[2].metric("腾讯 Key", "存在" if credential_status["tencent_key_available"] else "未设置")
st.caption("UI 不会显示或写入 API Key 原文。")

if st.button("保存服务配置"):
    try:
        updated = config.model_copy(
            update={
                "provider": provider,
                "baidu": config.baidu.model_copy(update={"ak_env": baidu_ak_env, "sn_env": baidu_sn_env or None}),
                "tencent": config.tencent.model_copy(update={"key_env": tencent_key_env}),
            }
        )
        save_config(AppConfig.model_validate(updated.model_dump()))
        st.success("已保存 config.yaml")
    except ValidationError as exc:
        st.error(str(exc))

st.subheader("配置校验")
check_api = st.checkbox("可选：连通性/配置检查", value=False)
if st.button("运行校验"):
    show_validation(check_api=check_api)
