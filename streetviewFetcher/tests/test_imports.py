"""Smoke tests for the initial skeleton."""

from pathlib import Path

from cn_streetview_fetcher.config import create_default_config, save_config, load_config
from cn_streetview_fetcher.services import ConfigService, PlanService


def test_default_config_roundtrip(tmp_path: Path) -> None:
    """Default config can be saved and loaded."""
    path = tmp_path / "config.yaml"
    config = create_default_config()
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.provider == config.provider


def test_services_smoke(tmp_path: Path) -> None:
    """Core services can be constructed without real API requests."""
    path = tmp_path / "config.yaml"
    save_config(create_default_config(), path)
    config = ConfigService(path).load()
    summary = PlanService(config).plan()
    assert summary.planned_tasks == 1
