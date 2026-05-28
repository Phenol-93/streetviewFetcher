"""Streamlit UI entry point."""

from pathlib import Path
import subprocess
import sys


def app_path() -> Path:
    """Return the path to the Streamlit app file."""
    return Path(__file__).resolve()


def main() -> None:
    """Launch the Streamlit UI."""
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path())], check=False)


def render() -> None:
    """Render the Streamlit home page."""
    from cn_streetview_fetcher.services import InspectService, PlanService
    from cn_streetview_fetcher.ui.state import load_config, setup_page, show_validation

    st = setup_page("仪表盘")
    config = load_config()
    summary = PlanService(config).plan()
    inspect = InspectService(config).inspect()

    cols = st.columns(4)
    cols[0].metric("输入点数", summary.input_points)
    cols[1].metric("任务数", summary.deduped_tasks)
    cols[2].metric("成功", inspect.success)
    cols[3].metric("失败", inspect.failed)

    st.subheader("配置校验")
    show_validation(check_api=False)

    st.subheader("任务计划摘要")
    st.json(
        {
            "provider_counts": summary.provider_counts,
            "heading_counts": summary.heading_counts,
            "pitch_counts": summary.pitch_counts,
            "warnings": summary.warnings,
        }
    )

    st.subheader("脱敏配置")
    st.json(config.redacted())


if __name__ == "__main__":
    render()
