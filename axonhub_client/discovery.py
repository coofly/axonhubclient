from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter

from .exceptions import ConfigurationError


CHANNEL_TYPE_ALIASES = {
    "newapi_channel_conn": "openai",
}

OPENAI_MODEL_DISCOVERY_TYPES = {
    "aihubmix",
    "atlascloud",
    "bailian",
    "burncloud",
    "cerebras",
    "deepinfra",
    "deepseek",
    "doubao",
    "fireworks",
    "gemini_openai",
    "github",
    "jina",
    "longcat",
    "minimax",
    "modelscope",
    "moonshot",
    "nanogpt",
    "nanogpt_responses",
    "openai",
    "openai_fake",
    "openai_responses",
    "openrouter",
    "opencode_go",
    "ppio",
    "qiniu",
    "siliconflow",
    "vercel",
    "volcengine",
    "xai",
    "xiaomi",
    "zai",
    "zhipu",
}


def normalize_channel_type(type_: str) -> str:
    value = type_.strip()
    return CHANNEL_TYPE_ALIASES.get(value, value)


def discover_supported_models(
    *,
    channel_type: str,
    base_url: str,
    api_key: str,
    timeout: float = 30,
    session: requests.Session | None = None,
) -> list[str]:
    """Discover models from an OpenAI-compatible /models endpoint."""
    normalized_type = normalize_channel_type(channel_type)
    if normalized_type not in OPENAI_MODEL_DISCOVERY_TYPES:
        raise ConfigurationError(
            f"未提供 --supported-model，且渠道类型 {normalized_type} 暂不支持自动获取 supportedModels；"
            "请手动提供 --supported-model。"
        )

    models_url = _models_url(base_url)
    client = session or _model_discovery_session()
    try:
        body = _get_models_with_requests(client, models_url, api_key, timeout)
    except requests.RequestException as exc:
        raise ConfigurationError(f"自动获取 supportedModels 失败：无法请求 {models_url}：{exc}") from exc

    models = _extract_model_ids(body)
    if not models:
        raise ConfigurationError("自动获取 supportedModels 失败：/models 响应中没有可用模型 ID。")
    return models


class _ModelDiscoveryTLSAdapter(HTTPAdapter):
    def __init__(self) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__()

    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        pool_kwargs["ssl_context"] = self._ssl_context
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def cert_verify(self, conn: Any, url: str, verify: bool, cert: Any) -> None:
        # The SSLContext already performs default certificate verification.
        # Letting requests mutate urllib3 connection attributes can make some
        # OpenSSL 3 handshakes fail even though urllib3 with this context works.
        return


def _model_discovery_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", _ModelDiscoveryTLSAdapter())
    return session


def _get_models_with_requests(
    client: requests.Session,
    models_url: str,
    api_key: str,
    timeout: float,
) -> Any:
    response = client.get(
        models_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout=timeout,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise ConfigurationError(f"自动获取 supportedModels 失败：{models_url} 未返回合法 JSON。") from exc

    if not response.ok:
        message = _response_error_message(body) or f"HTTP {response.status_code}"
        raise ConfigurationError(f"自动获取 supportedModels 失败：{message}")
    return body


def _models_url(base_url: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", "models")


def _extract_model_ids(body: Any) -> list[str]:
    items: Any
    if isinstance(body, dict):
        items = body.get("data", body.get("models"))
    else:
        items = body
    if not isinstance(items, list):
        return []

    model_ids: list[str] = []
    for item in items:
        if isinstance(item, str):
            model_ids.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            model_ids.append(item["id"])
    return list(dict.fromkeys(item.strip() for item in model_ids if item.strip()))


def _response_error_message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    message = body.get("message")
    if isinstance(message, str):
        return message
    return None
