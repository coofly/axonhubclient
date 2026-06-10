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


def _handle_model_channels(client: AxonHubClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.associations_json is not None or args.associations_file is not None:
        associations = load_json_list_arg(args.associations_json, args.associations_file, "associations")
        return client.models.channels(associations=associations)

    if not args.id:
        raise ConfigurationError("请提供模型 ID，或使用 --associations-json / --associations-file。")
    return client.models.channels(args.id, by_model_id=args.model_id)


def _handle_create_model(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = load_create_model_input(args.input_json, args.input_file)
    if not args.confirm:
        return _dry_run("CreateModel", "将创建 1 个模型；后端默认新模型状态为 disabled。", {"input": input_})
    return client.models.create(input_)


def _handle_bulk_create_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    inputs = load_bulk_create_models_input(args.input_json, args.input_file)
    if not args.confirm:
        return _dry_run(
            "BulkCreateModels",
            f"将批量创建 {len(inputs)} 个模型；后端默认新模型状态为 disabled。",
            {"inputs": inputs},
        )
    return {"models": client.models.bulk_create(inputs), "count": len(inputs)}


def _handle_update_model(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = load_update_model_input(args.input_json, args.input_file)
    variables = {"id": args.id, "input": input_}
    if not args.confirm:
        return _dry_run("UpdateModel", f"将使用 UpdateModelInput 更新模型 {args.id}。", variables)
    return client.models.update(args.id, input_)


def _handle_set_model_status(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    variables = {"id": args.id, "status": args.status}
    if not args.confirm:
        return _dry_run("UpdateModelStatus", f"将把模型 {args.id} 状态更新为 {args.status}。", variables)
    return {"success": client.models.set_status(args.id, args.status), **variables}


def _handle_model_rules_list(client: AxonHubClient, args: argparse.Namespace) -> Any:
    return client.models.rules(args.id, by_model_id=args.model_id)


def _handle_model_rule_action(client: AxonHubClient, args: argparse.Namespace) -> Any:
    action = args.rule_action
    operation = _build_model_rule_operation(action, args)
    variables = {
        "id": args.id,
        "byModelID": args.model_id,
        "ruleAction": action,
        **operation["variables"],
        "preserveExistingSettings": True,
        "normalizePriorities": True,
    }
    if not args.confirm:
        return _dry_run("UpdateModel", operation["effect"](args.id), variables)

    try:
        result = operation["apply"](client, args.id, args.model_id)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc
    if result is None:
        raise ConfigurationError("未找到指定模型，无法编辑关联规则。")
    return result


def _handle_set_model_rules(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    associations = load_json_list_arg(args.associations_json, args.associations_file, "associations")
    if not args.confirm:
        return _dry_run(
            "UpdateModel",
            f"将读取模型 {args.id} 的 settings 后，仅替换 settings.associations；其它 settings 字段保持不变。",
            {
                "id": args.id,
                "byModelID": args.model_id,
                "input": {"settings": {"associations": associations}},
                "preserveExistingSettings": True,
            },
        )
    result = client.models.set_rules(args.id, associations, by_model_id=args.model_id)
    if result is None:
        raise ConfigurationError("未找到指定模型，无法替换关联规则。")
    return result


def _handle_archive_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_model_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkArchiveModels", f"将归档 {len(ids)} 个模型。", variables)
    return {"success": client.models.archive(ids), "ids": ids}


def _handle_disable_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_model_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkDisableModels", f"将禁用 {len(ids)} 个模型。", variables)
    return {"success": client.models.disable(ids), "ids": ids}


def _handle_enable_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_model_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkEnableModels", f"将启用 {len(ids)} 个模型。", variables)
    return {"success": client.models.enable(ids), "ids": ids}


def _handle_recover_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_model_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkEnableModels", f"将恢复 {len(ids)} 个模型为 enabled。", variables)
    return {"success": client.models.recover(ids), "ids": ids}


def _handle_delete_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_model_ids(args.ids)
    variables = {"id": ids[0]} if len(ids) == 1 else {"ids": ids}
    if not args.confirm:
        effect = (
            f"将删除模型 {ids[0]}；这是不可逆高风险操作。"
            if len(ids) == 1
            else f"将删除 {len(ids)} 个模型；这是不可逆高风险操作。"
        )
        return _dry_run("DeleteModel" if len(ids) == 1 else "BulkDeleteModels", effect, variables)
    return {"success": client.models.delete(ids[0] if len(ids) == 1 else ids), "ids": ids}


def _handle_create_channel(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = build_create_channel_input(args)
    if not args.confirm:
        return _dry_run("CreateChannel", "将创建 1 个渠道；后端默认新渠道状态为 disabled。", {"input": input_})
    return client.channels.create(input_)


def _handle_bulk_create_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = normalize_bulk_create_input(load_json_object_arg(args.input_json, args.input_file, "create-many input"))
    if not args.confirm:
        return _dry_run(
            "BulkCreateChannels",
            f"将使用 1 份配置和 {len(input_.get('apiKeys', []))} 个 API key 创建渠道。",
            {"input": input_},
        )
    return client.channels.bulk_create(input_)


def _handle_import_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = load_channels_import_payload(args.input_json, args.input_file)
    if not args.confirm:
        return _dry_run("BulkImportChannels", f"将导入 {len(input_['channels'])} 条渠道记录。", {"input": input_})
    return client.channels.bulk_import(input_)


def _handle_update_channel(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = load_update_channel_input(args)
    variables = {"id": args.id, "input": input_}
    if not args.confirm:
        return _dry_run("UpdateChannel", f"将使用 UpdateChannelInput 更新渠道 {args.id}。", variables)
    return client.channels.update(args.id, input_)


def _handle_bulk_update_channel_ordering(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    input_ = load_bulk_ordering_input(args.input_json, args.input_file)
    if not args.confirm:
        return _dry_run(
            "BulkUpdateChannelOrdering",
            f"将更新 {len(input_.get('channels', []))} 个渠道的排序权重。",
            {"input": input_},
        )
    return client.channels.bulk_update_ordering(input_)


def _handle_set_channel_status(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    variables = {"id": args.id, "status": args.status}
    if not args.confirm:
        return _dry_run("UpdateChannelStatus", f"将把渠道 {args.id} 状态更新为 {args.status}。", variables)
    return client.channels.set_status(args.id, args.status)


def _handle_disable_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkDisableChannels", f"将禁用 {len(ids)} 个渠道。", variables)
    return {"success": client.channels.disable(ids), "ids": ids}


def _handle_enable_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkEnableChannels", f"将启用 {len(ids)} 个渠道。", variables)
    return {"success": client.channels.enable(ids), "ids": ids}


def _handle_save_channel_endpoints(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    endpoints = load_json_list_arg(args.endpoints_json, args.endpoints_file, "endpoints")
    variables = {"input": {"channelID": args.id, "endpoints": endpoints}}
    if not args.confirm:
        return _dry_run("SaveChannelEndpoints", f"将替换渠道 {args.id} 的 endpoints；空数组表示恢复使用默认 endpoints。", variables)
    return client.channels.save_endpoints(args.id, endpoints)


def _handle_test_channel(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    proxy = None
    if args.proxy_json:
        proxy = _json_arg(args.proxy_json, "proxy-json")
        if not isinstance(proxy, dict):
            raise ConfigurationError("--proxy-json 必须是 JSON object。")
    variables = {"input": {"channelID": args.id}}
    if args.model_id:
        variables["input"]["modelID"] = args.model_id
    if proxy:
        variables["input"]["proxy"] = proxy
    if not args.confirm:
        return _dry_run("TestChannel", f"将测试渠道 {args.id}；执行后会真实请求上游接口，可能消耗额度。", variables)
    return client.channels.test(args.id, model_id=args.model_id, proxy=proxy)


def _handle_test_channel_api_keys(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    variables = {"channelID": args.id, "modelID": args.model_id}
    if not args.confirm:
        return _dry_run("TestChannelAPIKeys", f"将逐个测试渠道 {args.id} 的 API key；执行后会真实请求上游接口，可能消耗额度。", variables)
    return client.channels.test_api_keys(args.id, model_id=args.model_id)


def _handle_disable_channel_api_key(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    key = _single_api_key(args.key, "key")
    variables = {"channelID": args.id, "key": key}
    if not args.confirm:
        return _dry_run("DisableChannelAPIKey", f"将禁用渠道 {args.id} 内 1 个 API key。", variables)
    return {"success": client.channels.disable_api_key(args.id, key), "channelID": args.id}


def _handle_enable_channel_api_key(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    key = _single_api_key(args.key, "key")
    variables = {"channelID": args.id, "key": key}
    if not args.confirm:
        return _dry_run("EnableChannelAPIKey", f"将启用渠道 {args.id} 内 1 个 API key。", variables)
    return {"success": client.channels.enable_api_key(args.id, key), "channelID": args.id}


def _handle_enable_all_channel_api_keys(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    variables = {"channelID": args.id}
    if not args.confirm:
        return _dry_run("EnableAllChannelAPIKeys", f"将启用渠道 {args.id} 内全部 API key。", variables)
    return {"success": client.channels.enable_all_api_keys(args.id), "channelID": args.id}


def _handle_enable_selected_channel_api_keys(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    keys = _api_keys_from_values(args.keys)
    _require_api_keys(keys)
    variables = {"channelID": args.id, "keys": keys}
    if not args.confirm:
        return _dry_run("EnableSelectedChannelAPIKeys", f"将启用渠道 {args.id} 内 {len(keys)} 个选中 API key。", variables)
    return {"success": client.channels.enable_selected_api_keys(args.id, keys), "channelID": args.id, "keyCount": len(keys)}


def _handle_delete_disabled_channel_api_keys(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    keys = _api_keys_from_values(args.keys)
    _require_api_keys(keys)
    variables = {"channelID": args.id, "keys": keys}
    if not args.confirm:
        return _dry_run(
            "DeleteDisabledChannelAPIKeys",
            f"将清理渠道 {args.id} 内 {len(keys)} 条 disabled API key 记录；这是高风险操作。",
            variables,
        )
    result = client.channels.delete_disabled_api_keys(args.id, keys)
    return {"channelID": args.id, "keyCount": len(keys), **result}


def _handle_sync_channel_models(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    variables = {"channelID": args.id, "pattern": args.pattern}
    if not args.confirm:
        return _dry_run("SyncChannelModels", f"将立即同步渠道 {args.id} 的 supportedModels。", variables)
    return client.channels.sync_models(args.id, pattern=args.pattern)


def _handle_archive_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkArchiveChannels", f"将归档 {len(ids)} 个渠道。", variables)
    return {"success": client.channels.archive(ids), "ids": ids}


def _handle_recover_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_ids(args.ids)
    variables = {"ids": ids}
    if not args.confirm:
        return _dry_run("BulkRecoverChannels", f"将恢复 {len(ids)} 个归档渠道。", variables)
    return {"success": client.channels.recover(ids), "ids": ids}


def _handle_delete_channels(client: AxonHubClient, args: argparse.Namespace) -> dict[str, Any]:
    ids = _dedupe_ids(args.ids)
    variables = {"id": ids[0]} if len(ids) == 1 else {"ids": ids}
    if not args.confirm:
        effect = (
            f"将删除渠道 {ids[0]}；这是不可逆高风险操作。"
            if len(ids) == 1
            else f"将删除 {len(ids)} 个渠道；这是不可逆高风险操作。"
        )
        return _dry_run("DeleteChannel" if len(ids) == 1 else "BulkDeleteChannels", effect, variables)
    return {"success": client.channels.delete(ids[0] if len(ids) == 1 else ids), "ids": ids}


def load_update_channel_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_json:
        input_ = _json_arg(args.input_json, "input-json")
    else:
        input_path = Path(args.input_file)
        try:
            input_ = json.loads(input_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"无法读取 update input 文件：{input_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"update input 文件不是合法 JSON：{input_path}") from exc
    if not isinstance(input_, dict):
        raise ConfigurationError("UpdateChannelInput 必须是 JSON object。")
    if not input_:
        raise ConfigurationError("UpdateChannelInput 不能为空。")
    return input_


MODEL_TYPE_VALUES = {"chat", "embedding", "rerank", "image_generation", "video_generation"}
MODEL_STATUS_VALUES = {"enabled", "disabled", "archived"}
MODEL_RULE_ACTIONS = {"list", "add", "remove", "enable", "disable", "reorder"}
CREATE_MODEL_REQUIRED_FIELDS = {"developer", "modelID", "name", "icon", "group", "modelCard", "settings"}
CREATE_MODEL_ALLOWED_FIELDS = CREATE_MODEL_REQUIRED_FIELDS | {"type", "remark"}
UPDATE_MODEL_ALLOWED_FIELDS = {
    "developer",
    "modelID",
    "type",
    "name",
    "icon",
    "group",
    "modelCard",
    "settings",
    "status",
    "clearRemark",
    "remark",
}
MODEL_FIELD_ALIASES = {
    "model_id": "modelID",
    "model_card": "modelCard",
    "clear_remark": "clearRemark",
}


def load_create_model_input(value: str | None, path: str | None) -> dict[str, Any]:
    payload = load_json_object_arg(value, path, "CreateModelInput")
    return normalize_create_model_input(payload)


def load_bulk_create_models_input(value: str | None, path: str | None) -> list[dict[str, Any]]:
    parsed = load_json_any_arg(value, path, "create-many models")
    if isinstance(parsed, dict):
        models = parsed.get("models")
    elif isinstance(parsed, list):
        models = parsed
    else:
        models = None

    if not isinstance(models, list):
        raise ConfigurationError("create-many models 必须是 JSON array，或包含 models 的 JSON object。")
    if not models:
        raise ConfigurationError("create-many models 不能为空。")
    if not all(isinstance(item, dict) for item in models):
        raise ConfigurationError("create-many models 中的每个模型都必须是 JSON object。")
    return [normalize_create_model_input(item) for item in models]


def load_update_model_input(value: str | None, path: str | None) -> dict[str, Any]:
    payload = load_json_object_arg(value, path, "UpdateModelInput")
    return normalize_update_model_input(payload)


def _parse_model_rules_args(rule_args: list[str]) -> tuple[str, str]:
    if len(rule_args) == 1:
        return "list", rule_args[0]
    if len(rule_args) == 2 and rule_args[0] in MODEL_RULE_ACTIONS:
        return rule_args[0], rule_args[1]
    if rule_args[0] not in MODEL_RULE_ACTIONS:
        raise ConfigurationError("models rules 支持 <id>，或 list/add/remove/enable/disable/reorder <id>。")
    raise ConfigurationError(f"models rules {rule_args[0]} 需要提供模型 ID。")


def _build_model_rule_operation(action: str, args: argparse.Namespace) -> dict[str, Any]:
    if action == "add":
        association = load_model_rule_object_arg(args.association_json, args.association_file)
        position = _optional_positive_int(args.position, "--position")
        return {
            "variables": {"association": association, "position": position},
            "effect": lambda model_id: f"将向模型 {model_id} 的关联规则中添加 1 条规则。",
            "apply": lambda client, model_id, by_model_id: client.models.add_rule(
                model_id,
                association,
                by_model_id=by_model_id,
                position=position,
            ),
        }
    if action == "remove":
        index = _required_positive_int(args.index, "--index")
        return {
            "variables": {"index": index},
            "effect": lambda model_id: f"将删除模型 {model_id} 的第 {index} 条关联规则。",
            "apply": lambda client, model_id, by_model_id: client.models.remove_rule(
                model_id,
                index,
                by_model_id=by_model_id,
            ),
        }
    if action in {"enable", "disable"}:
        index = _required_positive_int(args.index, "--index")
        disabled = action == "disable"
        verb = "禁用" if disabled else "启用"
        return {
            "variables": {"index": index, "disabled": disabled},
            "effect": lambda model_id: f"将{verb}模型 {model_id} 的第 {index} 条关联规则。",
            "apply": lambda client, model_id, by_model_id: client.models.set_rule_disabled(
                model_id,
                index,
                disabled,
                by_model_id=by_model_id,
            ),
        }
    if action == "reorder":
        from_index = _required_positive_int(args.from_index, "--from-index")
        to_index = _required_positive_int(args.to_index, "--to-index")
        return {
            "variables": {"fromIndex": from_index, "toIndex": to_index},
            "effect": lambda model_id: f"将模型 {model_id} 的第 {from_index} 条关联规则移动到第 {to_index} 位。",
            "apply": lambda client, model_id, by_model_id: client.models.reorder_rule(
                model_id,
                from_index,
                to_index,
                by_model_id=by_model_id,
            ),
        }
    raise ConfigurationError("models rules 支持 list/add/remove/enable/disable/reorder。")


def load_model_rule_object_arg(value: str | None, path: str | None) -> dict[str, Any]:
    if value is not None and path is not None:
        raise ConfigurationError("不能同时提供 --association-json 和 --association-file。")
    if value is None and path is None:
        raise ConfigurationError("rules add 需要提供 --association-json 或 --association-file。")
    association = load_json_object_arg(value, path, "association")
    if "type" not in association:
        raise ConfigurationError("ModelAssociationInput.type 不能为空。")
    return association


def _required_positive_int(value: int | None, name: str) -> int:
    if value is None:
        raise ConfigurationError(f"请提供 {name}。")
    return _positive_int(value, name)


def _optional_positive_int(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


def _positive_int(value: int, name: str) -> int:
    if value < 1:
        raise ConfigurationError(f"{name} 必须是大于等于 1 的整数。")
    return value


def normalize_create_model_input(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_model_field_aliases(payload)
    if "status" in normalized:
        raise ConfigurationError("CreateModelInput 不支持 status；请创建后使用 models status 或 models enable。")
    unknown = set(normalized) - CREATE_MODEL_ALLOWED_FIELDS
    if unknown:
        raise ConfigurationError(f"CreateModelInput 包含未知字段：{', '.join(sorted(unknown))}。")
    missing = CREATE_MODEL_REQUIRED_FIELDS - set(normalized)
    if missing:
        raise ConfigurationError(f"CreateModelInput 缺少必填字段：{', '.join(sorted(missing))}。")

    for field in ("developer", "modelID", "name", "icon", "group"):
        _require_non_empty_string(normalized, field, "CreateModelInput")
    if "type" in normalized:
        _validate_model_type(normalized["type"], "CreateModelInput.type")
    _require_dict_field(normalized, "modelCard", "CreateModelInput")
    _require_dict_field(normalized, "settings", "CreateModelInput")
    if "remark" in normalized and normalized["remark"] is not None and not isinstance(normalized["remark"], str):
        raise ConfigurationError("CreateModelInput.remark 必须是字符串或 null。")
    return normalized


def normalize_update_model_input(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_model_field_aliases(payload)
    unknown = set(normalized) - UPDATE_MODEL_ALLOWED_FIELDS
    if unknown:
        raise ConfigurationError(f"UpdateModelInput 包含未知字段：{', '.join(sorted(unknown))}。")
    if not normalized:
        raise ConfigurationError("UpdateModelInput 不能为空。")

    for field in ("developer", "modelID", "name", "icon", "group"):
        if field in normalized:
            _require_non_empty_string(normalized, field, "UpdateModelInput")
    if "type" in normalized:
        _validate_model_type(normalized["type"], "UpdateModelInput.type")
    if "status" in normalized:
        _validate_model_status(normalized["status"], "UpdateModelInput.status")
    if "modelCard" in normalized:
        _require_dict_field(normalized, "modelCard", "UpdateModelInput")
    if "settings" in normalized:
        _require_dict_field(normalized, "settings", "UpdateModelInput")
    if "clearRemark" in normalized and not isinstance(normalized["clearRemark"], bool):
        raise ConfigurationError("UpdateModelInput.clearRemark 必须是布尔值。")
    if "remark" in normalized and normalized["remark"] is not None and not isinstance(normalized["remark"], str):
        raise ConfigurationError("UpdateModelInput.remark 必须是字符串或 null。")
    return normalized


def load_json_any_arg(value: str | None, path: str | None, name: str) -> Any:
    if value is not None:
        return _json_arg(value, f"{name} input-json")
    if not path:
        raise ConfigurationError(f"请为 {name} 提供 --input-json 或输入文件。")
    input_path = Path(path)
    try:
        return json.loads(input_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"无法读取 {name} 文件：{input_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{name} 文件不是合法 JSON：{input_path}") from exc


def _normalize_model_field_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for source, target in MODEL_FIELD_ALIASES.items():
        if source in normalized:
            if target in normalized:
                raise ConfigurationError(f"不能同时提供 {source} 和 {target}。")
            normalized[target] = normalized.pop(source)
    return normalized


def _require_non_empty_string(payload: dict[str, Any], field: str, input_name: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{input_name}.{field} 必须是非空字符串。")
    payload[field] = value.strip()


def _require_dict_field(payload: dict[str, Any], field: str, input_name: str) -> None:
    if not isinstance(payload.get(field), dict):
        raise ConfigurationError(f"{input_name}.{field} 必须是 JSON object。")


def _validate_model_type(value: Any, field: str) -> None:
    if value not in MODEL_TYPE_VALUES:
        raise ConfigurationError(f"{field} 必须是以下值之一：{', '.join(sorted(MODEL_TYPE_VALUES))}。")


def _validate_model_status(value: Any, field: str) -> None:
    if value not in MODEL_STATUS_VALUES:
        raise ConfigurationError(f"{field} 必须是以下值之一：{', '.join(sorted(MODEL_STATUS_VALUES))}。")


def _dedupe_model_ids(ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys(item.strip() for item in ids if item.strip()))
    if not unique:
        raise ConfigurationError("至少需要提供一个模型 ID。")
    return unique


def load_json_list_arg(value: str | None, path: str | None, name: str) -> list[dict[str, Any]]:
    if value is not None:
        parsed = _json_arg(value, f"{name}-json")
    else:
        input_path = Path(path or "")
        try:
            parsed = json.loads(input_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"无法读取 {name} 文件：{input_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"{name} 文件不是合法 JSON：{input_path}") from exc
    if not isinstance(parsed, list):
        raise ConfigurationError(f"{name} 必须是 JSON array。")
    if not all(isinstance(item, dict) for item in parsed):
        raise ConfigurationError(f"{name} 数组元素必须是 JSON object。")
    return parsed


def load_json_object_arg(value: str | None, path: str | None, name: str) -> dict[str, Any]:
    if value is not None:
        parsed = _json_arg(value, f"{name}-json")
    else:
        if not path:
            raise ConfigurationError(f"请为 {name} 提供 --input-json 或输入文件。")
        input_path = Path(path)
        try:
            parsed = json.loads(input_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"无法读取 {name} 文件：{input_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"{name} 文件不是合法 JSON：{input_path}") from exc
    if not isinstance(parsed, dict):
        raise ConfigurationError(f"{name} 必须是 JSON object。")
    return parsed


def load_bulk_ordering_input(value: str | None, path: str | None) -> dict[str, Any]:
    if value is not None:
        parsed = _json_arg(value, "reorder input-json")
    else:
        if not path:
            raise ConfigurationError("请为 reorder input 提供 --input-json 或输入文件。")
        input_path = Path(path)
        try:
            parsed = json.loads(input_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"无法读取 reorder input 文件：{input_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"reorder input 文件不是合法 JSON：{input_path}") from exc

    if isinstance(parsed, list):
        channels = parsed
    elif isinstance(parsed, dict):
        channels = parsed.get("channels")
    else:
        channels = None

    if channels is None:
        raise ConfigurationError("reorder input 必须包含 channels。")
    if not isinstance(channels, list):
        raise ConfigurationError("reorder input 中的 channels 必须是 JSON array。")
    if not channels:
        raise ConfigurationError("reorder input 不能为空。")
    if not all(isinstance(item, dict) for item in channels):
        raise ConfigurationError("reorder input 中的每个渠道都必须是 JSON object。")
    normalized_channels = []
    for item in channels:
        normalized_channels.append(
            {
                "id": item.get("id"),
                "orderingWeight": item.get("orderingWeight", item.get("ordering_weight")),
            }
        )
    for item in normalized_channels:
        if not isinstance(item["id"], str) or not item["id"].strip():
            raise ConfigurationError("reorder input 中的 id 不能为空。")
        if not isinstance(item["orderingWeight"], int) or isinstance(item["orderingWeight"], bool):
            raise ConfigurationError("reorder input 中的 orderingWeight 必须是整数。")
    return {"channels": normalized_channels}


def normalize_bulk_create_input(payload: dict[str, Any]) -> dict[str, Any]:
    api_keys = payload.get("apiKeys", payload.get("api_keys"))
    if isinstance(api_keys, str):
        api_keys = [api_keys]
    if not isinstance(api_keys, list) or not all(isinstance(item, str) and item.strip() for item in api_keys):
        raise ConfigurationError("create-many input 中的 apiKeys / api_keys 必须是字符串数组。")
    if not api_keys:
        raise ConfigurationError("create-many input 中至少需要 1 个 apiKey。")

    supported_models = payload.get("supportedModels", payload.get("supported_models"))
    if not isinstance(supported_models, list) or not all(isinstance(item, str) and item.strip() for item in supported_models):
        raise ConfigurationError("create-many input 中的 supportedModels / supported_models 必须是字符串数组。")
    if not supported_models:
        raise ConfigurationError("create-many input 中至少需要 1 个 supportedModel。")

    default_test_model = payload.get("defaultTestModel", payload.get("default_test_model"))
    if not isinstance(default_test_model, str) or not default_test_model.strip():
        raise ConfigurationError("create-many input 中的 defaultTestModel / default_test_model 不能为空。")

    type_ = payload.get("type")
    name = payload.get("name")
    if not isinstance(type_, str) or not type_.strip():
        raise ConfigurationError("create-many input 中的 type 不能为空。")
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("create-many input 中的 name 不能为空。")

    normalized: dict[str, Any] = {
        "type": type_.strip(),
        "name": name.strip(),
        "apiKeys": [item.strip() for item in api_keys if item.strip()],
        "supportedModels": [item.strip() for item in supported_models if item.strip()],
        "defaultTestModel": default_test_model.strip(),
    }

    base_url = payload.get("baseURL", payload.get("base_url"))
    if base_url is not None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ConfigurationError("create-many input 中的 baseURL / base_url 不能为空。")
        normalized["baseURL"] = base_url.strip()

    tags = payload.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
            raise ConfigurationError("create-many input 中的 tags 必须是字符串数组。")
        normalized["tags"] = [item.strip() for item in tags if item.strip()]

    if payload.get("autoSyncSupportedModels") is not None:
        if not isinstance(payload["autoSyncSupportedModels"], bool):
            raise ConfigurationError("create-many input 中的 autoSyncSupportedModels 必须是布尔值。")
        normalized["autoSyncSupportedModels"] = payload["autoSyncSupportedModels"]
    if payload.get("auto_sync_supported_models") is not None:
        if not isinstance(payload["auto_sync_supported_models"], bool):
            raise ConfigurationError("create-many input 中的 auto_sync_supported_models 必须是布尔值。")
        normalized["autoSyncSupportedModels"] = payload["auto_sync_supported_models"]
    if payload.get("policies") is not None:
        normalized["policies"] = payload["policies"]
    if payload.get("settings") is not None:
        normalized["settings"] = payload["settings"]
    if payload.get("orderingWeight") is not None:
        if not isinstance(payload["orderingWeight"], int) or isinstance(payload["orderingWeight"], bool):
            raise ConfigurationError("create-many input 中的 orderingWeight 必须是整数。")
        normalized["orderingWeight"] = payload["orderingWeight"]
    if payload.get("ordering_weight") is not None:
        if not isinstance(payload["ordering_weight"], int) or isinstance(payload["ordering_weight"], bool):
            raise ConfigurationError("create-many input 中的 ordering_weight 必须是整数。")
        normalized["orderingWeight"] = payload["ordering_weight"]
    if payload.get("remark") is not None:
        normalized["remark"] = payload["remark"]

    return normalized


def load_channels_import_payload(value: str | None, path: str | None) -> dict[str, Any]:
    if value is not None:
        parsed = _json_arg(value, "input-json")
    else:
        if not path:
            raise ConfigurationError("请为渠道导入提供 --input-json 或输入文件。")
        input_path = Path(path)
        try:
            parsed = json.loads(input_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"无法读取渠道导入文件：{input_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"渠道导入文件不是合法 JSON：{input_path}") from exc

    if isinstance(parsed, dict) and "channels" in parsed:
        channels = parsed["channels"]
    elif isinstance(parsed, list):
        channels = parsed
    elif isinstance(parsed, dict):
        channels = [parsed]
    else:
        raise ConfigurationError("渠道导入数据必须是 JSON object 或 JSON array。")

    if not isinstance(channels, list):
        raise ConfigurationError("渠道导入数据中的 channels 必须是 JSON array。")
    if not channels:
        raise ConfigurationError("渠道导入数据不能为空。")
    if not all(isinstance(item, dict) for item in channels):
        raise ConfigurationError("渠道导入数据中的每个渠道都必须是 JSON object。")

    return {"channels": [_normalize_import_channel(item) for item in channels]}


def _normalize_import_channel(channel: dict[str, Any]) -> dict[str, Any]:
    api_key = channel.get("apiKey", channel.get("api_key"))
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigurationError("渠道导入数据中的 apiKey / api_key 不能为空。")

    base_url = channel.get("baseURL", channel.get("base_url"))
    if base_url is not None and (not isinstance(base_url, str) or not base_url.strip()):
        raise ConfigurationError("渠道导入数据中的 baseURL / base_url 不能为空。")

    supported_models = channel.get("supportedModels", channel.get("supported_models"))
    if not isinstance(supported_models, list) or not all(isinstance(item, str) and item.strip() for item in supported_models):
        raise ConfigurationError("渠道导入数据中的 supportedModels / supported_models 必须是字符串数组。")

    default_test_model = channel.get("defaultTestModel", channel.get("default_test_model"))
    if not isinstance(default_test_model, str) or not default_test_model.strip():
        raise ConfigurationError("渠道导入数据中的 defaultTestModel / default_test_model 不能为空。")

    normalized: dict[str, Any] = {
        "type": channel.get("type"),
        "name": channel.get("name"),
        "apiKey": api_key.strip(),
        "supportedModels": [item.strip() for item in supported_models],
        "defaultTestModel": default_test_model.strip(),
    }

    if not isinstance(normalized["type"], str) or not normalized["type"].strip():
        raise ConfigurationError("渠道导入数据中的 type 不能为空。")
    if not isinstance(normalized["name"], str) or not normalized["name"].strip():
        raise ConfigurationError("渠道导入数据中的 name 不能为空。")

    if base_url is not None:
        normalized["baseURL"] = base_url.strip()
    if channel.get("tags") is not None:
        if not isinstance(channel["tags"], list) or not all(isinstance(item, str) for item in channel["tags"]):
            raise ConfigurationError("渠道导入数据中的 tags 必须是字符串数组。")
        normalized["tags"] = [item.strip() for item in channel["tags"] if item.strip()]
    if channel.get("orderingWeight") is not None:
        normalized["orderingWeight"] = channel["orderingWeight"]
    if channel.get("ordering_weight") is not None:
        normalized["orderingWeight"] = channel["ordering_weight"]
    if channel.get("remark") is not None:
        normalized["remark"] = channel["remark"]
    if channel.get("autoSyncSupportedModels") is not None:
        normalized["autoSyncSupportedModels"] = channel["autoSyncSupportedModels"]
    if channel.get("auto_sync_supported_models") is not None:
        normalized["autoSyncSupportedModels"] = channel["auto_sync_supported_models"]
    if channel.get("autoSyncModelPattern") is not None:
        normalized["autoSyncModelPattern"] = channel["autoSyncModelPattern"]
    if channel.get("auto_sync_model_pattern") is not None:
        normalized["autoSyncModelPattern"] = channel["auto_sync_model_pattern"]

    return normalized


def _dedupe_ids(ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys(item.strip() for item in ids if item.strip()))
    if not unique:
        raise ConfigurationError("至少需要提供一个渠道 ID。")
    return unique


def build_create_channel_input(args: argparse.Namespace) -> dict[str, Any]:
    type_ = normalize_channel_type(args.type)
    supported_models = _split_values(args.supported_models)
    credentials = _build_channel_credentials(args)
    if not _has_channel_credentials(credentials) and type_ not in {"anthropic_aws", "anthropic_gcp"}:
        raise ConfigurationError("缺少上游凭证：请提供 --api-key、--oauth-api-key 或 GCP 凭证。")
    if not supported_models:
        supported_models = _discover_create_channel_supported_models(type_, args, credentials)

    input_: dict[str, Any] = {
        "type": type_,
        "baseURL": args.channel_base_url,
        "name": args.name,
        "credentials": credentials,
        "supportedModels": supported_models,
        "manualModels": _split_values(args.manual_models),
        "autoSyncSupportedModels": bool(args.auto_sync_supported_models),
        "autoSyncModelPattern": args.auto_sync_model_pattern or "",
        "tags": _split_values(args.tags),
        "defaultTestModel": args.default_test_model or supported_models[0],
    }
    if args.stream_policy:
        input_["policies"] = {"stream": args.stream_policy}
    if args.ordering_weight is not None:
        input_["orderingWeight"] = args.ordering_weight
    if args.remark:
        input_["remark"] = args.remark
    if args.settings_json:
        settings = _json_arg(args.settings_json, "settings-json")
        if not isinstance(settings, dict):
            raise ConfigurationError("--settings-json 必须是 JSON object。")
        input_["settings"] = settings
    if args.endpoints_json:
        endpoints = _json_arg(args.endpoints_json, "endpoints-json")
        if not isinstance(endpoints, list):
            raise ConfigurationError("--endpoints-json 必须是 JSON array。")
        input_["endpoints"] = endpoints
    return input_


def _discover_create_channel_supported_models(
    type_: str,
    args: argparse.Namespace,
    credentials: dict[str, Any],
) -> list[str]:
    api_key = _model_discovery_api_key(credentials)
    if not api_key:
        raise ConfigurationError("未提供 --supported-model，且缺少可用于自动获取 supportedModels 的上游 API key。")
    return discover_supported_models(
        channel_type=type_,
        base_url=args.channel_base_url,
        api_key=api_key,
        timeout=getattr(args, "timeout", 30),
    )


def _model_discovery_api_key(credentials: dict[str, Any]) -> str | None:
    api_keys = credentials.get("apiKeys")
    if isinstance(api_keys, list):
        for api_key in api_keys:
            if isinstance(api_key, str) and api_key.strip():
                return api_key.strip()

    api_key = credentials.get("apiKey")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def _build_channel_credentials(args: argparse.Namespace) -> dict[str, Any]:
    credentials: dict[str, Any] = {}

    api_keys = _api_keys_from_values(args.api_keys or [])
    if api_keys:
        credentials["apiKeys"] = api_keys

    if args.oauth_api_key:
        oauth_key = args.oauth_api_key.strip()
        if oauth_key:
            credentials["apiKey"] = oauth_key

    gcp_json = args.gcp_json.strip() if args.gcp_json else None
    if args.gcp_region or args.gcp_project_id or gcp_json:
        if not args.gcp_region or not args.gcp_project_id or not gcp_json:
            raise ConfigurationError("GCP 凭证需要同时提供 --gcp-region、--gcp-project-id 和 --gcp-json。")
        credentials["gcp"] = {
            "region": args.gcp_region,
            "projectID": args.gcp_project_id,
            "jsonData": gcp_json,
        }

    return credentials


def _has_channel_credentials(credentials: dict[str, Any]) -> bool:
    api_key = credentials.get("apiKey")
    api_keys = credentials.get("apiKeys")
    gcp = credentials.get("gcp")
    return bool(api_key or api_keys or gcp)


def _api_keys_from_values(values: list[str]) -> list[str]:
    keys: list[str] = []
    for value in values:
        keys.extend(_split_secret_values(value))
    return list(dict.fromkeys(keys))


def _single_api_key(value: str, name: str) -> str:
    keys = _api_keys_from_values([value])
    _require_api_keys(keys)
    if len(keys) != 1:
        raise ConfigurationError(f"--{name} 必须只包含一个 API key。")
    return keys[0]


def _require_api_keys(keys: list[str]) -> None:
    if not keys:
        raise ConfigurationError("至少需要提供一个 API key。")


def _split_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    items: list[str] = []
    for value in values:
        items.extend(part.strip() for part in value.split(","))
    return list(dict.fromkeys(item for item in items if item))


def _split_secret_values(value: str) -> list[str]:
    text = value.strip()
    if text.startswith("["):
        parsed = _json_arg(text, "api-key")
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ConfigurationError("API key JSON 值必须是字符串数组。")
        return [item.strip() for item in parsed if item.strip()]

    items: list[str] = []
    for line in text.splitlines():
        items.extend(part.strip() for part in line.split(","))
    return [item for item in items if item]


def _json_arg(value: str, name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"--{name} 不是合法 JSON。") from exc


def _is_no_client_command(args: argparse.Namespace) -> bool:
    return getattr(args, "resource", None) == "auth" and getattr(args, "action", None) in {"login", "logout"}


def user_config_dir() -> Path:
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "AxonhubClient"
        return Path.home() / "AppData" / "Roaming" / "AxonhubClient"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AxonhubClient"

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "axonhubclient"
    return Path.home() / ".config" / "axonhubclient"


def session_path() -> Path:
    return user_config_dir() / SESSION_FILENAME


def load_session(path: Path | None = None) -> dict[str, Any]:
    path = path or session_path()
    if not path.exists():
        raise ConfigurationError(f"未找到 session 文件：{path}，请先运行 axonhubclient auth login。")
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
        raise ConfigurationError("session 文件缺少 baseUrl，请重新运行 axonhubclient auth login。")
    if not isinstance(token, str) or not token.strip():
        raise ConfigurationError("session 文件缺少 token，请重新运行 axonhubclient auth login。")
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
        project_id=args.context_project_id,
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
