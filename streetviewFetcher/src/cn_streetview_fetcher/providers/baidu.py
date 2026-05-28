"""Baidu official Panorama Static Image provider mock implementation."""

import re
from typing import Any

from cn_streetview_fetcher.config import BaiduConfig
from cn_streetview_fetcher.providers.base import (
    BaseStreetViewProvider,
    HttpClient,
    HttpxHttpClient,
    MockHttpResponse,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
)


class BaiduProvider(BaseStreetViewProvider):
    """Provider facade for Baidu official Panorama Static Image API."""

    name = "baidu"
    image_endpoint = "https://api.map.baidu.com/panorama/v2"

    def __init__(self, config: BaiduConfig, http_client: HttpClient | None = None) -> None:
        super().__init__(http_client=http_client or HttpxHttpClient())
        self.config = config

    def validate_config(self) -> list[str]:
        """Validate Baidu provider configuration."""
        warnings: list[str] = []
        if self.config.api_key() is None:
            warnings.append(f"Baidu API key env var is not set: {self.config.ak_env}")
        return warnings

    def prepare_point(self, task: Any) -> dict[str, Any]:
        """Prepare Baidu location or panoid request fields."""
        prepared = {
            "task_id": task.task_id,
            "heading": task.heading,
            "pitch": task.pitch,
            "fov": task.fov,
            "width": task.width or self.config.width,
            "height": task.height or self.config.height,
            "coordtype": self.config.coordtype,
            "request_lng": task.request_lng,
            "request_lat": task.request_lat,
            "panoid_input": task.panoid_input,
        }
        if self.config.use_panoid and task.panoid_input:
            prepared["panoid"] = task.panoid_input
        else:
            prepared["location"] = f"{task.request_lng},{task.request_lat}"
        return prepared

    def build_image_request(self, prepared: dict[str, Any]) -> ProviderRequest:
        """Build a Baidu panorama image request."""
        params: dict[str, Any] = {
            "ak": self.config.api_key() or "__missing_baidu_ak__",
            "width": prepared["width"],
            "height": prepared["height"],
            "heading": prepared["heading"],
            "pitch": prepared["pitch"],
            "fov": prepared["fov"],
            "coordtype": prepared["coordtype"],
        }
        if self.config.sn():
            params["sn"] = self.config.sn()
        if "panoid" in prepared:
            params["panoid"] = prepared["panoid"]
        else:
            params["location"] = prepared["location"]
        return ProviderRequest(url=self.image_endpoint, params=params, purpose="image")

    def fetch_image(self, task: Any) -> ProviderResult:
        """Fetch a Baidu image using the configured HTTP client."""
        prepared = self.prepare_point(task)
        request = self.build_image_request(prepared)
        if self.config.api_key() is None:
            return ProviderResult(
                status=ProviderStatus.AUTH_ERROR,
                provider=self.name,
                message="Baidu API key is not configured.",
                debug_info={
                    "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)}
                },
            )
        try:
            response = self._get_with_retries(request)
        except Exception as exc:
            return ProviderResult(
                status=ProviderStatus.NETWORK_ERROR,
                provider=self.name,
                message="Baidu network error.",
                debug_info={
                    "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)},
                    "error": str(exc),
                },
            )
        result = self.parse_response(response, request)
        result.metadata.update({"task_id": task.task_id, "provider": self.name})
        result.metadata.update(self.normalize_metadata(task, result))
        return result

    def parse_response(self, response: MockHttpResponse, request: ProviderRequest) -> ProviderResult:
        """Parse a Baidu response into ProviderResult."""
        debug_info = {
            "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)},
            "status_code": response.status_code,
            "content_type": response.content_type,
        }
        if response.status_code >= 500:
            return ProviderResult(
                status=ProviderStatus.SERVER_ERROR,
                provider=self.name,
                message="Baidu server error.",
                debug_info=debug_info,
            )
        if response.status_code in {401, 403}:
            return ProviderResult(
                status=ProviderStatus.AUTH_ERROR,
                provider=self.name,
                message="Baidu authentication failed.",
                debug_info=debug_info,
            )
        if response.status_code >= 400:
            return ProviderResult(
                status=ProviderStatus.PARAM_ERROR,
                provider=self.name,
                message="Baidu request parameter error.",
                debug_info=debug_info,
            )
        if response.content_type.lower().startswith("image/") and response.content:
            return ProviderResult(
                status=ProviderStatus.SUCCESS,
                provider=self.name,
                image_bytes=response.content,
                message="Baidu image fetched.",
                debug_info=debug_info,
            )
        payload = response.json()
        debug_info["response"] = payload
        if response.text:
            debug_info["response_text"] = response.text
        status = str(payload.get("status", "")) or _extract_error_token(response.text, "status")
        error_code = str(payload.get("error", payload.get("code", status)))
        if not error_code:
            error_code = _extract_error_token(response.text, "error") or _extract_error_token(response.text, "code")
        error_message = str(payload.get("message", payload.get("msg", response.text or "")))
        if status in {"404", "302"}:
            normalized_status = ProviderStatus.NO_PANO
            message = "Baidu returned no panorama for this location."
        elif status in {"1", "2", "200", "201"}:
            normalized_status = ProviderStatus.PARAM_ERROR
            message = error_message or "Baidu rejected request parameters."
        elif status in {"101", "102", "110", "111"}:
            normalized_status = ProviderStatus.AUTH_ERROR
            message = error_message or "Baidu authentication or quota error."
        else:
            normalized_status = ProviderStatus.UNKNOWN_ERROR
            message = error_message or "Baidu returned an unknown non-image response."
        debug_info["error_code"] = error_code
        return ProviderResult(status=normalized_status, provider=self.name, message=message, debug_info=debug_info)

    def _get_with_retries(self, request: ProviderRequest) -> MockHttpResponse:
        """Execute a request with retry for network errors only."""
        attempts = max(1, self.config.max_retries + 1)
        last_error: Exception | None = None
        for _attempt in range(attempts):
            try:
                return self.http_client.get(request, timeout=self.config.timeout)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Network request failed after {attempts} attempts: {type(last_error).__name__}")

    def normalize_metadata(self, task: Any, result: ProviderResult) -> dict[str, Any]:
        """Normalize Baidu metadata for storage or UI."""
        _ = result
        prepared = self.prepare_point(task)
        request = self.build_image_request(prepared)
        return {
            "provider": self.name,
            "request_mode": "panoid" if "panoid" in prepared else "location",
            "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)},
        }

    def redact_sensitive_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove Baidu credentials from request params."""
        redacted = dict(params)
        for key in ("ak", "sn"):
            if key in redacted:
                redacted[key] = "***"
        return redacted

    def mock_result(self) -> ProviderResult:
        """Return a placeholder result for skeleton-level tests."""
        return ProviderResult(status=ProviderStatus.UNKNOWN_ERROR, provider=self.name, message="TODO")


def _extract_error_token(text: str, key: str) -> str:
    """Extract a simple numeric error token from non-JSON error text."""
    if not text:
        return ""
    pattern = rf"['\"]?{re.escape(key)}['\"]?\s*[:=]\s*['\"]?(?P<value>\d+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return ""
    return match.group("value")
