from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests

from .exceptions import ConfigurationError, GraphQLError, HTTPError


_OPERATION_RE = re.compile(r"^\s*(query|mutation|subscription)\s+([A-Za-z_][A-Za-z0-9_]*)")


def extract_operation_name(query: str) -> str | None:
    match = _OPERATION_RE.match(query)
    if not match:
        return None
    return match.group(2)


class GraphQLTransport:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        endpoint: str = "/admin/graphql",
        session: requests.Session | None = None,
        timeout: float = 30,
        project_id: str | None = None,
    ) -> None:
        if not base_url:
            raise ConfigurationError("缺少 AxonHub base URL。")
        self.base_url = base_url.rstrip("/") + "/"
        self.endpoint = endpoint.lstrip("/")
        self.token = token
        self.timeout = timeout
        self.project_id = project_id
        self.session = session or requests.Session()

    @property
    def graphql_url(self) -> str:
        return urljoin(self.base_url, self.endpoint)

    def rest_url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.project_id:
            headers["X-Project-ID"] = self.project_id
        if extra:
            headers.update(extra)
        return headers

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "variables": variables or {},
            "operationName": operation_name or extract_operation_name(query),
        }
        try:
            response = self.session.post(
                self.graphql_url,
                json=payload,
                headers=self.headers(headers),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise HTTPError(f"GraphQL 请求失败：{exc}") from exc

        if response.status_code in (401, 403):
            raise GraphQLError("认证失败：Admin Token 无效或权限不足。", is_auth_error=True)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise HTTPError("服务端返回非 JSON 响应，请检查 base URL 和端点。", status_code=response.status_code)

        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPError("无法解析服务端 JSON 响应。", status_code=response.status_code) from exc

        if not response.ok:
            message = _first_graphql_error_message(body) or f"HTTP {response.status_code}"
            raise HTTPError(message, status_code=response.status_code)

        errors = body.get("errors")
        if errors:
            is_auth_error = any(_is_auth_error(error) for error in errors)
            message = _first_graphql_error_message(body) or "GraphQL 请求失败。"
            raise GraphQLError(message, errors=errors, is_auth_error=is_auth_error)

        data = body.get("data")
        if data is None:
            raise GraphQLError("GraphQL 响应缺少 data 字段。")
        return data

    def get_json(self, path: str) -> dict[str, Any]:
        try:
            response = self.session.get(
                self.rest_url(path),
                headers=self.headers({"Accept": "application/json"}),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise HTTPError(f"HTTP 请求失败：{exc}") from exc

        if response.status_code in (401, 403):
            raise HTTPError("认证失败：Admin Token 无效或权限不足。", status_code=response.status_code)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise HTTPError("服务端返回非 JSON 响应，请检查 base URL 和端点。", status_code=response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPError("无法解析服务端 JSON 响应。", status_code=response.status_code) from exc
        if not response.ok:
            raise HTTPError(f"HTTP {response.status_code}", status_code=response.status_code)
        if not isinstance(body, dict):
            raise HTTPError("服务端 JSON 响应不是对象。", status_code=response.status_code)
        return body

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(
                self.rest_url(path),
                json=payload,
                headers=self.headers({"Accept": "application/json"}),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise HTTPError(f"HTTP 请求失败：{exc}") from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise HTTPError("服务端返回非 JSON 响应，请检查 base URL 和端点。", status_code=response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPError("无法解析服务端 JSON 响应。", status_code=response.status_code) from exc
        if not response.ok:
            message = _rest_error_message(body) or f"HTTP {response.status_code}"
            raise HTTPError(message, status_code=response.status_code)
        if not isinstance(body, dict):
            raise HTTPError("服务端 JSON 响应不是对象。", status_code=response.status_code)
        return body


def _first_graphql_error_message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")
    if not errors:
        return None
    first = errors[0]
    if isinstance(first, dict):
        return first.get("message")
    return str(first)


def _is_auth_error(error: dict[str, Any]) -> bool:
    message = str(error.get("message", "")).lower()
    code = str(error.get("extensions", {}).get("code", "")).upper()
    return "unauthorized" in message or "unauthenticated" in message or code == "UNAUTHENTICATED"


def _rest_error_message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    message = body.get("message")
    if isinstance(message, str):
        return message
    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        nested = error.get("message")
        if isinstance(nested, str):
            return nested
    return None
