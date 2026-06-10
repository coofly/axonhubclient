from __future__ import annotations

from typing import Any

from . import queries
from .transport import GraphQLTransport


class AuthAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def status(self) -> dict[str, Any]:
        return self.transport.get_json("/admin/system/status")

    def login(self, *, email: str, password: str) -> dict[str, Any]:
        return self.transport.post_json(
            "/admin/auth/signin",
            {"email": email, "password": password},
        )

    def whoami(self) -> dict[str, Any]:
        data = self.transport.execute(queries.ME_QUERY)
        return data["me"]


class APIKeysAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        status: str | None = None,
        type_: str | None = None,
        name: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {"first": first}
        where: dict[str, Any] = {}
        if after:
            variables["after"] = after
        if status:
            where["status"] = status
        if type_:
            where["type"] = type_
        else:
            where["typeNotIn"] = ["noauth"]
        if name:
            where["nameContainsFold"] = name
        if project_id:
            where["projectID"] = project_id
        if user_id:
            where["userID"] = user_id
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.API_KEYS, variables)
        return data["apiKeys"]

    def get(self, api_key_id: str) -> dict[str, Any] | None:
        data = self.transport.execute(queries.GET_API_KEY, {"id": api_key_id})
        return data.get("node")

    def quota_usage(self, api_key_id: str) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.API_KEY_QUOTA_USAGES, {"apiKeyId": api_key_id})
        return data["apiKeyQuotaUsages"]

    def profile_templates(
        self,
        *,
        first: int = 100,
        project_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {"first": first}
        where: dict[str, Any] = {}
        if project_id:
            where["projectID"] = project_id
        if name:
            where["nameContainsFold"] = name
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.API_KEY_PROFILE_TEMPLATES, variables)
        return data["apiKeyProfileTemplates"]


class ChannelsAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        status_in: list[str] | None = None,
        type_in: list[str] | None = None,
        has_tag: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        where: dict[str, Any] = {}
        if status_in:
            where["statusIn"] = status_in
        if type_in:
            where["typeIn"] = type_in
        input_: dict[str, Any] = {"first": first}
        if after:
            input_["after"] = after
        if where:
            input_["where"] = where
        if has_tag:
            input_["hasTag"] = has_tag
        if model:
            input_["model"] = model
        data = self.transport.execute(queries.QUERY_CHANNELS, {"input": input_})
        return data["queryChannels"]

    def get(self, channel_id: str) -> dict[str, Any] | None:
        data = self.transport.execute(queries.GET_CHANNEL, {"id": channel_id})
        return data.get("node")

    def summary(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.ALL_CHANNEL_SUMMARYS, {"includeArchived": include_archived})
        return data["allChannelSummarys"]

    def tags(self) -> list[str]:
        data = self.transport.execute(queries.ALL_CHANNEL_TAGS)
        return data["allChannelTags"]

    def count_by_type(self, *, status_in: list[str] | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(
            queries.COUNT_CHANNELS_BY_TYPE,
            {"input": {"statusIn": status_in} if status_in else {}},
        )
        return data["countChannelsByType"]

    def create(self, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(queries.CREATE_CHANNEL, {"input": input_})
        return data["createChannel"]

    def bulk_create(self, input_: dict[str, Any]) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.BULK_CREATE_CHANNELS, {"input": input_})
        return data["bulkCreateChannels"]

    def bulk_import(self, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(queries.BULK_IMPORT_CHANNELS, {"input": input_})
        return data["bulkImportChannels"]

    def update(self, channel_id: str, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(
            queries.UPDATE_CHANNEL,
            {"id": channel_id, "input": input_},
        )
        return data["updateChannel"]

    def set_status(self, channel_id: str, status: str) -> dict[str, Any]:
        data = self.transport.execute(
            queries.UPDATE_CHANNEL_STATUS,
            {"id": channel_id, "status": status},
        )
        return data["updateChannelStatus"]

    def save_endpoints(self, channel_id: str, endpoints: list[dict[str, Any]]) -> dict[str, Any]:
        data = self.transport.execute(
            queries.SAVE_CHANNEL_ENDPOINTS,
            {"input": {"channelID": channel_id, "endpoints": endpoints}},
        )
        return data["saveChannelEndpoints"]

    def bulk_update_ordering(self, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(queries.BULK_UPDATE_CHANNEL_ORDERING, {"input": input_})
        return data["bulkUpdateChannelOrdering"]

    def test(
        self,
        channel_id: str,
        *,
        model_id: str | None = None,
        proxy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_: dict[str, Any] = {"channelID": channel_id}
        if model_id:
            input_["modelID"] = model_id
        if proxy:
            input_["proxy"] = proxy
        data = self.transport.execute(queries.TEST_CHANNEL, {"input": input_})
        return data["testChannel"]

    def test_api_keys(self, channel_id: str, *, model_id: str | None = None) -> dict[str, Any]:
        data = self.transport.execute(
            queries.TEST_CHANNEL_API_KEYS,
            {"channelID": channel_id, "modelID": model_id},
        )
        return data["testChannelAPIKeys"]

    def sync_models(self, channel_id: str, *, pattern: str | None = None) -> dict[str, Any]:
        data = self.transport.execute(
            queries.SYNC_CHANNEL_MODELS,
            {"channelID": channel_id, "pattern": pattern},
        )
        return data["syncChannelModels"]

    def archive(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_ARCHIVE_CHANNELS, {"ids": ids})
        return data["bulkArchiveChannels"]

    def disable(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_DISABLE_CHANNELS, {"ids": ids})
        return data["bulkDisableChannels"]

    def enable(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_ENABLE_CHANNELS, {"ids": ids})
        return data["bulkEnableChannels"]

    def recover(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_RECOVER_CHANNELS, {"ids": ids})
        return data["bulkRecoverChannels"]

    def delete(self, channel_id_or_ids: str | list[str]) -> bool:
        if isinstance(channel_id_or_ids, str):
            data = self.transport.execute(queries.DELETE_CHANNEL, {"id": channel_id_or_ids})
            return data["deleteChannel"]

        data = self.transport.execute(queries.BULK_DELETE_CHANNELS, {"ids": channel_id_or_ids})
        return data["bulkDeleteChannels"]

    def disable_api_key(self, channel_id: str, key: str) -> bool:
        data = self.transport.execute(
            queries.DISABLE_CHANNEL_API_KEY,
            {"channelID": channel_id, "key": key},
        )
        return data["disableChannelAPIKey"]

    def enable_api_key(self, channel_id: str, key: str) -> bool:
        data = self.transport.execute(
            queries.ENABLE_CHANNEL_API_KEY,
            {"channelID": channel_id, "key": key},
        )
        return data["enableChannelAPIKey"]

    def enable_all_api_keys(self, channel_id: str) -> bool:
        data = self.transport.execute(queries.ENABLE_ALL_CHANNEL_API_KEYS, {"channelID": channel_id})
        return data["enableAllChannelAPIKeys"]

    def enable_selected_api_keys(self, channel_id: str, keys: list[str]) -> bool:
        data = self.transport.execute(
            queries.ENABLE_SELECTED_CHANNEL_API_KEYS,
            {"channelID": channel_id, "keys": keys},
        )
        return data["enableSelectedChannelAPIKeys"]

    def delete_disabled_api_keys(self, channel_id: str, keys: list[str]) -> dict[str, Any]:
        data = self.transport.execute(
            queries.DELETE_DISABLED_CHANNEL_API_KEYS,
            {"channelID": channel_id, "keys": keys},
        )
        return data["deleteDisabledChannelAPIKeys"]


class ModelsAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        status_in: list[str] | None = None,
        model_id: str | None = None,
        name: str | None = None,
        type_in: list[str] | None = None,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {"first": first}
        where: dict[str, Any] = {}
        if after:
            variables["after"] = after
        if status_in:
            where["statusIn"] = status_in
        if model_id:
            where["modelID"] = model_id
        if name:
            where["nameContainsFold"] = name
        if type_in:
            where["typeIn"] = type_in
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.MODELS, variables)
        return data["models"]

    def get(self, model_id: str) -> dict[str, Any] | None:
        data = self.transport.execute(queries.GET_MODEL, {"id": model_id})
        return data.get("node")

    def get_by_model_id(self, model_id: str) -> dict[str, Any] | None:
        result = self.list(first=1, model_id=model_id)
        edges = result.get("edges") or []
        if not edges:
            return None
        return edges[0].get("node")

    def create(self, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(queries.CREATE_MODEL, {"input": input_})
        return data["createModel"]

    def bulk_create(self, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.BULK_CREATE_MODELS, {"inputs": inputs})
        return data["bulkCreateModels"]

    def update(self, model_id: str, input_: dict[str, Any]) -> dict[str, Any]:
        data = self.transport.execute(
            queries.UPDATE_MODEL,
            {"id": model_id, "input": input_},
        )
        return data["updateModel"]

    def set_status(self, model_id: str, status: str) -> bool:
        data = self.transport.execute(
            queries.UPDATE_MODEL_STATUS,
            {"id": model_id, "status": status},
        )
        return data["updateModelStatus"]

    def archive(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_ARCHIVE_MODELS, {"ids": ids})
        return data["bulkArchiveModels"]

    def disable(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_DISABLE_MODELS, {"ids": ids})
        return data["bulkDisableModels"]

    def enable(self, ids: list[str]) -> bool:
        data = self.transport.execute(queries.BULK_ENABLE_MODELS, {"ids": ids})
        return data["bulkEnableModels"]

    def recover(self, ids: list[str]) -> bool:
        return self.enable(ids)

    def delete(self, model_id_or_ids: str | list[str]) -> bool:
        if isinstance(model_id_or_ids, str):
            data = self.transport.execute(queries.DELETE_MODEL, {"id": model_id_or_ids})
            return data["deleteModel"]

        data = self.transport.execute(queries.BULK_DELETE_MODELS, {"ids": model_id_or_ids})
        return data["bulkDeleteModels"]

    def rules(self, model_id: str, *, by_model_id: bool = False) -> list[dict[str, Any]]:
        model = self.get_by_model_id(model_id) if by_model_id else self.get(model_id)
        if not model:
            return []
        settings = model.get("settings") or {}
        return settings.get("associations") or []

    def set_rules(
        self,
        model_id: str,
        associations: list[dict[str, Any]],
        *,
        by_model_id: bool = False,
    ) -> dict[str, Any] | None:
        model = self.get_by_model_id(model_id) if by_model_id else self.get(model_id)
        if not model:
            return None
        settings = dict(model.get("settings") or {})
        settings["associations"] = associations
        return self.update(model["id"], {"settings": settings})

    def add_rule(
        self,
        model_id: str,
        association: dict[str, Any],
        *,
        by_model_id: bool = False,
        position: int | None = None,
    ) -> dict[str, Any] | None:
        def mutate(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
            insert_at = len(associations) if position is None else self._position_to_offset(position, len(associations))
            associations.insert(insert_at, dict(association))
            return self._normalize_rule_priorities(associations)

        return self._update_rules(model_id, mutate, by_model_id=by_model_id)

    def remove_rule(self, model_id: str, index: int, *, by_model_id: bool = False) -> dict[str, Any] | None:
        def mutate(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
            del associations[self._index_to_offset(index, len(associations))]
            return self._normalize_rule_priorities(associations)

        return self._update_rules(model_id, mutate, by_model_id=by_model_id)

    def set_rule_disabled(
        self,
        model_id: str,
        index: int,
        disabled: bool,
        *,
        by_model_id: bool = False,
    ) -> dict[str, Any] | None:
        def mutate(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
            target = self._index_to_offset(index, len(associations))
            associations[target] = {**associations[target], "disabled": disabled}
            return self._normalize_rule_priorities(associations)

        return self._update_rules(model_id, mutate, by_model_id=by_model_id)

    def reorder_rule(
        self,
        model_id: str,
        from_index: int,
        to_index: int,
        *,
        by_model_id: bool = False,
    ) -> dict[str, Any] | None:
        def mutate(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
            source = self._index_to_offset(from_index, len(associations))
            target = self._index_to_offset(to_index, len(associations))
            item = associations.pop(source)
            associations.insert(target, item)
            return self._normalize_rule_priorities(associations)

        return self._update_rules(model_id, mutate, by_model_id=by_model_id)

    def _update_rules(
        self,
        model_id: str,
        mutate: Any,
        *,
        by_model_id: bool = False,
    ) -> dict[str, Any] | None:
        model = self.get_by_model_id(model_id) if by_model_id else self.get(model_id)
        if not model:
            return None
        settings = dict(model.get("settings") or {})
        associations = self._sort_rules(settings.get("associations") or [])
        settings["associations"] = mutate(associations)
        return self.update(model["id"], {"settings": settings})

    @staticmethod
    def _sort_rules(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            dict(item)
            for _, item in sorted(
                enumerate(associations),
                key=lambda item: (item[1].get("priority", 0), item[0]),
            )
        ]

    @staticmethod
    def _normalize_rule_priorities(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**item, "priority": index} for index, item in enumerate(associations)]

    @staticmethod
    def _index_to_offset(index: int, size: int) -> int:
        if index < 1 or index > size:
            raise ValueError("rule index is out of range")
        return index - 1

    @staticmethod
    def _position_to_offset(position: int, size: int) -> int:
        if position < 1 or position > size + 1:
            raise ValueError("rule position is out of range")
        return position - 1

    def channels(
        self,
        model_id: str | None = None,
        *,
        by_model_id: bool = False,
        associations: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if associations is None:
            if model_id is None:
                raise ValueError("model_id is required when associations is not provided")
            model = self.get_by_model_id(model_id) if by_model_id else self.get(model_id)
            if not model:
                return []
            settings = model.get("settings") or {}
            associations = settings.get("associations") or []

        data = self.transport.execute(
            queries.QUERY_MODEL_CHANNEL_CONNECTIONS,
            {"associations": associations},
        )
        return data["queryModelChannelConnections"]

    def unassociated_channels(self) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.QUERY_UNASSOCIATED_CHANNELS)
        return data["queryUnassociatedChannels"]

    def fastest(self, *, time_window: str = "day", limit: int = 5) -> list[dict[str, Any]]:
        data = self.transport.execute(
            queries.FASTEST_MODELS,
            {"input": {"timeWindow": time_window, "limit": limit}},
        )
        return data["fastestModels"]


