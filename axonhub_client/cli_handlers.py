from __future__ import annotations

import argparse
from typing import Any

from .client import AxonHubClient
from .cli_helpers import *


def _dry_run(operation: str, effect: str, variables: dict[str, Any]) -> dict[str, Any]:
    return {
        "dryRun": True,
        "operation": operation,
        "effect": effect,
        "variables": variables,
    }


__all__ = [
    '_handle_model_channels',
    '_handle_create_model',
    '_handle_bulk_create_models',
    '_handle_update_model',
    '_handle_set_model_status',
    '_handle_model_rules_list',
    '_handle_model_rule_action',
    '_handle_set_model_rules',
    '_handle_archive_models',
    '_handle_disable_models',
    '_handle_enable_models',
    '_handle_recover_models',
    '_handle_delete_models',
    '_handle_create_channel',
    '_handle_bulk_create_channels',
    '_handle_import_channels',
    '_handle_update_channel',
    '_handle_bulk_update_channel_ordering',
    '_handle_set_channel_status',
    '_handle_disable_channels',
    '_handle_enable_channels',
    '_handle_save_channel_endpoints',
    '_handle_test_channel',
    '_handle_test_channel_api_keys',
    '_handle_disable_channel_api_key',
    '_handle_enable_channel_api_key',
    '_handle_enable_all_channel_api_keys',
    '_handle_enable_selected_channel_api_keys',
    '_handle_delete_disabled_channel_api_keys',
    '_handle_sync_channel_models',
    '_handle_archive_channels',
    '_handle_recover_channels',
    '_handle_delete_channels',
]

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


