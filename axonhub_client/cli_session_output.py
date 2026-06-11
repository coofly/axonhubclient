from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import AxonHubClient
from .exceptions import ConfigurationError


SESSION_FILENAME = "session.json"
APP_DIR_NAME = "axonhub-client"


__all__ = [
    '_is_no_client_command',
    'user_config_dir',
    'session_path',
    'load_session',
    'save_session',
    '_handle_logout',
    '_make_client',
    '_prompt_login_value',
    '_handle_login',
    '_validate_login_field',
    '_validate_login_base_url',
    'print_result',
    'sanitize',
    'print_dict',
    'print_table',
    '_looks_like_connection',
    '_scalar_view',
    '_choose_columns',
    '_clip',
]

def _is_no_client_command(args: argparse.Namespace) -> bool:
    return getattr(args, "resource", None) == "auth" and getattr(args, "action", None) in {"login", "logout"}


def user_config_dir() -> Path:
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def session_path() -> Path:
    return user_config_dir() / SESSION_FILENAME


def load_session(path: Path | None = None) -> dict[str, Any]:
    path = path or session_path()
    if not path.exists():
        raise ConfigurationError(f"未找到 session 文件：{path}，请先运行 axonhub-client auth login。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"无法读取 session 文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"session 文件不是合法 JSON：{path}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"session 文件根节点必须是 JSON object：{path}")

    base_url = data.get("baseUrl")
    token = data.get("token")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ConfigurationError("session 文件缺少 baseUrl，请重新运行 axonhub-client auth login。")
    if not isinstance(token, str) or not token.strip():
        raise ConfigurationError("session 文件缺少 token，请重新运行 axonhub-client auth login。")
    _validate_login_base_url(base_url)
    return data


def save_session(session: dict[str, Any], path: Path | None = None) -> Path:
    path = path or session_path()
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        raise ConfigurationError(f"无法写入 session 文件：{path}") from exc
    return path


def _handle_logout(_client: AxonHubClient | None, _args: argparse.Namespace) -> dict[str, Any]:
    path = session_path()
    if not path.exists():
        return {"success": True, "message": "当前没有已保存的 session。", "sessionFile": str(path)}
    try:
        path.unlink()
    except OSError as exc:
        raise ConfigurationError(f"无法删除 session 文件：{path}") from exc
    return {"success": True, "message": "已清除当前 session。", "sessionFile": str(path)}


def _make_client(args: argparse.Namespace) -> AxonHubClient:
    session = load_session()
    return AxonHubClient.from_config(
        session["baseUrl"].strip(),
        admin_token=session["token"].strip(),
        timeout=args.timeout,
        project_id=args.project_id,
    )


def _prompt_login_value(value: str | None, label: str, *, secret: bool = False) -> str:
    if value is not None and value.strip():
        return value.strip()
    prompt = f"{label}: "
    return getpass.getpass(prompt) if secret else input(prompt).strip()


def _handle_login(_client: AxonHubClient | None, args: argparse.Namespace) -> dict[str, Any]:
    base_url = _prompt_login_value(args.url, "AxonHub URL")
    username = _prompt_login_value(args.username, "Username")
    password = _prompt_login_value(args.password, "Password", secret=True)
    _validate_login_base_url(base_url)
    _validate_login_field("username", username)
    _validate_login_field("password", password)

    client = AxonHubClient.from_config(base_url, timeout=args.timeout)
    response = client.auth.login(email=username, password=password)
    token = response.get("token")
    if not token:
        raise ConfigurationError("登录响应缺少 token 字段。")
    path = save_session(
        {
            "schemaVersion": 1,
            "baseUrl": base_url.rstrip("/"),
            "token": token,
            "user": response.get("user"),
            "savedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    return {
        "success": True,
        "message": "登录成功，已保存 session。",
        "sessionFile": str(path),
        "baseUrl": base_url.rstrip("/"),
        "user": response.get("user"),
    }


def _validate_login_field(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"缺少登录字段 {name}，请通过交互输入或命令行参数提供。")
    if value.startswith("REPLACE_WITH_") or value.startswith("<") and value.endswith(">"):
        raise ConfigurationError(f"登录字段 {name} 仍是占位符，请先替换为真实值。")


def _validate_login_base_url(value: Any) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        raise ConfigurationError("登录配置字段 baseUrl 必须是字符串。")
    if "example.com" in value:
        raise ConfigurationError("登录字段 baseUrl 仍是示例地址，请先替换为真实 AxonHub 地址。")


def print_result(result: Any, *, as_json: bool, redact: bool = True) -> None:
    if redact:
        result = sanitize(result)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if isinstance(result, dict):
        if _looks_like_connection(result):
            print_table([edge["node"] for edge in result.get("edges", [])])
            page_info = result.get("pageInfo") or {}
            print(f"totalCount: {result.get('totalCount', 0)}")
            if page_info.get("hasNextPage"):
                print(f"nextCursor: {page_info.get('endCursor')}")
            return
        print_dict(result)
        return

    if isinstance(result, list):
        print_table(result)
        return

    print(result)


def sanitize(value: Any) -> Any:
    sensitive_keys = {
        "apiKey",
        "apiKeys",
        "key",
        "keys",
        "token",
        "accessToken",
        "refreshToken",
        "password",
        "jsonData",
        "secretKey",
    }
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if key in sensitive_keys else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def print_dict(data: dict[str, Any]) -> None:
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            print(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"{key}: {value}")


def print_table(rows: Iterable[Any]) -> None:
    rows = list(rows)
    if not rows:
        print("无数据")
        return
    if not all(isinstance(row, dict) for row in rows):
        for row in rows:
            print(row)
        return

    scalar_rows = [_scalar_view(row) for row in rows]
    columns = _choose_columns(scalar_rows)
    widths = {
        column: min(
            max(len(column), *(len(str(row.get(column, ""))) for row in scalar_rows)),
            48,
        )
        for column in columns
    }
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in scalar_rows:
        print("  ".join(_clip(str(row.get(column, "")), widths[column]).ljust(widths[column]) for column in columns))


def _looks_like_connection(data: dict[str, Any]) -> bool:
    return "edges" in data and isinstance(data.get("edges"), list)


def _scalar_view(row: dict[str, Any]) -> dict[str, Any]:
    scalar = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            scalar[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            scalar[key] = ",".join(str(item) for item in value)
    return scalar


def _choose_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "id",
        "name",
        "modelID",
        "type",
        "status",
        "baseURL",
        "channelName",
        "modelId",
        "count",
        "cost",
        "successRate",
        "totalTokens",
    ]
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    ordered = [key for key in preferred if key in keys]
    ordered.extend(key for key in keys if key not in ordered)
    return ordered[:8]


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"
