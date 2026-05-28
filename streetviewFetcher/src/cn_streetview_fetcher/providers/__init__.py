"""Street-view provider interfaces."""

from cn_streetview_fetcher.providers.baidu import BaiduProvider
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
from cn_streetview_fetcher.providers.tencent import TencentProvider

__all__ = [
    "BaiduProvider",
    "BaseStreetViewProvider",
    "HttpClient",
    "HttpxHttpClient",
    "MockHttpClient",
    "MockHttpResponse",
    "ProviderRequest",
    "ProviderResult",
    "ProviderStatus",
    "TencentProvider",
]
