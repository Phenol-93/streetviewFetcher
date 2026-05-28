"""Typed configuration models."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

ProviderName = Literal["baidu", "tencent", "both", "from_table"]
InputType = Literal["table", "bbox", "geojson", "polygon"]
CoordSysName = Literal["wgs84", "gcj02", "bd09"]
LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_TENCENT_SIZE_PATTERN = re.compile(r"^\s*(?P<width>\d+)\s*[xX*]\s*(?P<height>\d+)\s*$")


@dataclass(frozen=True, slots=True)
class ProviderCredentialStatus:
    """Non-sensitive provider credential availability flags."""

    baidu_ak_available: bool
    baidu_sn_available: bool
    tencent_key_available: bool


@dataclass(frozen=True, slots=True)
class ProviderCredentials:
    """Resolved API credentials read from environment variables.

    Instances of this class may contain secrets. Do not log or serialize them.
    """

    baidu_ak: str | None
    baidu_sn: str | None
    tencent_key: str | None


def _read_env(env_name: str | None) -> str | None:
    """Read a non-empty environment variable value."""
    if not env_name:
        return None
    value = os.getenv(env_name)
    if value is None or value == "":
        return None
    return value


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse a simple KEY=VALUE line from a dotenv file."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if key.startswith("export "):
        key = key.removeprefix("export ").strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _load_env_file_fallback(path: Path, override: bool) -> None:
    """Load a small dotenv subset without requiring python-dotenv."""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parsed = _parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value


def load_env_file(path: Path, override: bool = False) -> None:
    """Load environment variables from a dotenv file if it exists.

    Existing process environment variables win by default so shell-provided
    credentials can override project-local defaults.
    """
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_file_fallback(path, override=override)
        return
    load_dotenv(path, override=override)


def _parse_tencent_size(value: str) -> tuple[int, int]:
    """Parse a Tencent size string such as ``600x480``."""
    match = _TENCENT_SIZE_PATTERN.match(value)
    if match is None:
        raise ValueError("Tencent size must look like WIDTHxHEIGHT, for example 600x480.")
    width = int(match.group("width"))
    height = int(match.group("height"))
    return width, height


class BaiduConfig(BaseModel):
    """Baidu provider configuration."""

    ak_env: str = "BAIDU_MAP_AK"
    sn_env: str | None = "BAIDU_MAP_SN"
    width: int = Field(default=1024, ge=1, le=1024)
    height: int = Field(default=512, ge=1, le=512)
    fov: int = Field(default=90, ge=10, le=120)
    coordtype: Literal["wgs84ll", "bd09ll"] = "wgs84ll"
    use_panoid: bool = False
    timeout: float = Field(default=15.0, gt=0)
    max_retries: int = Field(default=3, ge=0)

    def api_key(self) -> str | None:
        """Read the Baidu API key from its configured environment variable."""
        return _read_env(self.ak_env)

    def sn(self) -> str | None:
        """Read the optional Baidu SN value from its configured environment variable."""
        return _read_env(self.sn_env)

    def credential_status(self) -> dict[str, bool]:
        """Return non-sensitive credential availability for UI display."""
        return {
            "ak_available": self.api_key() is not None,
            "sn_available": self.sn() is not None,
        }


class TencentConfig(BaseModel):
    """Tencent provider configuration."""

    model_config = ConfigDict(extra="allow")

    key_env: str = "TENCENT_MAP_KEY"
    size: str = "600x480"
    radius: int = Field(default=50, ge=1, le=200)
    use_pano_cache: bool = True
    skip_no_pano: bool = True
    timeout: float = Field(default=15.0, gt=0)
    max_retries: int = Field(default=3, ge=0)

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str) -> str:
        """Validate Tencent image size and normalize the separator."""
        width, height = _parse_tencent_size(value)
        if width > 960 or height > 640:
            raise ValueError("Tencent size cannot exceed 960x640.")
        if width <= 0 or height <= 0:
            raise ValueError("Tencent size width and height must be positive.")
        return f"{width}x{height}"

    def size_tuple(self) -> tuple[int, int]:
        """Return Tencent image size as ``(width, height)``."""
        return _parse_tencent_size(self.size)

    def api_key(self) -> str | None:
        """Read the Tencent API key from its configured environment variable."""
        return _read_env(self.key_env)

    def credential_status(self) -> dict[str, bool]:
        """Return non-sensitive credential availability for UI display."""
        return {"key_available": self.api_key() is not None}

    def warnings(self) -> list[str]:
        """Return Tencent-specific non-fatal configuration warnings."""
        extra = self.model_extra or {}
        if "fov" in extra:
            return ["Tencent Street View static image API does not support fov; tencent.fov will be ignored."]
        return []


class UiConfig(BaseModel):
    """Streamlit UI configuration."""

    project_dir: Path = Path(".")
    preview_rows: int = Field(default=20, ge=1)
    max_preview_points: int = Field(default=500, ge=1)
    enable_map_preview: bool = True
    theme: Literal["light", "dark", "system"] = "light"
    auto_refresh_seconds: int = Field(default=2, ge=1)


class AppConfig(BaseModel):
    """Application configuration shared by CLI and UI."""

    provider: ProviderName = "baidu"
    input_type: InputType = "table"
    input_path: Path | None = None
    bbox: tuple[float, float, float, float] | None = None
    polygon: list[tuple[float, float]] | None = None
    spacing_meters: float = Field(default=50.0, gt=0)
    output_dir: Path = Path("output")
    metadata_path: Path = Path("output/metadata.jsonl")
    coord_sys: CoordSysName = "wgs84"
    headings: list[float] = Field(default_factory=lambda: [0.0])
    pitches: list[float] = Field(default_factory=lambda: [0.0])
    concurrency: int = Field(default=4, ge=1)
    rate_limit: float = Field(default=2.0, gt=0)
    retry_times: int = Field(default=3, ge=0)
    resume: bool = True
    dry_run: bool = True
    dedupe: bool = True
    log_level: LogLevelName = "INFO"
    baidu: BaiduConfig = Field(default_factory=BaiduConfig)
    tencent: TencentConfig = Field(default_factory=TencentConfig)
    ui: UiConfig = Field(default_factory=UiConfig)

    @field_validator("headings")
    @classmethod
    def validate_headings(cls, values: list[float]) -> list[float]:
        """Validate Baidu/Tencent heading values."""
        if not values:
            raise ValueError("headings cannot be empty.")
        invalid = [value for value in values if value < 0 or value > 360]
        if invalid:
            raise ValueError("heading values must be in the range 0..360 degrees.")
        return values

    @field_validator("pitches")
    @classmethod
    def validate_pitches(cls, values: list[float]) -> list[float]:
        """Validate Baidu/Tencent pitch values."""
        if not values:
            raise ValueError("pitches cannot be empty.")
        invalid = [value for value in values if value < -90 or value > 90]
        if invalid:
            raise ValueError("pitch values must be in the range -90..90 degrees.")
        return values

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize log level names before validation."""
        return value.upper()

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: tuple[float, float, float, float] | None) -> tuple[float, float, float, float] | None:
        """Validate bbox coordinates in ``min_lng,min_lat,max_lng,max_lat`` order."""
        if value is None:
            return None
        min_lng, min_lat, max_lng, max_lat = value
        if min_lng >= max_lng or min_lat >= max_lat:
            raise ValueError("bbox must be [min_lng, min_lat, max_lng, max_lat].")
        if min_lng < -180 or max_lng > 180 or min_lat < -90 or max_lat > 90:
            raise ValueError("bbox coordinates are outside valid longitude/latitude ranges.")
        return value

    @field_validator("polygon")
    @classmethod
    def validate_polygon(
        cls, value: list[tuple[float, float]] | None
    ) -> list[tuple[float, float]] | None:
        """Validate polygon coordinates."""
        if value is None:
            return None
        if len(value) < 3:
            raise ValueError("polygon must contain at least three coordinates.")
        for lng, lat in value:
            if lng < -180 or lng > 180 or lat < -90 or lat > 90:
                raise ValueError("polygon coordinates are outside valid longitude/latitude ranges.")
        return value

    @model_validator(mode="after")
    def validate_provider_specific_config(self) -> "AppConfig":
        """Run cross-field validation for provider-specific settings."""
        if self.provider in {"tencent", "both"} and self.baidu.fov:
            # Baidu fov is valid globally for Baidu. Tencent ignores fov-like values,
            # so warnings are emitted from ``warnings`` instead of raising here.
            pass
        return self

    def redacted(self) -> dict[str, Any]:
        """Return config data suitable for UI display and logs.

        The returned dict contains environment variable names and credential
        availability flags only, never resolved API key values.
        """
        data = self.model_dump(mode="json")
        data["credentials"] = asdict(self.credential_status())
        return data

    def credential_status(self) -> ProviderCredentialStatus:
        """Return non-sensitive provider credential availability flags."""
        baidu_status = self.baidu.credential_status()
        tencent_status = self.tencent.credential_status()
        return ProviderCredentialStatus(
            baidu_ak_available=baidu_status["ak_available"],
            baidu_sn_available=baidu_status["sn_available"],
            tencent_key_available=tencent_status["key_available"],
        )

    def resolve_credentials(self) -> ProviderCredentials:
        """Read provider credentials from environment variables.

        The returned object may contain secrets and must not be logged.
        """
        return ProviderCredentials(
            baidu_ak=self.baidu.api_key(),
            baidu_sn=self.baidu.sn(),
            tencent_key=self.tencent.api_key(),
        )

    def warnings(self) -> list[str]:
        """Return non-fatal configuration warnings."""
        warnings = self.tencent.warnings()
        if self.dry_run:
            warnings.append("dry_run is enabled; no real API requests will be made.")
        return warnings


def create_default_config() -> AppConfig:
    """Create the default application configuration."""
    return AppConfig(input_path=Path("examples/input_points.csv"))


def load_config(path: Path) -> AppConfig:
    """Load an application configuration from YAML."""
    load_env_file(path.parent / ".env")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: Path) -> None:
    """Write an application configuration to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)
