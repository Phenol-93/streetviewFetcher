"""Tencent official Street View provider mock implementation."""

from typing import Any

from cn_streetview_fetcher.config import TencentConfig
from cn_streetview_fetcher.providers.base import (
    BaseStreetViewProvider,
    HttpClient,
    HttpxHttpClient,
    MockHttpClient,
    MockHttpResponse,
    ProviderRequest,
    ProviderResult,
    ProviderStatus,
)


class TencentProvider(BaseStreetViewProvider):
    """Provider facade for Tencent official Street View APIs."""

    name = "tencent"
    getpano_endpoint = "https://apis.map.qq.com/ws/streetview/v1/getpano"
    image_endpoint = "https://apis.map.qq.com/ws/streetview/v1/image"

    def __init__(self, config: TencentConfig, http_client: HttpClient | None = None) -> None:
        super().__init__(http_client=http_client or HttpxHttpClient())
        self.config = config

    def validate_config(self) -> list[str]:
        """Validate Tencent provider configuration."""
        warnings = self.config.warnings()
        if self.config.api_key() is None:
            warnings.append(f"Tencent API key env var is not set: {self.config.key_env}")
        return warnings

    def prepare_point(self, task: Any) -> dict[str, Any]:
        """Prepare Tencent GCJ-02 location fields."""
        return {
            "task_id": task.task_id,
            "location": f"{task.request_lat},{task.request_lng}",
            "lat": task.request_lat,
            "lng": task.request_lng,
            "heading": task.heading,
            "pitch": task.pitch,
            "size": task.size or self.config.size,
            "radius": task.radius or self.config.radius,
            "panoid_input": task.panoid_input,
        }

    def build_pano_request(self, prepared: dict[str, Any]) -> ProviderRequest:
        """Build Tencent getpano request."""
        return ProviderRequest(
            url=self.getpano_endpoint,
            params={
                "key": self.config.api_key() or "__missing_tencent_key__",
                "location": prepared["location"],
                "lat": prepared["lat"],
                "lng": prepared["lng"],
                "radius": prepared["radius"],
                "output": "json",
            },
            purpose="getpano",
        )

    def build_image_request(self, prepared: dict[str, Any]) -> ProviderRequest:
        """Build Tencent street-view image request."""
        params = {
            "key": self.config.api_key() or "__missing_tencent_key__",
            "size": prepared["size"],
            "heading": prepared["heading"],
            "pitch": prepared["pitch"],
        }
        pano_id = prepared.get("pano_id") or prepared.get("panoid_input")
        if pano_id:
            params["pano"] = pano_id
        else:
            params["location"] = prepared["location"]
        return ProviderRequest(url=self.image_endpoint, params=params, purpose="image")

    def fetch_image(self, task: Any) -> ProviderResult:
        """Run Tencent mock getpano -> image flow."""
        prepared = self.prepare_point(task)
        pano_request = self.build_pano_request(prepared)
        if self.config.api_key() is None:
            return ProviderResult(
                status=ProviderStatus.AUTH_ERROR,
                provider=self.name,
                message="Tencent API key is not configured.",
                debug_info={
                    "request": {"url": pano_request.url, "params": self.redact_sensitive_params(pano_request.params)}
                },
            )
        try:
            pano_response = self._get_with_retries(pano_request)
        except Exception as exc:
            return ProviderResult(
                status=ProviderStatus.NETWORK_ERROR,
                provider=self.name,
                message="Tencent getpano network error.",
                debug_info={
                    "request": {"url": pano_request.url, "params": self.redact_sensitive_params(pano_request.params)},
                    "error": str(exc),
                },
            )
        pano_result = self.parse_pano_response(pano_response, pano_request)
        if pano_result.status != ProviderStatus.SUCCESS:
            pano_result.metadata.update({"task_id": task.task_id, "provider": self.name, "flow": "getpano"})
            return pano_result

        prepared["pano_id"] = pano_result.metadata.get("pano_id")
        image_request = self.build_image_request(prepared)
        try:
            image_response = self._get_with_retries(image_request)
        except Exception as exc:
            return ProviderResult(
                status=ProviderStatus.NETWORK_ERROR,
                provider=self.name,
                message="Tencent image network error.",
                debug_info={
                    "request": {"url": image_request.url, "params": self.redact_sensitive_params(image_request.params)},
                    "getpano": pano_result.debug_info,
                    "error": str(exc),
                },
            )
        result = self.parse_response(image_response, image_request)
        result.metadata.update(
            {
                "task_id": task.task_id,
                "provider": self.name,
                "flow": "getpano->image",
                "pano_id": prepared.get("pano_id"),
                "pano_metadata": pano_result.metadata,
            }
        )
        result.metadata.update(self.normalize_metadata(task, result))
        result.debug_info["getpano"] = pano_result.debug_info
        return result

    def parse_pano_response(self, response: MockHttpResponse, request: ProviderRequest) -> ProviderResult:
        """Parse Tencent getpano response."""
        debug_info = {
            "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)},
            "status_code": response.status_code,
            "content_type": response.content_type,
            "response": response.json(),
        }
        if response.status_code in {401, 403}:
            return ProviderResult(
                status=ProviderStatus.AUTH_ERROR,
                provider=self.name,
                message="Tencent authentication failed.",
                debug_info=debug_info,
            )
        if response.status_code >= 500:
            return ProviderResult(
                status=ProviderStatus.SERVER_ERROR,
                provider=self.name,
                message="Tencent getpano server error.",
                debug_info=debug_info,
            )
        payload = response.json()
        status = int(payload.get("status", -1))
        if status == 0:
            detail = payload.get("detail") or {}
            pano_id = detail.get("id") or detail.get("pano")
            if not pano_id:
                return ProviderResult(
                    status=ProviderStatus.NO_PANO,
                    provider=self.name,
                    message="Tencent returned no pano id.",
                    debug_info=debug_info,
                )
            return ProviderResult(
                status=ProviderStatus.SUCCESS,
                provider=self.name,
                metadata={
                    "pano_id": pano_id,
                    "pano_location": detail.get("location"),
                    "description": detail.get("description"),
                },
                message="Tencent mock pano found.",
                debug_info=debug_info,
            )
        if status in {110, 111, 112, 311}:
            normalized = ProviderStatus.AUTH_ERROR
            message = "Tencent authentication or quota error."
        elif status in {310, 348, 404}:
            normalized = ProviderStatus.NO_PANO
            message = "Tencent returned no panorama for this location."
        elif status in {2, 306, 347}:
            normalized = ProviderStatus.PARAM_ERROR
            message = "Tencent rejected getpano parameters."
        else:
            normalized = ProviderStatus.UNKNOWN_ERROR
            message = "Tencent returned an unknown getpano response."
        return ProviderResult(status=normalized, provider=self.name, message=message, debug_info=debug_info)

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

    def parse_response(self, response: MockHttpResponse, request: ProviderRequest) -> ProviderResult:
        """Parse Tencent image response."""
        debug_info = {
            "request": {"url": request.url, "params": self.redact_sensitive_params(request.params)},
            "status_code": response.status_code,
            "content_type": response.content_type,
        }
        if response.status_code in {401, 403}:
            return ProviderResult(
                status=ProviderStatus.AUTH_ERROR,
                provider=self.name,
                message="Tencent authentication failed.",
                debug_info=debug_info,
            )
        if response.status_code >= 500:
            return ProviderResult(
                status=ProviderStatus.SERVER_ERROR,
                provider=self.name,
                message="Tencent image server error.",
                debug_info=debug_info,
            )
        if response.status_code >= 400:
            return ProviderResult(
                status=ProviderStatus.PARAM_ERROR,
                provider=self.name,
                message="Tencent image request parameter error.",
                debug_info=debug_info,
            )
        if response.content_type.startswith("image/") and response.content:
            return ProviderResult(
                status=ProviderStatus.SUCCESS,
                provider=self.name,
                image_bytes=response.content,
                message="Tencent mock image fetched.",
                debug_info=debug_info,
            )
        debug_info["response"] = response.json()
        return ProviderResult(
            status=ProviderStatus.UNKNOWN_ERROR,
            provider=self.name,
            message="Tencent returned an unknown non-image response.",
            debug_info=debug_info,
        )

    def normalize_metadata(self, task: Any, result: ProviderResult) -> dict[str, Any]:
        """Normalize Tencent metadata for storage or UI."""
        prepared = self.prepare_point(task)
        if result.metadata.get("pano_id"):
            prepared["pano_id"] = result.metadata["pano_id"]
        pano_request = self.build_pano_request(prepared)
        image_request = self.build_image_request(prepared)
        return {
            "provider": self.name,
            "flow": "getpano->image",
            "requests": [
                {"url": pano_request.url, "params": self.redact_sensitive_params(pano_request.params)},
                {"url": image_request.url, "params": self.redact_sensitive_params(image_request.params)},
            ],
        }

    def redact_sensitive_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove Tencent credentials from request params."""
        redacted = dict(params)
        if "key" in redacted:
            redacted["key"] = "***"
        return redacted

    def mock_result(self) -> ProviderResult:
        """Return a placeholder result for skeleton-level tests."""
        return ProviderResult(status=ProviderStatus.UNKNOWN_ERROR, provider=self.name, message="TODO")
