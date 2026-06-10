from __future__ import annotations

from typing import Any

from .client_utils import _connection_nodes, _pick
from .exceptions import SESSION_RELOGIN_MESSAGE, is_auth_error


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


