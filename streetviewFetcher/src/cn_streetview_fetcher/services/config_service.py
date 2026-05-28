"""Configuration service."""

from dataclasses import dataclass
from pathlib import Path

from cn_streetview_fetcher.config import AppConfig, load_config, save_config
from cn_streetview_fetcher.inputs import InputReadError
from cn_streetview_fetcher.providers import BaiduProvider, TencentProvider
from cn_streetview_fetcher.services.input_service import InputService
from cn_streetview_fetcher.services.plan_service import PlanService


@dataclass(slots=True)
class ValidationResult:
    """Configuration validation result."""

    ok: bool
    message: str
    warnings: list[str]
    errors: list[str]
    input_points: int = 0
    planned_tasks: int = 0
    credential_status: dict[str, bool] | None = None


class ConfigService:
    """Load, save, and validate project configuration."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load(self) -> AppConfig:
        """Load the project configuration."""
        return load_config(self.config_path)

    def save(self, config: AppConfig) -> None:
        """Save the project configuration."""
        save_config(config, self.config_path)

    def validate(self, check_api: bool = False) -> ValidationResult:
        """Validate config syntax and local references."""
        errors: list[str] = []
        warnings: list[str] = []
        input_points = 0
        planned_tasks = 0
        try:
            config = self.load()
        except Exception as exc:
            return ValidationResult(
                ok=False,
                message="Config is invalid.",
                warnings=[],
                errors=[str(exc)],
            )

        warnings.extend(config.warnings())
        credential_status = config.credential_status()
        credential_map = {
            "baidu_ak_available": credential_status.baidu_ak_available,
            "baidu_sn_available": credential_status.baidu_sn_available,
            "tencent_key_available": credential_status.tencent_key_available,
        }

        try:
            input_result = InputService(config).read()
            input_points = input_result.stats.total_points
            warnings.extend(input_result.warnings)
        except InputReadError as exc:
            errors.append(str(exc))

        try:
            plan = PlanService(config).create_plan()
            planned_tasks = len(plan.tasks)
        except Exception as exc:
            errors.append(str(exc))

        active_providers = self._active_providers(config)
        if "baidu" in active_providers and not credential_status.baidu_ak_available:
            errors.append(f"Baidu AK env var is not set: {config.baidu.ak_env}")
        if "tencent" in active_providers and not credential_status.tencent_key_available:
            errors.append(f"Tencent key env var is not set: {config.tencent.key_env}")

        if check_api:
            warnings.extend(self._check_provider_connectivity(config, active_providers))

        ok = not errors
        return ValidationResult(
            ok=ok,
            message="Config is valid." if ok else "Config validation failed.",
            warnings=warnings,
            errors=errors,
            input_points=input_points,
            planned_tasks=planned_tasks,
            credential_status=credential_map,
        )

    def _active_providers(self, config: AppConfig) -> set[str]:
        """Return providers implied by config and input rows."""
        if config.provider == "baidu":
            return {"baidu"}
        if config.provider == "tencent":
            return {"tencent"}
        if config.provider == "both":
            return {"baidu", "tencent"}
        providers: set[str] = set()
        try:
            for point in InputService(config).load_points():
                if point.provider == "both":
                    providers.update({"baidu", "tencent"})
                elif point.provider in {"baidu", "tencent"}:
                    providers.add(point.provider)
        except InputReadError:
            return set()
        return providers or {"baidu"}

    def _check_provider_connectivity(self, config: AppConfig, providers: set[str]) -> list[str]:
        """Run non-image provider checks for CLI validation."""
        warnings: list[str] = []
        if "baidu" in providers:
            warnings.extend(BaiduProvider(config.baidu).validate_config())
        if "tencent" in providers:
            warnings.extend(TencentProvider(config.tencent).validate_config())
        warnings.append("API connectivity check is limited to local credential/config checks; no image request was sent.")
        return warnings
