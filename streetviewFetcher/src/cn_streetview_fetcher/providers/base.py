"""Provider abstractions for official street-view APIs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

import httpx


class ProviderStatus(str, Enum):
    """Normalized provider result status."""

    SUCCESS = "success"
    NO_PANO = "no_pano"
    AUTH_ERROR = "auth_error"
    PARAM_ERROR = "param_error"
    COORD_ERROR = "coord_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(slots=True)
class ProviderRequest:
    """A provider HTTP request description."""

    url: str
    params: dict[str, Any]
    purpose: str = "image"


@dataclass(slots=True)
class MockHttpResponse:
    """Small mock HTTP response used before real API integration."""

    status_code: int
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    json_data: dict[str, Any] | None = None
    text: str = ""

    def json(self) -> dict[str, Any]:
        """Return mock JSON response data."""
        return self.json_data or {}

    @property
    def content_type(self) -> str:
        """Return response content type."""
        return self.headers.get("content-type", "")


class MockHttpClient:
    """Mock HTTP client that never performs network requests."""

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Return deterministic mock responses for provider requests."""
        _ = timeout
        params = request.params
        if params.get("__mock_status") == "auth_error":
            return MockHttpResponse(
                status_code=403,
                json_data={"status": 110, "message": "mock auth error"},
                text="mock auth error",
            )
        if params.get("__mock_status") == "param_error":
            return MockHttpResponse(
                status_code=400,
                json_data={"status": 2, "message": "mock param error"},
                text="mock param error",
            )
        if params.get("__mock_status") == "no_pano":
            return MockHttpResponse(status_code=200, json_data={"status": 404, "message": "mock no pano"})
        if request.purpose == "getpano":
            return MockHttpResponse(
                status_code=200,
                json_data={
                    "status": 0,
                    "detail": {
                        "id": "mock_tencent_pano",
                        "location": {"lat": params.get("lat"), "lng": params.get("lng")},
                        "description": "mock pano",
                    },
                },
            )
        return MockHttpResponse(
            status_code=200,
            content=b"mock-image-bytes",
            headers={"content-type": "image/jpeg"},
        )


class HttpClient(Protocol):
    """HTTP client interface used by providers."""

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Execute a GET request and return a response-like object."""


class HttpxHttpClient:
    """Real HTTP client backed by httpx."""

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Execute a real HTTP GET request."""
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(request.url, params=request.params)
        json_data: dict[str, Any] | None = None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            try:
                json_data = response.json()
            except ValueError:
                json_data = None
        return MockHttpResponse(
            status_code=response.status_code,
            content=response.content,
            headers={"content-type": content_type},
            json_data=json_data,
            text=response.text,
        )


@dataclass(slots=True)
class ProviderResult:
    """Normalized response returned by all providers."""

    status: ProviderStatus
    provider: str
    image_bytes: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return whether the result is successful."""
        return self.status == ProviderStatus.SUCCESS


class BaseStreetViewProvider(ABC):
    """Base class implemented by official street-view providers."""

    name: str

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self.http_client = http_client or MockHttpClient()

    @abstractmethod
    def validate_config(self) -> list[str]:
        """Validate provider configuration and return warnings."""

    @abstractmethod
    def prepare_point(self, task: Any) -> dict[str, Any]:
        """Prepare provider-specific point parameters from a StreetViewTask."""

    @abstractmethod
    def build_image_request(self, prepared: dict[str, Any]) -> ProviderRequest:
        """Build a provider image request description."""

    @abstractmethod
    def fetch_image(self, task: Any) -> ProviderResult:
        """Fetch one street-view image for a prepared task."""

    @abstractmethod
    def parse_response(self, response: MockHttpResponse, request: ProviderRequest) -> ProviderResult:
        """Parse a provider response into a normalized result."""

    @abstractmethod
    def normalize_metadata(self, task: Any, result: ProviderResult) -> dict[str, Any]:
        """Normalize provider metadata for storage or UI display."""

    @abstractmethod
    def redact_sensitive_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove API credentials from params before logging or metadata storage."""
