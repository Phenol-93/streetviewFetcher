"""Configuration model tests."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from cn_streetview_fetcher.config import AppConfig, TencentConfig, create_default_config, load_config, save_config


def test_tencent_size_is_normalized_and_limited() -> None:
    """Tencent size supports common separators and enforces documented limits."""
    assert TencentConfig(size="960X640").size == "960x640"
    with pytest.raises(ValidationError):
        TencentConfig(size="961x640")
    with pytest.raises(ValidationError):
        TencentConfig(size="960x641")
    with pytest.raises(ValidationError):
        TencentConfig(radius=201)


def test_baidu_and_angle_ranges_are_validated() -> None:
    """Baidu dimensions and global heading/pitch ranges are validated."""
    with pytest.raises(ValidationError):
        AppConfig(baidu={"width": 1025})
    with pytest.raises(ValidationError):
        AppConfig(baidu={"height": 513})
    with pytest.raises(ValidationError):
        AppConfig(headings=[361])
    with pytest.raises(ValidationError):
        AppConfig(pitches=[-91])


def test_tencent_fov_is_warning_not_error() -> None:
    """Unsupported Tencent fov values are preserved as warnings."""
    config = AppConfig(tencent={"fov": 90})
    assert any("does not support fov" in warning for warning in config.warnings())


def test_credentials_are_read_but_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    """API keys are read from env while redacted config hides secret values."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    monkeypatch.setenv("BAIDU_MAP_SN", "baidu-sn")
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = create_default_config()

    credentials = config.resolve_credentials()
    assert credentials.baidu_ak == "baidu-secret"
    assert credentials.baidu_sn == "baidu-sn"
    assert credentials.tencent_key == "tencent-secret"

    display = config.redacted()
    display_text = repr(display)
    assert "baidu-secret" not in display_text
    assert "baidu-sn" not in display_text
    assert "tencent-secret" not in display_text
    assert display["credentials"]["baidu_ak_available"] is True
    assert display["credentials"]["tencent_key_available"] is True


def test_yaml_roundtrip_keeps_model_values(tmp_path: Path) -> None:
    """YAML load and save roundtrip through typed config."""
    path = tmp_path / "config.yaml"
    config = AppConfig(provider="both", headings=[0, 90], pitches=[0], tencent={"size": "640*480"})
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.provider == "both"
    assert loaded.headings == [0, 90]
    assert loaded.tencent.size == "640x480"
    assert "BAIDU_MAP_AK" in path.read_text(encoding="utf-8")
    assert os.getenv("BAIDU_MAP_AK", "not-a-secret") not in path.read_text(encoding="utf-8")


def test_load_config_reads_dotenv_next_to_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Project-local .env values are available to config credential helpers."""
    env_name = "TEST_DOTENV_BAIDU_AK"
    monkeypatch.delenv(env_name, raising=False)
    (tmp_path / ".env").write_text(f"{env_name}=from-dotenv\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    save_config(AppConfig(baidu={"ak_env": env_name}), path)

    try:
        loaded = load_config(path)
        assert loaded.baidu.api_key() == "from-dotenv"
        assert "from-dotenv" not in repr(loaded.redacted())
    finally:
        os.environ.pop(env_name, None)


def test_shell_env_wins_over_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing process environment variables are not overwritten by .env."""
    env_name = "TEST_DOTENV_PRIORITY_BAIDU_AK"
    monkeypatch.setenv(env_name, "from-shell")
    (tmp_path / ".env").write_text(f"{env_name}=from-dotenv\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    save_config(AppConfig(baidu={"ak_env": env_name}), path)

    loaded = load_config(path)
    assert loaded.baidu.api_key() == "from-shell"
