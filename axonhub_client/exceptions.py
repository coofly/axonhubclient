from __future__ import annotations


class AxonHubClientError(Exception):
    """Base error raised by AxonHubClient."""


SESSION_RELOGIN_MESSAGE = "当前 session 已失效或权限不足，请重新运行 axonhubclient auth login。"


class ConfigurationError(AxonHubClientError):
    """Raised when required client configuration is missing."""


class HTTPError(AxonHubClientError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphQLError(AxonHubClientError):
    def __init__(
        self,
        message: str,
        *,
        errors: list[dict] | None = None,
        is_auth_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.errors = errors or []
        self.is_auth_error = is_auth_error


def is_auth_error(exc: BaseException) -> bool:
    if isinstance(exc, GraphQLError):
        return exc.is_auth_error
    if isinstance(exc, HTTPError):
        return exc.status_code in (401, 403)
    return False
