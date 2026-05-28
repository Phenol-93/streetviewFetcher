"""Provider abstraction tests."""

from typing import Any

import pytest

from cn_streetview_fetcher.config import AppConfig
from cn_streetview_fetcher.inputs import PointRecord
from cn_streetview_fetcher.providers import (
    BaiduProvider,
    MockHttpClient,
    MockHttpResponse,
    ProviderRequest,
    ProviderStatus,
    TencentProvider,
)
from cn_streetview_fetcher.tasks import build_tasks


class RaisingClient(MockHttpClient):
    """Mock client that simulates a network failure."""

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Raise instead of returning a response."""
        _ = (request, timeout)
        raise RuntimeError("mock connection failed")


class TencentNoPanoClient(MockHttpClient):
    """Mock Tencent client that returns no pano during getpano."""

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Return a no_pano response for getpano."""
        _ = timeout
        if request.purpose == "getpano":
            return MockHttpResponse(status_code=200, json_data={"status": 404, "message": "not found"})
        return super().get(request)


class CountingNetworkThenSuccessClient(MockHttpClient):
    """Mock client that fails once, then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Fail on the first call to exercise retry behavior."""
        _ = timeout
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary network failure")
        return super().get(request, timeout=timeout)


class ParamErrorClient(MockHttpClient):
    """Mock client that returns a parameter error response."""

    def __init__(self) -> None:
        self.calls = 0

    def get(self, request: ProviderRequest, timeout: float | None = None) -> MockHttpResponse:
        """Return a parameter error without raising."""
        _ = timeout
        self.calls += 1
        return MockHttpResponse(status_code=400, json_data={"status": 2, "message": "bad parameter"})


def _first_task(config: AppConfig) -> Any:
    """Build one task for provider tests."""
    return build_tasks(
        points=[
            PointRecord(
                point_id="p1",
                lng=116.397389,
                lat=39.908722,
                coord_sys="wgs84",
            )
        ],
        config=config,
    )[0]


def test_baidu_builds_location_request_and_redacts_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu provider supports location requests and redacts credentials."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    monkeypatch.setenv("BAIDU_MAP_SN", "baidu-sn")
    config = AppConfig(provider="baidu", baidu={"use_panoid": False})
    task = _first_task(config)
    provider = BaiduProvider(config.baidu, http_client=MockHttpClient())

    prepared = provider.prepare_point(task)
    request = provider.build_image_request(prepared)
    result = provider.fetch_image(task)

    assert "location" in request.params
    assert result.status == ProviderStatus.SUCCESS
    assert result.image_bytes == b"mock-image-bytes"
    assert "baidu-secret" not in repr(result.metadata)
    assert "baidu-secret" not in repr(result.debug_info)
    assert request.params["ak"] == "baidu-secret"
    assert provider.redact_sensitive_params(request.params)["ak"] == "***"


def test_baidu_supports_panoid_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu provider can build panoid-based requests."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu", baidu={"use_panoid": True})
    task = build_tasks(
        [
            PointRecord(
                point_id="p1",
                lng=116.397389,
                lat=39.908722,
                coord_sys="wgs84",
                panoid="baidu-pano",
            )
        ],
        config,
    )[0]
    provider = BaiduProvider(config.baidu)

    request = provider.build_image_request(provider.prepare_point(task))

    assert request.params["panoid"] == "baidu-pano"
    assert "location" not in request.params


def test_baidu_parse_image_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu image response returns success and image bytes."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu")
    provider = BaiduProvider(config.baidu, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"ak": "baidu-secret"}, purpose="image")
    response = MockHttpResponse(status_code=200, content=b"image", headers={"content-type": "image/jpeg"})

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.SUCCESS
    assert result.image_bytes == b"image"
    assert "baidu-secret" not in repr(result.debug_info)


def test_baidu_parse_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu non-image error response is parsed and redacted."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu")
    provider = BaiduProvider(config.baidu, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"ak": "baidu-secret"}, purpose="image")
    response = MockHttpResponse(
        status_code=200,
        json_data={"status": 2, "message": "invalid parameter"},
        headers={"content-type": "application/json"},
        text='{"status":2,"message":"invalid parameter"}',
    )

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.PARAM_ERROR
    assert result.message == "invalid parameter"
    assert result.debug_info["error_code"] == "2"
    assert "baidu-secret" not in repr(result.debug_info)


def test_baidu_parse_text_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu text error response exposes text and parsed error code."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu")
    provider = BaiduProvider(config.baidu, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"ak": "baidu-secret"}, purpose="image")
    response = MockHttpResponse(
        status_code=200,
        headers={"content-type": "text/plain"},
        text="status: 101, message: invalid ak",
    )

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.AUTH_ERROR
    assert result.debug_info["error_code"] == "101"
    assert "invalid ak" in result.debug_info["response_text"]
    assert "baidu-secret" not in repr(result.debug_info)


def test_baidu_parse_no_pano_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu no street-view response maps to no_pano."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu")
    provider = BaiduProvider(config.baidu, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"ak": "baidu-secret"}, purpose="image")
    response = MockHttpResponse(status_code=200, json_data={"status": 404, "message": "not found"})

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.NO_PANO
    assert result.message
    assert "baidu-secret" not in repr(result.debug_info)


def test_tencent_getpano_then_image_flow_redacts_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent provider uses getpano -> image and redacts detailed debug info."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    task = _first_task(config)
    provider = TencentProvider(config.tencent, http_client=MockHttpClient())

    result = provider.fetch_image(task)

    assert result.status == ProviderStatus.SUCCESS
    assert result.metadata["flow"] == "getpano->image"
    assert result.metadata["pano_id"] == "mock_tencent_pano"
    assert "tencent-secret" not in repr(result.metadata)
    assert "tencent-secret" not in repr(result.debug_info)
    assert result.debug_info["getpano"]["request"]["params"]["key"] == "***"


