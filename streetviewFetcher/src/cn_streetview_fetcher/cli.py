"""Command line interface for cn-streetview-fetcher."""

from pathlib import Path
import subprocess
import sys
from typing import NoReturn

import typer

from cn_streetview_fetcher.config import AppConfig, create_default_config
from cn_streetview_fetcher.inputs import InputReadError
from cn_streetview_fetcher.services import ConfigService, FetchResult, FetchService, InspectService, PlanService, ResumeService

app = typer.Typer(help="Fetch street-view images through official APIs.")


@app.command()
def init(
    config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config file."),
) -> None:
    """Create a default configuration file."""
    if config_path.exists() and not force:
        _fail(
            f"Config already exists: {config_path}",
            "Use --force to overwrite it, or pass --config to write another path.",
        )
    service = ConfigService(config_path)
    service.save(create_default_config())
    typer.echo(f"Created default config: {config_path}")
    typer.echo("Next: set BAIDU_MAP_AK and/or TENCENT_MAP_KEY in your environment, then run `cnsv validate`.")


@app.command()
def validate(
    config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
    check_api: bool = typer.Option(False, "--check-api", help="Run provider credential/config checks without image download."),
) -> None:
    """Validate configuration, input, and API key availability."""
    result = ConfigService(config_path).validate(check_api=check_api)
    _section("Validation")
    typer.echo(result.message)
    typer.echo(f"Input points: {result.input_points}")
    typer.echo(f"Planned tasks: {result.planned_tasks}")
    typer.echo(f"Credentials: {result.credential_status or {}}")
    _print_warnings(result.warnings)
    if result.errors:
        _print_errors(result.errors)
        _repair_hint("Fix config.yaml/input files or set the missing API key environment variables, then rerun validate.")
        raise typer.Exit(code=1)


@app.command()
def plan(config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c")) -> None:
    """Generate a task plan and output statistics without downloading."""
    config = _load_config_or_exit(config_path)
    try:
        summary = PlanService(config).plan()
    except InputReadError as exc:
        _fail(str(exc), "Check input_path, input_type, coord_sys, and coordinate columns.")
    _section("Task Plan")
    typer.echo(summary.to_text())


@app.command()
def fetch(config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c")) -> None:
    """Execute downloads, or dry-run when configured."""
    config = _load_config_or_exit(config_path)
    if config.dry_run:
        typer.echo("dry_run is enabled. No image requests will be sent.")
    result = FetchService(config).fetch()
    _print_fetch_result("Fetch", result)


@app.command()
def resume(config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c")) -> None:
    """Continue unfinished tasks."""
    config = _load_config_or_exit(config_path)
    if config.dry_run:
        typer.echo("dry_run is enabled. Resume will only select tasks; no image requests will be sent.")
    result = FetchService(config).resume()
    _print_fetch_result("Resume", result)


@app.command("retry-failed")
def retry_failed(config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c")) -> None:
    """Retry failed tasks only."""
    config = _load_config_or_exit(config_path)
    if config.dry_run:
        typer.echo("dry_run is enabled. Retry-failed will only select tasks; no image requests will be sent.")
    result = FetchService(config).retry_failed()
    _print_fetch_result("Retry Failed", result)


@app.command()
def inspect(config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c")) -> None:
    """Inspect metadata and output status statistics."""
    config = _load_config_or_exit(config_path)
    result = InspectService(config).inspect()
    _section("Metadata Inspect")
    typer.echo(result.to_text())


@app.command()
def ui() -> None:
    """Open the local Streamlit UI."""
    from cn_streetview_fetcher.ui.app import app_path

    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path())], check=False)


def _load_config_or_exit(config_path: Path) -> AppConfig:
    """Load config or exit with a repair hint."""
    try:
        return ConfigService(config_path).load()
    except Exception as exc:
        _fail(f"Could not load config: {exc}", "Run `cnsv init` or pass a valid --config path.")


def _print_fetch_result(title: str, result: FetchResult) -> None:
    """Print a fetch-like command result."""
    _section(title)
    typer.echo(result.message)
    typer.echo(f"Total: {result.total}")
    typer.echo(f"Success: {result.success}")
    typer.echo(f"Failed: {result.failed}")
    typer.echo(f"Skipped: {result.skipped}")
    typer.echo(f"Dry-run: {result.dry_run}")
    if result.failed:
        _repair_hint("Run `cnsv inspect` for details, then `cnsv retry-failed` after fixing the cause.")


def _section(title: str) -> None:
    """Print a simple section header."""
    typer.echo(f"\n== {title} ==")


def _print_warnings(warnings: list[str]) -> None:
    """Print warnings."""
    if warnings:
        typer.echo("\nWarnings:")
        for warning in warnings:
            typer.echo(f"- {warning}")


def _print_errors(errors: list[str]) -> None:
    """Print errors."""
    typer.echo("\nErrors:")
    for error in errors:
        typer.echo(f"- {error}")


def _repair_hint(message: str) -> None:
    """Print a repair hint."""
    typer.echo(f"\nFix: {message}")


def _fail(message: str, repair: str) -> NoReturn:
    """Print an error and exit."""
    typer.echo(f"Error: {message}", err=True)
    typer.echo(f"Fix: {repair}", err=True)
    raise typer.Exit(code=1)
