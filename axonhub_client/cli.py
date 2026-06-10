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
from .discovery import discover_supported_models, normalize_channel_type
from .exceptions import AxonHubClientError, ConfigurationError, SESSION_RELOGIN_MESSAGE, is_auth_error
from .cli_helpers import *
from .cli_handlers import *
from .cli_session_output import *


SESSION_FILENAME = "session.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        if _is_no_client_command(args):
            result = args.handler(None, args)
        else:
            client = _make_client(args)
            result = args.handler(client, args)
        print_result(result, as_json=args.json, redact=not getattr(args, "sensitive_output", False))
        return 0
    except AxonHubClientError as exc:
        message = SESSION_RELOGIN_MESSAGE if not _is_no_client_command(args) and is_auth_error(exc) else str(exc)
        print(f"错误：{message}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axonhubclient", description="AxonHub Admin API 管理客户端")
    parser.add_argument(
        "--context-project-id",
        dest="context_project_id",
        help="可选的 X-Project-ID 请求上下文",
    )
    parser.add_argument("--timeout", type=float, default=30, help="请求超时时间，单位秒")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整响应")

    subparsers = parser.add_subparsers(dest="resource")
    _add_auth_commands(subparsers)
    _add_channel_commands(subparsers)
    _add_api_key_commands(subparsers)
    _add_model_commands(subparsers)
    _add_request_commands(subparsers)
    _add_usage_commands(subparsers)
    _add_trace_commands(subparsers)
    _add_diagnostics_commands(subparsers)
    _add_inventory_commands(subparsers)
    _add_smoke_commands(subparsers)
    return parser


def _add_auth_commands(subparsers: argparse._SubParsersAction) -> None:
    auth = subparsers.add_parser("auth", help="认证与系统状态")
    actions = auth.add_subparsers(dest="action", required=True)
    actions.add_parser("status", help="读取 /admin/system/status").set_defaults(
        handler=lambda client, _args: client.auth.status()
    )
    login = actions.add_parser("login", help="通过账号密码登录并保存 session")
    login.add_argument("--url", help="AxonHub 实例地址；缺省时交互输入")
    login.add_argument("--username", help="管理员用户名；当前会映射到 AxonHub 登录接口的 email 字段")
    login.add_argument("--password", help="管理员密码；缺省时隐藏输入")
    login.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")
    login.set_defaults(handler=_handle_login)
    actions.add_parser("whoami", help="读取当前 admin token 对应用户").set_defaults(
        handler=lambda client, _args: client.auth.whoami()
    )
    actions.add_parser("logout", help="清除当前用户默认 session").set_defaults(handler=_handle_logout)


