from __future__ import annotations

from .client_admin import APIKeysAPI, AuthAPI, ChannelsAPI, ModelsAPI
from .client_management import DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from .client_observability import RequestsAPI, TracesAPI, UsageAPI, UsageLogsAPI
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


