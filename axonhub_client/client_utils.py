from __future__ import annotations

from typing import Any


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
