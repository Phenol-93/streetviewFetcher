"""CLI tests."""

from pathlib import Path

from typer.testing import CliRunner

from cn_streetview_fetcher.cli import app
from cn_streetview_fetcher.config import AppConfig, save_config
from cn_streetview_fetcher.storage import MetadataStore


runner = CliRunner()


def test_cli_init_plan_and_validate(tmp_path: Path, monkeypatch) -> None:
    """CLI init, validate, and plan use core services and print clear output."""
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")

    init_result = runner.invoke(app, ["init", "--config", str(config_path)])
    assert init_result.exit_code == 0
    assert "Created default config" in init_result.output

    validate_result = runner.invoke(app, ["validate", "--config", str(config_path)])
    assert validate_result.exit_code == 0
    assert "Validation" in validate_result.output
    assert "baidu-secret" not in validate_result.output

    plan_result = runner.invoke(app, ["plan", "--config", str(config_path)])
    assert plan_result.exit_code == 0
    assert "Task Plan" in plan_result.output
    assert "Planned tasks" in plan_result.output


def test_cli_validate_reports_missing_key(tmp_path: Path, monkeypatch) -> None:
    """validate reports missing key with repair hints."""
    monkeypatch.delenv("BAIDU_MAP_AK", raising=False)
    config_path = tmp_path / "config.yaml"
    save_config(AppConfig(input_path=Path("examples/input_points.csv")), config_path)

    result = runner.invoke(app, ["validate", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "Baidu AK env var is not set" in result.output
    assert "Fix:" in result.output


def test_cli_fetch_dry_run_does_not_write_metadata(tmp_path: Path, monkeypatch) -> None:
    """dry-run fetch does not perform downloads or write metadata."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    metadata_path = tmp_path / "metadata.jsonl"
    config_path = tmp_path / "config.yaml"
    save_config(
        AppConfig(
            input_path=Path("examples/input_points.csv"),
            metadata_path=metadata_path,
            output_dir=tmp_path / "output",
            dry_run=True,
        ),
        config_path,
    )

    result = runner.invoke(app, ["fetch", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "dry_run is enabled" in result.output
    assert not metadata_path.exists()


def test_cli_inspect_outputs_distributions(tmp_path: Path) -> None:
    """inspect prints status counts and distributions."""
    metadata_path = tmp_path / "metadata.jsonl"
    MetadataStore(metadata_path).append({"task_id": "t1", "status": "success", "provider": "baidu", "heading": 0})
    MetadataStore(metadata_path).append({"task_id": "t2", "status": "failed", "provider": "tencent", "heading": 90})
    config_path = tmp_path / "config.yaml"
    save_config(AppConfig(input_path=Path("examples/input_points.csv"), metadata_path=metadata_path), config_path)

    result = runner.invoke(app, ["inspect", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Success: 1" in result.output
    assert "Failed: 1" in result.output
    assert "Provider counts" in result.output
    assert "Heading counts" in result.output
