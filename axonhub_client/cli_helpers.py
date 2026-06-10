from __future__ import annotations

import argparse
import json
from typing import Any

from .discovery import discover_supported_models, normalize_channel_type
from .exceptions import ConfigurationError


__all__ = [
    'load_update_channel_input',
    'load_create_model_input',
    'load_bulk_create_models_input',
    'load_update_model_input',
    '_parse_model_rules_args',
    '_build_model_rule_operation',
    'load_model_rule_object_arg',
    '_required_positive_int',
    '_optional_positive_int',
    '_positive_int',
    'normalize_create_model_input',
    'normalize_update_model_input',
    'load_json_any_arg',
    '_normalize_model_field_aliases',
    '_require_non_empty_string',
    '_require_dict_field',
    '_validate_model_type',
    '_validate_model_status',
    '_dedupe_model_ids',
    'load_json_list_arg',
    'load_json_object_arg',
    'load_bulk_ordering_input',
    'normalize_bulk_create_input',
    'load_channels_import_payload',
    '_normalize_import_channel',
    '_dedupe_ids',
    'build_create_channel_input',
    '_discover_create_channel_supported_models',
    '_model_discovery_api_key',
    '_build_channel_credentials',
    '_has_channel_credentials',
    '_api_keys_from_values',
    '_single_api_key',
    '_require_api_keys',
    '_split_values',
    '_split_secret_values',
    '_json_arg',
    'MODEL_TYPE_VALUES',
    'MODEL_STATUS_VALUES',
    'MODEL_RULE_ACTIONS',
    'CREATE_MODEL_REQUIRED_FIELDS',
    'CREATE_MODEL_ALLOWED_FIELDS',
    'UPDATE_MODEL_ALLOWED_FIELDS',
    'MODEL_FIELD_ALIASES',
]

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