def test_tencent_no_pano_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent getpano no result maps to no_pano."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    task = _first_task(config)
    result = TencentProvider(config.tencent, http_client=TencentNoPanoClient()).fetch_image(task)

    assert result.status == ProviderStatus.NO_PANO
    assert result.message


def test_missing_keys_map_to_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing API keys return auth_error in mock fetch."""
    monkeypatch.delenv("BAIDU_MAP_AK", raising=False)
    monkeypatch.delenv("BAIDU_MAP_SN", raising=False)
    monkeypatch.delenv("TENCENT_MAP_KEY", raising=False)
    baidu_config = AppConfig(provider="baidu")
    tencent_config = AppConfig(provider="tencent")

    baidu_result = BaiduProvider(baidu_config.baidu).fetch_image(_first_task(baidu_config))
    tencent_result = TencentProvider(tencent_config.tencent, http_client=MockHttpClient()).fetch_image(_first_task(tencent_config))

    assert baidu_result.status == ProviderStatus.AUTH_ERROR
    assert tencent_result.status == ProviderStatus.AUTH_ERROR
    assert "__missing" not in repr(baidu_result.debug_info)
    assert "__missing" not in repr(tencent_result.debug_info)


def test_network_error_status_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider client exceptions are normalized as network_error."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu")
    result = BaiduProvider(config.baidu, http_client=RaisingClient()).fetch_image(_first_task(config))

    assert result.status == ProviderStatus.NETWORK_ERROR
    assert result.message == "Baidu network error."


def test_baidu_network_errors_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu network errors are retried."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu", baidu={"max_retries": 1})
    client = CountingNetworkThenSuccessClient()
    task = _first_task(config)

    result = BaiduProvider(config.baidu, http_client=client).fetch_image(task)

    assert result.status == ProviderStatus.SUCCESS
    assert client.calls == 2


def test_baidu_param_error_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baidu parameter errors are parsed without retrying."""
    monkeypatch.setenv("BAIDU_MAP_AK", "baidu-secret")
    config = AppConfig(provider="baidu", baidu={"max_retries": 3})
    client = ParamErrorClient()
    task = _first_task(config)

    result = BaiduProvider(config.baidu, http_client=client).fetch_image(task)

    assert result.status == ProviderStatus.PARAM_ERROR
    assert client.calls == 1


def test_tencent_parse_getpano_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent getpano success response extracts pano details."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    provider = TencentProvider(config.tencent, http_client=MockHttpClient())
    request = ProviderRequest(
        url=provider.getpano_endpoint,
        params={"key": "tencent-secret", "location": "39.9,116.3", "radius": 50, "output": "json"},
        purpose="getpano",
    )
    response = MockHttpResponse(
        status_code=200,
        json_data={
            "status": 0,
            "detail": {
                "id": "pano-123",
                "location": {"lat": 39.9, "lng": 116.3},
                "description": "A road",
            },
        },
    )

    result = provider.parse_pano_response(response, request)

    assert result.status == ProviderStatus.SUCCESS
    assert result.metadata["pano_id"] == "pano-123"
    assert result.metadata["pano_location"] == {"lat": 39.9, "lng": 116.3}
    assert result.metadata["description"] == "A road"
    assert "tencent-secret" not in repr(result.debug_info)


def test_tencent_parse_getpano_no_pano(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent getpano no result maps to no_pano."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    provider = TencentProvider(config.tencent, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.getpano_endpoint, params={"key": "tencent-secret"}, purpose="getpano")
    response = MockHttpResponse(status_code=200, json_data={"status": 404, "message": "not found"})

    result = provider.parse_pano_response(response, request)

    assert result.status == ProviderStatus.NO_PANO
    assert result.message
    assert "tencent-secret" not in repr(result.debug_info)


def test_tencent_parse_image_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent image response is accepted only when content is an image."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    provider = TencentProvider(config.tencent, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"key": "tencent-secret", "pano": "pano-123"}, purpose="image")
    response = MockHttpResponse(status_code=200, content=b"image", headers={"content-type": "image/jpeg"})

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.SUCCESS
    assert result.image_bytes == b"image"
    assert "tencent-secret" not in repr(result.debug_info)


def test_tencent_parse_image_non_image_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent image parser rejects non-image responses."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent")
    provider = TencentProvider(config.tencent, http_client=MockHttpClient())
    request = ProviderRequest(url=provider.image_endpoint, params={"key": "tencent-secret"}, purpose="image")
    response = MockHttpResponse(status_code=200, json_data={"status": 0}, headers={"content-type": "application/json"})

    result = provider.parse_response(response, request)

    assert result.status == ProviderStatus.UNKNOWN_ERROR
    assert "tencent-secret" not in repr(result.debug_info)


def test_tencent_network_errors_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent network errors are retried."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent", tencent={"max_retries": 1})
    client = CountingNetworkThenSuccessClient()
    task = _first_task(config)

    result = TencentProvider(config.tencent, http_client=client).fetch_image(task)

    assert result.status == ProviderStatus.SUCCESS
    assert client.calls >= 2


def test_tencent_param_error_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tencent parameter errors are parsed without retrying."""
    monkeypatch.setenv("TENCENT_MAP_KEY", "tencent-secret")
    config = AppConfig(provider="tencent", tencent={"max_retries": 3})
    client = ParamErrorClient()
    task = _first_task(config)

    result = TencentProvider(config.tencent, http_client=client).fetch_image(task)

    assert result.status == ProviderStatus.PARAM_ERROR
    assert client.calls == 1
