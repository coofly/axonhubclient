from __future__ import annotations

from typing import Any

from . import queries
from .exceptions import SESSION_RELOGIN_MESSAGE, is_auth_error
from .transport import GraphQLTransport


class AxonHubClient:
    """AxonHub Admin API client."""

    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport
        self.auth = AuthAPI(transport)
        self.api_keys = APIKeysAPI(transport)
        self.channels = ChannelsAPI(transport)
        self.diagnostics = DiagnosticsAPI(self)
        self.models = ModelsAPI(transport)
        self.requests = RequestsAPI(transport)
        self.smoke_test = SmokeTestAPI(self)
        self.traces = TracesAPI(transport)
        self.usage = UsageAPI(transport)
        self.usage_logs = UsageLogsAPI(transport)
        self.inventory = InventoryAPI(self)

    @classmethod
    def from_config(
        cls,
        base_url: str,
        *,
        admin_token: str | None = None,
        timeout: float = 30,
        project_id: str | None = None,
    ) -> "AxonHubClient":
        return cls(GraphQLTransport(base_url, token=admin_token, timeout=timeout, project_id=project_id))


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


class UsageAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def overview(self) -> dict[str, Any]:
        data = self.transport.execute(queries.DASHBOARD_OVERVIEW)
        return data["dashboardOverview"]

    def requests_by_channel(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.REQUESTS_BY_CHANNEL, {"timeWindow": time_window})
        return data["requestStatsByChannel"]

    def requests_by_model(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.REQUESTS_BY_MODEL, {"timeWindow": time_window})
        return data["requestStatsByModel"]

    def tokens_by_channel(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.TOKENS_BY_CHANNEL, {"timeWindow": time_window})
        return data["tokenStatsByChannel"]

    def tokens_by_model(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.TOKENS_BY_MODEL, {"timeWindow": time_window})
        return data["tokenStatsByModel"]

    def cost_by_channel(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.COST_BY_CHANNEL, {"timeWindow": time_window})
        return data["costStatsByChannel"]

    def cost_by_model(self, *, time_window: str | None = None) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.COST_BY_MODEL, {"timeWindow": time_window})
        return data["costStatsByModel"]

    def daily(self) -> list[dict[str, Any]]:
        data = self.transport.execute(queries.DAILY_REQUEST_STATS)
        return data["dailyRequestStats"]

    def token_stats(self) -> dict[str, Any]:
        data = self.transport.execute(queries.TOKEN_STATS)
        return data["tokenStats"]

    def channel_success_rates(
        self,
        *,
        time_window: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        data = self.transport.execute(
            queries.CHANNEL_SUCCESS_RATES,
            {"timeWindow": time_window, "limit": limit},
        )
        return data["channelSuccessRates"]


class RequestsAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        status_in: list[str] | None = None,
        source_in: list[str] | None = None,
        channel_id: str | None = None,
        project_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> dict[str, Any]:
        variables = _connection_variables(first=first, after=after)
        where = _request_where(
            status_in=status_in,
            source_in=source_in,
            channel_id=channel_id,
            project_id=project_id,
            model_id=model_id,
            trace_id=trace_id,
            created_after=created_after,
            created_before=created_before,
        )
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.REQUESTS, variables)
        return data["requests"]

    def get(self, request_id: str, *, include_content: bool = False) -> dict[str, Any] | None:
        query = queries.GET_REQUEST_WITH_CONTENT if include_content else queries.GET_REQUEST
        data = self.transport.execute(query, {"id": request_id})
        return data.get("node")

    def executions(
        self,
        request_id: str,
        *,
        first: int = 100,
        after: str | None = None,
        status_in: list[str] | None = None,
        channel_id: str | None = None,
    ) -> dict[str, Any]:
        variables = _connection_variables(first=first, after=after)
        variables["requestID"] = request_id
        where: dict[str, Any] = {}
        if status_in:
            where["statusIn"] = status_in
        if channel_id:
            where["channelID"] = channel_id
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.REQUEST_EXECUTIONS, variables)
        node = data.get("node") or {}
        return node.get("executions") or {"edges": [], "pageInfo": {}, "totalCount": 0}


class UsageLogsAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        source_in: list[str] | None = None,
        channel_id: str | None = None,
        project_id: str | None = None,
        request_id: str | None = None,
        model_id: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> dict[str, Any]:
        variables = _connection_variables(first=first, after=after)
        where = _usage_log_where(
            source_in=source_in,
            channel_id=channel_id,
            project_id=project_id,
            request_id=request_id,
            model_id=model_id,
            created_after=created_after,
            created_before=created_before,
        )
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.USAGE_LOGS, variables)
        return data["usageLogs"]

    def get(self, usage_log_id: str) -> dict[str, Any] | None:
        data = self.transport.execute(queries.GET_USAGE_LOG, {"id": usage_log_id})
        return data.get("node")


class TracesAPI:
    def __init__(self, transport: GraphQLTransport) -> None:
        self.transport = transport

    def list(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        trace_id: str | None = None,
        thread_id: str | None = None,
        request_id: str | None = None,
        project_id: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> dict[str, Any]:
        variables = _connection_variables(first=first, after=after)
        where = _trace_where(
            trace_id=trace_id,
            thread_id=thread_id,
            request_id=request_id,
            project_id=project_id,
            created_after=created_after,
            created_before=created_before,
        )
        if where:
            variables["where"] = where
        data = self.transport.execute(queries.TRACES, variables)
        return data["traces"]

    def get(self, trace_id: str) -> dict[str, Any] | None:
        data = self.transport.execute(queries.GET_TRACE, {"id": trace_id})
        return data.get("node")


class DiagnosticsAPI:
    def __init__(self, client: AxonHubClient) -> None:
        self.client = client

    def channel_health(
        self,
        *,
        channel_id: str | None = None,
        first: int = 50,
        time_window: str | None = "day",
        min_success_rate: float = 0.95,
        recent_failures: int = 5,
    ) -> dict[str, Any]:
        if channel_id:
            channel = self.client.channels.get(channel_id)
            channels = [channel] if channel else []
        else:
            connection = self.client.channels.list(first=first)
            channels = _connection_nodes(connection)

        rates = self.client.usage.channel_success_rates(time_window=time_window, limit=first)
        rates_by_id = {str(item.get("channelId")): item for item in rates if item.get("channelId") is not None}
        items = [
            self._channel_health_item(channel, rates_by_id.get(str(channel.get("id"))), min_success_rate, recent_failures)
            for channel in channels
            if channel
        ]
        return {
            "timeWindow": time_window,
            "minSuccessRate": min_success_rate,
            "channels": items,
            "summary": {
                "total": len(items),
                "healthy": sum(1 for item in items if item["level"] == "healthy"),
                "warning": sum(1 for item in items if item["level"] == "warning"),
                "critical": sum(1 for item in items if item["level"] == "critical"),
            },
        }

    def _channel_health_item(
        self,
        channel: dict[str, Any],
        rate: dict[str, Any] | None,
        min_success_rate: float,
        recent_failures: int,
    ) -> dict[str, Any]:
        channel_id = str(channel.get("id"))
        failed_requests = self.client.requests.list(
            first=recent_failures,
            status_in=["failed"],
            channel_id=channel_id,
        )
        failures = _connection_nodes(failed_requests)
        reasons = [
            execution.get("node", {}).get("errorMessage")
            for request in failures
            for execution in ((request.get("executions") or {}).get("edges") or [])
            if execution.get("node", {}).get("errorMessage")
        ]
        success_rate = rate.get("successRate") if rate else None
        issues: list[str] = []
        if channel.get("status") != "enabled":
            issues.append("channel_not_enabled")
        if channel.get("errorMessage"):
            issues.append("channel_error_message")
        if not channel.get("supportedModels"):
            issues.append("no_supported_models")
        if isinstance(success_rate, (int, float)) and success_rate < min_success_rate:
            issues.append("low_success_rate")
        if failures:
            issues.append("recent_failed_requests")

        level = "healthy"
        if issues:
            level = "warning"
        if "channel_not_enabled" in issues or "low_success_rate" in issues or "channel_error_message" in issues:
            level = "critical"

        return {
            "id": channel.get("id"),
            "name": channel.get("name"),
            "type": channel.get("type"),
            "status": channel.get("status"),
            "level": level,
            "issues": issues,
            "successRate": success_rate,
            "successStats": rate or {},
            "latencyMs": self._latest_latency(failures),
            "errorMessage": channel.get("errorMessage"),
            "recentErrorReasons": list(dict.fromkeys(reasons))[:5],
            "recentFailedRequests": [
                _pick(
                    request,
                    "id",
                    "createdAt",
                    "modelID",
                    "status",
                    "metricsLatencyMs",
                    "metricsFirstTokenLatencyMs",
                    "metricsReasoningDurationMs",
                )
                for request in failures
            ],
            "config": _pick(channel, "supportedModels", "defaultTestModel", "tags", "baseURL"),
        }

    @staticmethod
    def _latest_latency(requests: list[dict[str, Any]]) -> int | None:
        for request in requests:
            latency = request.get("metricsLatencyMs")
            if latency is not None:
                return latency
        return None


class SmokeTestAPI:
    def __init__(self, client: AxonHubClient) -> None:
        self.client = client

    def run(self) -> dict[str, Any]:
        steps = [
            ("auth.status", lambda: self.client.auth.status()),
            ("auth.whoami", lambda: self.client.auth.whoami()),
            ("inventory.summary", lambda: self.client.inventory.summary(channel_first=50, model_first=100)),
            ("requests.list", lambda: self.client.requests.list(first=5)),
            ("usage_logs.list", lambda: self.client.usage_logs.list(first=5)),
            ("traces.list", lambda: self.client.traces.list(first=5)),
            ("diagnostics.channel_health", lambda: self.client.diagnostics.channel_health(first=10)),
        ]
        results = []
        for name, run in steps:
            try:
                results.append({"name": name, "ok": True, "result": run()})
            except Exception as exc:  # pragma: no cover - defensive aggregation for live smoke tests.
                message = SESSION_RELOGIN_MESSAGE if is_auth_error(exc) else str(exc)
                results.append({"name": name, "ok": False, "error": message})
        return {
            "ok": all(item["ok"] for item in results),
            "mode": "read-only",
            "steps": results,
        }


class InventoryAPI:
    def __init__(self, client: AxonHubClient) -> None:
        self.client = client

    def summary(
        self,
        *,
        channel_first: int = 500,
        model_first: int = 1000,
        success_window: str | None = "day",
        success_limit: int | None = 20,
        min_success_rate: float = 0.95,
    ) -> dict[str, Any]:
        channels_connection = self.client.channels.list(first=channel_first)
        model_connection = self.client.models.list(first=model_first)
        usage_overview = self.client.usage.overview()
        channel_success_rates = self.client.usage.channel_success_rates(
            time_window=success_window,
            limit=success_limit,
        )
        unassociated_channels = self.client.models.unassociated_channels()

        channel_nodes = self._connection_nodes(channels_connection)
        model_nodes = self._connection_nodes(model_connection)
        channel_anomalies = self._channel_anomalies(channel_nodes, channel_success_rates, min_success_rate)
        model_anomalies = self._model_anomalies(model_nodes, unassociated_channels)

        return {
            "channels": {
                "total": channels_connection.get("totalCount", len(channel_nodes)),
                "fetched": len(channel_nodes),
                "byStatus": self._count_by(channel_nodes, "status"),
                "byType": self._count_by(channel_nodes, "type"),
                "anomalies": channel_anomalies,
                "pageInfo": channels_connection.get("pageInfo") or {},
            },
            "models": {
                "total": model_connection.get("totalCount", len(model_nodes)),
                "fetched": len(model_nodes),
                "byStatus": self._count_by(model_nodes, "status"),
                "byType": self._count_by(model_nodes, "type"),
                "anomalies": model_anomalies,
                "pageInfo": model_connection.get("pageInfo") or {},
            },
            "usage": {
                "overview": usage_overview,
                "channelSuccessRates": channel_success_rates,
            },
            "attention": {
                "channelsWithErrors": len(channel_anomalies["withErrors"]),
                "channelsWithoutModels": len(channel_anomalies["withoutSupportedModels"]),
                "lowSuccessChannels": len(channel_anomalies["lowSuccessRates"]),
                "modelsWithoutAssociations": len(model_anomalies["withoutAssociations"]),
                "unassociatedChannelModelEntries": len(model_anomalies["unassociatedChannels"]),
            },
        }

    @staticmethod
    def _connection_nodes(connection: dict[str, Any]) -> list[dict[str, Any]]:
        return _connection_nodes(connection)

    @staticmethod
    def _count_by(items: list[dict[str, Any]], field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            key = str(item.get(field) or "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _channel_anomalies(
        channels: list[dict[str, Any]],
        success_rates: list[dict[str, Any]],
        min_success_rate: float,
    ) -> dict[str, Any]:
        return {
            "notEnabled": [
                InventoryAPI._pick(item, "id", "name", "type", "status")
                for item in channels
                if item.get("status") != "enabled"
            ],
            "withErrors": [
                InventoryAPI._pick(item, "id", "name", "type", "status", "errorMessage")
                for item in channels
                if item.get("errorMessage")
            ],
            "withoutSupportedModels": [
                InventoryAPI._pick(item, "id", "name", "type", "status")
                for item in channels
                if not item.get("supportedModels")
            ],
            "lowSuccessRates": [
                item
                for item in success_rates
                if isinstance(item.get("successRate"), (int, float)) and item["successRate"] < min_success_rate
            ],
        }

    @staticmethod
    def _model_anomalies(
        models: list[dict[str, Any]],
        unassociated_channels: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "notEnabled": [
                InventoryAPI._pick(item, "id", "developer", "modelID", "type", "status")
                for item in models
                if item.get("status") != "enabled"
            ],
            "withoutAssociations": [
                InventoryAPI._pick(item, "id", "developer", "modelID", "type", "status", "associatedChannelCount")
                for item in models
                if item.get("associatedChannelCount") == 0
            ],
            "unassociatedChannels": unassociated_channels,
        }

    @staticmethod
    def _pick(item: dict[str, Any], *fields: str) -> dict[str, Any]:
        return _pick(item, *fields)


def _connection_variables(*, first: int = 100, after: str | None = None) -> dict[str, Any]:
    variables: dict[str, Any] = {
        "first": first,
        "orderBy": {"field": "CREATED_AT", "direction": "DESC"},
    }
    if after:
        variables["after"] = after
    return variables


def _request_where(
    *,
    status_in: list[str] | None = None,
    source_in: list[str] | None = None,
    channel_id: str | None = None,
    project_id: str | None = None,
    model_id: str | None = None,
    trace_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> dict[str, Any]:
    where: dict[str, Any] = {}
    if status_in:
        where["statusIn"] = status_in
    if source_in:
        where["sourceIn"] = source_in
    if channel_id:
        where["channelID"] = channel_id
    if project_id:
        where["projectID"] = project_id
    if model_id:
        where["modelID"] = model_id
    if trace_id:
        where["traceID"] = trace_id
    _add_created_window(where, created_after=created_after, created_before=created_before)
    return where


def _usage_log_where(
    *,
    source_in: list[str] | None = None,
    channel_id: str | None = None,
    project_id: str | None = None,
    request_id: str | None = None,
    model_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> dict[str, Any]:
    where: dict[str, Any] = {}
    if source_in:
        where["sourceIn"] = source_in
    if channel_id:
        where["channelID"] = channel_id
    if project_id:
        where["projectID"] = project_id
    if request_id:
        where["requestID"] = request_id
    if model_id:
        where["modelID"] = model_id
    _add_created_window(where, created_after=created_after, created_before=created_before)
    return where


def _trace_where(
    *,
    trace_id: str | None = None,
    thread_id: str | None = None,
    request_id: str | None = None,
    project_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> dict[str, Any]:
    where: dict[str, Any] = {}
    if trace_id:
        where["traceID"] = trace_id
    if thread_id:
        where["threadID"] = thread_id
    if request_id:
        where["hasRequestsWith"] = [{"id": request_id}]
    if project_id:
        where["projectID"] = project_id
    _add_created_window(where, created_after=created_after, created_before=created_before)
    return where


def _add_created_window(where: dict[str, Any], *, created_after: str | None, created_before: str | None) -> None:
    if created_after:
        where["createdAtGTE"] = created_after
    if created_before:
        where["createdAtLTE"] = created_before


def _connection_nodes(connection: dict[str, Any]) -> list[dict[str, Any]]:
    return [edge.get("node") or {} for edge in connection.get("edges") or []]


def _pick(item: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {field: item.get(field) for field in fields if field in item}