def _add_confirm_flag(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--confirm", action="store_true", help="确认提交真实 mutation；未传时只做 dry-run")


def _dry_run(operation: str, effect: str, variables: dict[str, Any]) -> dict[str, Any]:
    return {
        "dryRun": True,
        "operation": operation,
        "effect": effect,
        "variables": variables,
    }


def _add_channel_commands(subparsers: argparse._SubParsersAction) -> None:
    channels = subparsers.add_parser("channels", help="渠道资产盘点与管理")
    actions = channels.add_subparsers(dest="action", required=True)

    list_cmd = actions.add_parser("list", help="分页读取渠道")
    list_cmd.add_argument("--first", type=int, default=100)
    list_cmd.add_argument("--after")
    list_cmd.add_argument("--status", action="append", dest="statuses", help="可重复传入，如 enabled")
    list_cmd.add_argument("--type", action="append", dest="types", help="可重复传入，如 openai")
    list_cmd.add_argument("--tag")
    list_cmd.add_argument("--model")
    list_cmd.set_defaults(
        handler=lambda client, args: client.channels.list(
            first=args.first,
            after=args.after,
            status_in=args.statuses,
            type_in=args.types,
            has_tag=args.tag,
            model=args.model,
        )
    )

    get_cmd = actions.add_parser("get", help="读取单个渠道")
    get_cmd.add_argument("id")
    get_cmd.set_defaults(handler=lambda client, args: client.channels.get(args.id))

    summary_cmd = actions.add_parser("summary", help="读取渠道摘要和模型入口")
    summary_cmd.add_argument("--include-archived", action="store_true")
    summary_cmd.set_defaults(
        handler=lambda client, args: client.channels.summary(include_archived=args.include_archived)
    )

    actions.add_parser("tags", help="读取全部渠道标签").set_defaults(
        handler=lambda client, _args: client.channels.tags()
    )

    count_cmd = actions.add_parser("count-by-type", help="按渠道 type 计数")
    count_cmd.add_argument("--status", action="append", dest="statuses")
    count_cmd.set_defaults(handler=lambda client, args: client.channels.count_by_type(status_in=args.statuses))

    create_cmd = actions.add_parser("create", help="创建渠道；默认只做 dry-run")
    create_cmd.add_argument("--type", required=True, help="渠道类型，如 openai、anthropic、gemini_openai")
    create_cmd.add_argument("--name", required=True, help="渠道名称")
    create_cmd.add_argument(
        "--upstream-base-url",
        "--channel-base-url",
        dest="channel_base_url",
        required=True,
        help="上游 API endpoint；AxonHub 实例地址来自用户配置目录中的 session",
    )
    create_cmd.add_argument(
        "--api-key",
        action="append",
        dest="api_keys",
        help="上游 API key；可重复，单次也可用逗号、换行或 JSON array 分隔多个 key",
    )
    create_cmd.add_argument(
        "--oauth-api-key",
        help="OAuth JSON 凭证字符串；用于 codex、claudecode、antigravity、github_copilot 等",
    )
    create_cmd.add_argument("--gcp-region", help="anthropic_gcp 等 GCP 凭证 region")
    create_cmd.add_argument("--gcp-project-id", help="anthropic_gcp 等 GCP 凭证 projectID")
    create_cmd.add_argument("--gcp-json", help="GCP service account JSON 字符串")
    create_cmd.add_argument(
        "--supported-model",
        action="append",
        dest="supported_models",
        help="支持模型；可重复，单次也可用逗号分隔；未提供时会尝试从 OpenAI/NewAPI 兼容 /models 自动获取",
    )
    create_cmd.add_argument("--manual-model", action="append", dest="manual_models", help="手动模型标记；仅显式传入时写入")
    create_cmd.add_argument("--default-test-model", help="默认测试模型；缺省为第一个 supported model")
    create_cmd.add_argument("--tag", action="append", dest="tags", help="渠道标签；可重复，单次也可用逗号分隔")
    create_cmd.add_argument("--auto-sync-supported-models", action="store_true", help="开启自动同步 supportedModels")
    create_cmd.add_argument("--auto-sync-model-pattern", default="", help="自动同步模型过滤正则")
    create_cmd.add_argument("--ordering-weight", type=int, help="排序权重")
    create_cmd.add_argument("--remark", help="备注")
    create_cmd.add_argument("--stream-policy", choices=["unlimited", "require", "forbid"], help="stream 能力策略")
    create_cmd.add_argument("--settings-json", help="ChannelSettingsInput JSON object")
    create_cmd.add_argument("--endpoints-json", help="ChannelEndpointInput 数组 JSON")
    _add_confirm_flag(create_cmd)
    create_cmd.set_defaults(handler=_handle_create_channel)

    bulk_create_cmd = actions.add_parser("create-many", help="按 API key 批量创建渠道；默认只做 dry-run")
    bulk_create_cmd.add_argument("input_file", nargs="?", help="包含 BulkCreateChannelsInput JSON object 的文件")
    bulk_create_cmd.add_argument("--input-json", help="BulkCreateChannelsInput JSON object")
    _add_confirm_flag(bulk_create_cmd)
    bulk_create_cmd.set_defaults(handler=_handle_bulk_create_channels)

    import_cmd = actions.add_parser("import", help="批量导入渠道；默认只做 dry-run")
    import_cmd.add_argument("input_file", nargs="?", help="包含渠道导入数据的 JSON 文件")
    import_cmd.add_argument("--input-json", help="渠道导入数据 JSON")
    _add_confirm_flag(import_cmd)
    import_cmd.set_defaults(handler=_handle_import_channels)

    update_cmd = actions.add_parser("update", help="更新渠道；接收完整 UpdateChannelInput JSON，默认只做 dry-run")
    update_cmd.add_argument("id", help="渠道 ID")
    input_group = update_cmd.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-json", help="UpdateChannelInput JSON object，如 '{\"orderingWeight\": 100}'")
    input_group.add_argument("--input-file", help="包含 UpdateChannelInput JSON object 的文件")
    _add_confirm_flag(update_cmd)
    update_cmd.set_defaults(handler=_handle_update_channel)

    status_cmd = actions.add_parser("status", help="更新渠道状态；默认只做 dry-run")
    status_cmd.add_argument("id", help="渠道 ID")
    status_cmd.add_argument("status", choices=["enabled", "disabled"], help="目标状态；归档和恢复请使用 archive/recover")
    _add_confirm_flag(status_cmd)
    status_cmd.set_defaults(handler=_handle_set_channel_status)

    bulk_ordering_cmd = actions.add_parser("reorder", help="批量更新渠道排序权重；默认只做 dry-run")
    bulk_ordering_cmd.add_argument("input_file", nargs="?", help="包含 BulkUpdateChannelOrderingInput JSON object 的文件")
    bulk_ordering_cmd.add_argument("--input-json", help="BulkUpdateChannelOrderingInput JSON object")
    _add_confirm_flag(bulk_ordering_cmd)
    bulk_ordering_cmd.set_defaults(handler=_handle_bulk_update_channel_ordering)

    disable_cmd = actions.add_parser("disable", help="批量禁用一个或多个渠道；默认只做 dry-run")
    disable_cmd.add_argument("ids", nargs="+", help="渠道 ID，可传多个")
    _add_confirm_flag(disable_cmd)
    disable_cmd.set_defaults(handler=_handle_disable_channels)

    enable_cmd = actions.add_parser("enable", help="批量启用一个或多个渠道；默认只做 dry-run")
    enable_cmd.add_argument("ids", nargs="+", help="渠道 ID，可传多个")
    _add_confirm_flag(enable_cmd)
    enable_cmd.set_defaults(handler=_handle_enable_channels)

    endpoints = actions.add_parser("endpoints", help="渠道 endpoint 管理")
    endpoint_actions = endpoints.add_subparsers(dest="endpoint_action", required=True)
    endpoints_set_cmd = endpoint_actions.add_parser("set", help="保存渠道 endpoints；默认只做 dry-run")
    endpoints_set_cmd.add_argument("id", help="渠道 ID")
    endpoints_input_group = endpoints_set_cmd.add_mutually_exclusive_group(required=True)
    endpoints_input_group.add_argument("--endpoints-json", help="ChannelEndpointInput JSON array")
    endpoints_input_group.add_argument("--endpoints-file", help="包含 ChannelEndpointInput JSON array 的文件")
    _add_confirm_flag(endpoints_set_cmd)
    endpoints_set_cmd.set_defaults(handler=_handle_save_channel_endpoints)

    test_cmd = actions.add_parser("test", help="测试渠道连通性；默认只做 dry-run")
    test_cmd.add_argument("id", help="渠道 ID")
    test_cmd.add_argument("--model", dest="model_id", help="测试模型；默认使用渠道 defaultTestModel")
    test_cmd.add_argument("--proxy-json", help="ProxyConfigInput JSON object")
    _add_confirm_flag(test_cmd)
    test_cmd.set_defaults(handler=_handle_test_channel)

    keys = actions.add_parser("keys", help="渠道内 API key 管理")
    key_actions = keys.add_subparsers(dest="key_action", required=True)
    api_keys_test_cmd = key_actions.add_parser("test", help="逐个测试渠道 API key；默认只做 dry-run")
    api_keys_test_cmd.add_argument("id", help="渠道 ID")
    api_keys_test_cmd.add_argument("--model", dest="model_id", help="测试模型；默认使用渠道 defaultTestModel")
    _add_confirm_flag(api_keys_test_cmd)
    api_keys_test_cmd.set_defaults(handler=_handle_test_channel_api_keys)

    disable_api_key_cmd = key_actions.add_parser("disable", help="禁用渠道内单个 API key；默认只做 dry-run")
    disable_api_key_cmd.add_argument("id", help="渠道 ID")
    disable_api_key_cmd.add_argument("--key", required=True, help="目标 API key")
    _add_confirm_flag(disable_api_key_cmd)
    disable_api_key_cmd.set_defaults(handler=_handle_disable_channel_api_key)

    enable_api_key_cmd = key_actions.add_parser("enable", help="启用渠道内单个 API key；默认只做 dry-run")
    enable_api_key_cmd.add_argument("id", help="渠道 ID")
    enable_api_key_cmd.add_argument("--key", required=True, help="目标 API key")
    _add_confirm_flag(enable_api_key_cmd)
    enable_api_key_cmd.set_defaults(handler=_handle_enable_channel_api_key)

    enable_all_api_keys_cmd = key_actions.add_parser("enable-all", help="启用渠道内全部 API key；默认只做 dry-run")
    enable_all_api_keys_cmd.add_argument("id", help="渠道 ID")
    _add_confirm_flag(enable_all_api_keys_cmd)
    enable_all_api_keys_cmd.set_defaults(handler=_handle_enable_all_channel_api_keys)

    enable_selected_api_keys_cmd = key_actions.add_parser("enable-selected", help="启用渠道内选中的 API key；默认只做 dry-run")
    enable_selected_api_keys_cmd.add_argument("id", help="渠道 ID")
    enable_selected_api_keys_cmd.add_argument(
        "--key",
        action="append",
        dest="keys",
        required=True,
        help="目标 API key；可重复，单次也可用逗号、换行或 JSON array 分隔多个 key",
    )
    _add_confirm_flag(enable_selected_api_keys_cmd)
    enable_selected_api_keys_cmd.set_defaults(handler=_handle_enable_selected_channel_api_keys)

    delete_disabled_api_keys_cmd = key_actions.add_parser(
        "prune-disabled",
        help="清理渠道 disabled API key 记录；默认只做 dry-run，高风险操作",
    )
    delete_disabled_api_keys_cmd.add_argument("id", help="渠道 ID")
    delete_disabled_api_keys_cmd.add_argument(
        "--key",
        action="append",
        dest="keys",
        required=True,
        help="目标 API key；可重复，单次也可用逗号、换行或 JSON array 分隔多个 key",
    )
    _add_confirm_flag(delete_disabled_api_keys_cmd)
    delete_disabled_api_keys_cmd.set_defaults(handler=_handle_delete_disabled_channel_api_keys)

    channel_models = actions.add_parser("models", help="渠道模型同步")
    channel_model_actions = channel_models.add_subparsers(dest="channel_model_action", required=True)
    sync_cmd = channel_model_actions.add_parser("sync", help="立即同步渠道 supportedModels；默认只做 dry-run")
    sync_cmd.add_argument("id", help="渠道 ID")
    sync_cmd.add_argument("--pattern", help="覆盖本次同步的模型过滤正则")
    _add_confirm_flag(sync_cmd)
    sync_cmd.set_defaults(handler=_handle_sync_channel_models)

    archive_cmd = actions.add_parser("archive", help="归档一个或多个渠道；默认只做 dry-run")
    archive_cmd.add_argument("ids", nargs="+", help="渠道 ID，可传多个")
    _add_confirm_flag(archive_cmd)
    archive_cmd.set_defaults(handler=_handle_archive_channels)

    recover_cmd = actions.add_parser("recover", help="恢复一个或多个归档渠道；默认只做 dry-run")
    recover_cmd.add_argument("ids", nargs="+", help="渠道 ID，可传多个")
    _add_confirm_flag(recover_cmd)
    recover_cmd.set_defaults(handler=_handle_recover_channels)

    delete_cmd = actions.add_parser("delete", help="删除一个或多个渠道；默认只做 dry-run，高风险操作")
    delete_cmd.add_argument("ids", nargs="+", help="渠道 ID，可传多个")
    _add_confirm_flag(delete_cmd)
    delete_cmd.set_defaults(handler=_handle_delete_channels)


def _add_api_key_commands(subparsers: argparse._SubParsersAction) -> None:
    api_keys = subparsers.add_parser("api-keys", help="API Key 和 Profile 只读盘点")
    actions = api_keys.add_subparsers(dest="action", required=True)

    list_cmd = actions.add_parser("list", help="分页读取 API Key 摘要；不会读取明文 key")
    list_cmd.add_argument("--first", type=int, default=100)
    list_cmd.add_argument("--after")
    list_cmd.add_argument("--status", choices=["enabled", "disabled", "archived"])
    list_cmd.add_argument("--type", dest="type_", choices=["user", "service_account", "noauth"])
    list_cmd.add_argument("--name", help="按名称模糊筛选")
    list_cmd.add_argument("--project-id", help="按项目 ID 筛选")
    list_cmd.add_argument("--user-id", help="按用户 ID 筛选")
    list_cmd.set_defaults(
        handler=lambda client, args: client.api_keys.list(
            first=args.first,
            after=args.after,
            status=args.status,
            type_=args.type_,
            name=args.name,
            project_id=args.project_id,
            user_id=args.user_id,
        )
    )

    get_cmd = actions.add_parser("get", help="读取单个 API Key 详情；不会读取明文 key")
    get_cmd.add_argument("id", help="API Key ID")
    get_cmd.set_defaults(handler=lambda client, args: client.api_keys.get(args.id))

    quota_cmd = actions.add_parser("quota", help="读取 API Key 各 Profile 的配额用量")
    quota_cmd.add_argument("id", help="API Key ID")
    quota_cmd.set_defaults(handler=lambda client, args: client.api_keys.quota_usage(args.id))

    templates_cmd = actions.add_parser("templates", help="读取 API Key Profile 模板")
    templates_cmd.add_argument("--first", type=int, default=100)
    templates_cmd.add_argument("--project-id", help="按项目 ID 筛选")
    templates_cmd.add_argument("--name", help="按名称模糊筛选")
    templates_cmd.set_defaults(
        handler=lambda client, args: client.api_keys.profile_templates(
            first=args.first,
            project_id=args.project_id,
            name=args.name,
        )
    )


def _add_model_commands(subparsers: argparse._SubParsersAction) -> None:
    models = subparsers.add_parser("models", help="模型资产盘点")
    actions = models.add_subparsers(dest="action", required=True)
    list_cmd = actions.add_parser("list", help="分页读取模型")
    list_cmd.add_argument("--first", type=int, default=100)
    list_cmd.add_argument("--after")
    list_cmd.add_argument("--status", action="append", dest="statuses")
    list_cmd.add_argument("--type", action="append", dest="types")
    list_cmd.add_argument("--model-id", help="按 modelID 精确筛选")
    list_cmd.add_argument("--name", help="按名称模糊筛选")
    list_cmd.set_defaults(
        handler=lambda client, args: client.models.list(
            first=args.first,
            after=args.after,
            status_in=args.statuses,
            model_id=args.model_id,
            name=args.name,
            type_in=args.types,
        )
    )

    get_cmd = actions.add_parser("get", help="读取单个模型")
    get_cmd.add_argument("id", help="模型实体 ID；使用 --model-id 时传 modelID")
    get_cmd.add_argument("--model-id", action="store_true", help="把 id 参数作为 modelID 查询")
    get_cmd.set_defaults(
        handler=lambda client, args: client.models.get_by_model_id(args.id) if args.model_id else client.models.get(args.id)
    )

    create_cmd = actions.add_parser("create", help="创建模型；默认只做 dry-run")
    create_input = create_cmd.add_mutually_exclusive_group(required=True)
    create_input.add_argument("--input-json", help="CreateModelInput JSON object")
    create_input.add_argument("--input-file", help="包含 CreateModelInput JSON object 的文件")
    _add_confirm_flag(create_cmd)
    create_cmd.set_defaults(handler=_handle_create_model)

    bulk_create_cmd = actions.add_parser("create-many", help="批量创建模型；默认只做 dry-run")
    bulk_create_input = bulk_create_cmd.add_mutually_exclusive_group(required=True)
    bulk_create_input.add_argument("--input-json", help="CreateModelInput JSON array，或 {\"models\": [...]}")
    bulk_create_input.add_argument("--input-file", help="包含批量模型输入的 JSON 文件")
    _add_confirm_flag(bulk_create_cmd)
    bulk_create_cmd.set_defaults(handler=_handle_bulk_create_models)

    update_cmd = actions.add_parser("update", help="更新模型；默认只做 dry-run")
    update_cmd.add_argument("id", help="模型实体 ID")
    update_input = update_cmd.add_mutually_exclusive_group(required=True)
    update_input.add_argument("--input-json", help="UpdateModelInput JSON object")
    update_input.add_argument("--input-file", help="包含 UpdateModelInput JSON object 的文件")
    _add_confirm_flag(update_cmd)
    update_cmd.set_defaults(handler=_handle_update_model)

    status_cmd = actions.add_parser("status", help="设置单个模型状态；默认只做 dry-run")
    status_cmd.add_argument("id", help="模型实体 ID")
    status_cmd.add_argument("status", choices=["enabled", "disabled", "archived"])
    _add_confirm_flag(status_cmd)
    status_cmd.set_defaults(handler=_handle_set_model_status)

    fastest_cmd = actions.add_parser("fastest", help="读取最快模型吞吐排行")
    fastest_cmd.add_argument("--window", choices=["day", "week", "month", "allTime"], default="day")
    fastest_cmd.add_argument("--limit", type=int, default=5)
    fastest_cmd.set_defaults(handler=lambda client, args: client.models.fastest(time_window=args.window, limit=args.limit))

    rules_cmd = actions.add_parser("rules", help="读取、预览或编辑模型关联规则")
    rule_actions = rules_cmd.add_subparsers(dest="rule_action", required=True)

    rules_list_cmd = rule_actions.add_parser("list", help="读取模型关联规则")
    rules_list_cmd.add_argument("id", help="模型实体 ID；使用 --model-id 时传 modelID")
    rules_list_cmd.add_argument("--model-id", action="store_true", help="把 id 参数作为 modelID 查询")
    rules_list_cmd.set_defaults(handler=_handle_model_rules_list)

    rules_preview_cmd = rule_actions.add_parser("preview", help="预览模型关联渠道")
    rules_preview_cmd.add_argument("id", nargs="?", help="模型实体 ID；使用 --model-id 时传 modelID")
    rules_preview_cmd.add_argument("--model-id", action="store_true", help="把 id 参数作为 modelID 查询")
    preview_input = rules_preview_cmd.add_mutually_exclusive_group()
    preview_input.add_argument("--associations-json", help="ModelAssociationInput JSON array；提供后不读取模型")
    preview_input.add_argument("--associations-file", help="包含 ModelAssociationInput JSON array 的文件；提供后不读取模型")
    rules_preview_cmd.set_defaults(handler=_handle_model_channels)

    rule_actions.add_parser("unassociated", help="检测渠道中未关联到模型配置的模型").set_defaults(
        handler=lambda client, _args: client.models.unassociated_channels()
    )

    rules_replace_cmd = rule_actions.add_parser("replace", help="整组替换模型关联规则；默认只做 dry-run")
    rules_replace_cmd.add_argument("id", help="模型实体 ID；使用 --model-id 时传 modelID")
    rules_replace_cmd.add_argument("--model-id", action="store_true", help="把 id 参数作为 modelID 查询")
    replace_input = rules_replace_cmd.add_mutually_exclusive_group(required=True)
    replace_input.add_argument("--associations-json", help="ModelAssociationInput JSON array")
    replace_input.add_argument("--associations-file", help="包含 ModelAssociationInput JSON array 的文件")
    _add_confirm_flag(rules_replace_cmd)
    rules_replace_cmd.set_defaults(handler=_handle_set_model_rules)

    for action_name, help_text in (
        ("add", "添加模型关联规则；默认只做 dry-run"),
        ("remove", "移除模型关联规则；默认只做 dry-run"),
        ("enable", "启用模型关联规则；默认只做 dry-run"),
        ("disable", "禁用模型关联规则；默认只做 dry-run"),
        ("reorder", "调整模型关联规则顺序；默认只做 dry-run"),
    ):
        rule_cmd = rule_actions.add_parser(action_name, help=help_text)
        rule_cmd.add_argument("id", help="模型实体 ID；使用 --model-id 时传 modelID")
        rule_cmd.add_argument("--model-id", action="store_true", help="把 id 参数作为 modelID 查询")
        if action_name == "add":
            rule_cmd.add_argument("--association-json", help="单条 ModelAssociationInput JSON object")
            rule_cmd.add_argument("--association-file", help="包含单条 ModelAssociationInput JSON object 的文件")
            rule_cmd.add_argument("--position", type=int, help="1-based 插入位置；默认追加")
        elif action_name == "reorder":
            rule_cmd.add_argument("--from-index", type=int, required=True, help="1-based 原位置")
            rule_cmd.add_argument("--to-index", type=int, required=True, help="1-based 目标位置")
        else:
            rule_cmd.add_argument("--index", type=int, required=True, help="1-based 规则索引")
        _add_confirm_flag(rule_cmd)
        rule_cmd.set_defaults(handler=_handle_model_rule_action, rule_action=action_name)

    enable_cmd = actions.add_parser("enable", help="启用一个或多个模型；默认只做 dry-run")
    enable_cmd.add_argument("ids", nargs="+", help="模型实体 ID，可传多个")
    _add_confirm_flag(enable_cmd)
    enable_cmd.set_defaults(handler=_handle_enable_models)

    disable_cmd = actions.add_parser("disable", help="禁用一个或多个模型；默认只做 dry-run")
    disable_cmd.add_argument("ids", nargs="+", help="模型实体 ID，可传多个")
    _add_confirm_flag(disable_cmd)
    disable_cmd.set_defaults(handler=_handle_disable_models)

    archive_cmd = actions.add_parser("archive", help="归档一个或多个模型；默认只做 dry-run")
    archive_cmd.add_argument("ids", nargs="+", help="模型实体 ID，可传多个")
    _add_confirm_flag(archive_cmd)
    archive_cmd.set_defaults(handler=_handle_archive_models)

    recover_cmd = actions.add_parser("recover", help="恢复一个或多个模型为 enabled；默认只做 dry-run")
    recover_cmd.add_argument("ids", nargs="+", help="模型实体 ID，可传多个")
    _add_confirm_flag(recover_cmd)
    recover_cmd.set_defaults(handler=_handle_recover_models)

    delete_cmd = actions.add_parser("delete", help="删除一个或多个模型；默认只做 dry-run，高风险操作")
    delete_cmd.add_argument("ids", nargs="+", help="模型实体 ID，可传多个")
    _add_confirm_flag(delete_cmd)
    delete_cmd.set_defaults(handler=_handle_delete_models)


def _add_usage_commands(subparsers: argparse._SubParsersAction) -> None:
    usage = subparsers.add_parser("usage", help="用量和 dashboard 统计")
    actions = usage.add_subparsers(dest="action", required=True)

    actions.add_parser("overview", help="读取 dashboardOverview").set_defaults(
        handler=lambda client, _args: client.usage.overview()
    )
    _add_time_window_command(actions, "requests-by-channel", lambda c, a: c.usage.requests_by_channel(time_window=a.window))
    _add_time_window_command(actions, "requests-by-model", lambda c, a: c.usage.requests_by_model(time_window=a.window))
    _add_time_window_command(actions, "tokens-by-channel", lambda c, a: c.usage.tokens_by_channel(time_window=a.window))
    _add_time_window_command(actions, "tokens-by-model", lambda c, a: c.usage.tokens_by_model(time_window=a.window))
    _add_time_window_command(actions, "cost-by-channel", lambda c, a: c.usage.cost_by_channel(time_window=a.window))
    _add_time_window_command(actions, "cost-by-model", lambda c, a: c.usage.cost_by_model(time_window=a.window))

    actions.add_parser("daily", help="读取 dailyRequestStats").set_defaults(
        handler=lambda client, _args: client.usage.daily()
    )
    actions.add_parser("token-stats", help="读取 tokenStats 聚合").set_defaults(
        handler=lambda client, _args: client.usage.token_stats()
    )
    success = actions.add_parser("channel-success-rates", help="读取渠道成功率")
    success.add_argument("--window", choices=["day", "week", "month", "allTime"])
    success.add_argument("--limit", type=int)
    success.set_defaults(
        handler=lambda client, args: client.usage.channel_success_rates(
            time_window=args.window,
            limit=args.limit,
        )
    )

    logs = actions.add_parser("logs", help="用量日志只读查询")
    log_actions = logs.add_subparsers(dest="usage_log_action", required=True)
    list_cmd = log_actions.add_parser("list", help="分页读取用量日志")
    _add_log_list_filters(list_cmd, include_status=False, include_trace=False)
    list_cmd.add_argument("--request-id")
    list_cmd.set_defaults(
        handler=lambda client, args: client.usage_logs.list(
            first=args.first,
            after=args.after,
            source_in=args.sources,
            channel_id=args.channel_id,
            project_id=args.project_id,
            request_id=args.request_id,
            model_id=args.model,
            created_after=args.created_after,
            created_before=args.created_before,
        )
    )

    get_cmd = log_actions.add_parser("get", help="读取单个用量日志")
    get_cmd.add_argument("id")
    get_cmd.set_defaults(handler=lambda client, args: client.usage_logs.get(args.id))


def _add_request_commands(subparsers: argparse._SubParsersAction) -> None:
    requests = subparsers.add_parser("requests", help="请求日志只读查询")
    actions = requests.add_subparsers(dest="action", required=True)

    list_cmd = actions.add_parser("list", help="分页读取请求日志摘要")
    _add_log_list_filters(list_cmd, include_status=True, include_trace=True)
    list_cmd.set_defaults(
        handler=lambda client, args: client.requests.list(
            first=args.first,
            after=args.after,
            status_in=args.statuses,
            source_in=args.sources,
            channel_id=args.channel_id,
            project_id=args.project_id,
            model_id=args.model,
            trace_id=args.trace_id,
            created_after=args.created_after,
            created_before=args.created_before,
        )
    )

    get_cmd = actions.add_parser("get", help="读取单个请求日志；默认不读取正文")
    get_cmd.add_argument("id")
    get_cmd.add_argument("--include-content", action="store_true", help="同时读取 headers、请求正文、响应正文和 chunks")
    get_cmd.set_defaults(handler=lambda client, args: client.requests.get(args.id, include_content=args.include_content))

    executions_cmd = actions.add_parser("executions", help="读取请求的上游执行记录摘要")
    executions_cmd.add_argument("id", help="请求 ID")
    executions_cmd.add_argument("--first", type=int, default=100)
    executions_cmd.add_argument("--after")
    executions_cmd.add_argument("--status", action="append", dest="statuses")
    executions_cmd.add_argument("--channel-id")
    executions_cmd.set_defaults(
        handler=lambda client, args: client.requests.executions(
            args.id,
            first=args.first,
            after=args.after,
            status_in=args.statuses,
            channel_id=args.channel_id,
        )
    )

def _add_trace_commands(subparsers: argparse._SubParsersAction) -> None:
    traces = subparsers.add_parser("traces", help="Trace 只读查询")
    actions = traces.add_subparsers(dest="action", required=True)

    list_cmd = actions.add_parser("list", help="分页读取 Trace")
    list_cmd.add_argument("--first", type=int, default=100)
    list_cmd.add_argument("--after")
    list_cmd.add_argument("--trace-id")
    list_cmd.add_argument("--thread-id")
    list_cmd.add_argument("--request-id")
    list_cmd.add_argument("--project-id")
    list_cmd.add_argument("--created-after", help="ISO/RFC3339 时间，映射到 createdAtGTE")
    list_cmd.add_argument("--created-before", help="ISO/RFC3339 时间，映射到 createdAtLTE")
    list_cmd.set_defaults(
        handler=lambda client, args: client.traces.list(
            first=args.first,
            after=args.after,
            trace_id=args.trace_id,
            thread_id=args.thread_id,
            request_id=args.request_id,
            project_id=args.project_id,
            created_after=args.created_after,
            created_before=args.created_before,
        )
    )

    get_cmd = actions.add_parser("get", help="读取单个 Trace 详情和 rawRootSegment")
    get_cmd.add_argument("id")
    get_cmd.set_defaults(handler=lambda client, args: client.traces.get(args.id))


def _add_diagnostics_commands(subparsers: argparse._SubParsersAction) -> None:
    diagnostics = subparsers.add_parser("diagnostics", help="运维排障诊断")
    actions = diagnostics.add_subparsers(dest="action", required=True)

    health = actions.add_parser("channel-health", help="聚合渠道健康、成功率和最近失败请求")
    health.add_argument("--channel-id")
    health.add_argument("--limit", type=int, default=50, help="未指定渠道时最多诊断多少个渠道")
    health.add_argument("--window", choices=["day", "week", "month", "allTime"], default="day")
    health.add_argument("--min-success-rate", type=float, default=0.95)
    health.add_argument("--recent-failures", type=int, default=5)
    health.set_defaults(
        handler=lambda client, args: client.diagnostics.channel_health(
            channel_id=args.channel_id,
            first=args.limit,
            time_window=args.window,
            min_success_rate=args.min_success_rate,
            recent_failures=args.recent_failures,
        )
    )


def _add_inventory_commands(subparsers: argparse._SubParsersAction) -> None:
    inventory = subparsers.add_parser("inventory", help="实例资产和异常状态汇总")
    actions = inventory.add_subparsers(dest="action", required=True)
    summary = actions.add_parser("summary", help="聚合渠道、模型、用量和异常状态")
    summary.add_argument("--channel-first", type=int, default=500, help="最多读取多少条渠道记录")
    summary.add_argument("--model-first", type=int, default=1000, help="最多读取多少条模型记录")
    summary.add_argument("--success-window", choices=["day", "week", "month", "allTime"], default="day")
    summary.add_argument("--success-limit", type=int, default=20, help="读取多少条渠道成功率记录")
    summary.add_argument("--min-success-rate", type=float, default=0.95, help="低于该成功率时归入关注项")
    summary.set_defaults(
        handler=lambda client, args: client.inventory.summary(
            channel_first=args.channel_first,
            model_first=args.model_first,
            success_window=args.success_window,
            success_limit=args.success_limit,
            min_success_rate=args.min_success_rate,
        )
    )


def _add_smoke_commands(subparsers: argparse._SubParsersAction) -> None:
    smoke = subparsers.add_parser("smoke", help="真实实例 smoke test 流程")
    actions = smoke.add_subparsers(dest="action", required=True)
    actions.add_parser("read-only", help="执行只读 smoke test，不提交任何 mutation").set_defaults(
        handler=lambda client, _args: client.smoke_test.run()
    )


def _add_log_list_filters(
    cmd: argparse.ArgumentParser,
    *,
    include_status: bool,
    include_trace: bool,
) -> None:
    cmd.add_argument("--first", type=int, default=100)
    cmd.add_argument("--after")
    if include_status:
        cmd.add_argument("--status", action="append", dest="statuses")
    else:
        cmd.set_defaults(statuses=None)
    cmd.add_argument("--source", action="append", dest="sources")
    cmd.add_argument("--channel-id")
    cmd.add_argument("--project-id")
    cmd.add_argument("--model")
    if include_trace:
        cmd.add_argument("--trace-id")
    else:
        cmd.set_defaults(trace_id=None)
    cmd.add_argument("--created-after", help="ISO/RFC3339 时间，映射到 createdAtGTE")
    cmd.add_argument("--created-before", help="ISO/RFC3339 时间，映射到 createdAtLTE")


def _add_time_window_command(
    actions: argparse._SubParsersAction,
    name: str,
    handler: Any,
) -> None:
    cmd = actions.add_parser(name)
    cmd.add_argument("--window", choices=["day", "week", "month", "allTime"])
    cmd.set_defaults(handler=handler)

