from __future__ import annotations

from typing import Any

from . import queries
from .client_utils import _add_created_window, _connection_variables, _request_where, _trace_where, _usage_log_where
from .transport import GraphQLTransport


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


