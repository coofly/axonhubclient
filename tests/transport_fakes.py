import unittest

from axonhub_client.client import AxonHubClient, DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from axonhub_client.discovery import discover_supported_models, normalize_channel_type
from axonhub_client.exceptions import ConfigurationError, GraphQLError
from axonhub_client.transport import GraphQLTransport, extract_operation_name


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {"data": {"ok": True}}
        self.headers = headers or {"content-type": "application/json"}
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts = []
        self.gets = []

    def post(self, url, json, headers, timeout):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.response

    def get(self, url, headers, timeout):
        self.gets.append({"url": url, "headers": headers, "timeout": timeout})
        return self.response


class FakeChannelsAPI:
    def __init__(self):
        self.list_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return {
            "edges": [
                {
                    "node": {
                        "id": "1",
                        "name": "healthy",
                        "type": "openai",
                        "status": "enabled",
                        "supportedModels": ["gpt-4o-mini"],
                    }
                },
                {
                    "node": {
                        "id": "2",
                        "name": "broken",
                        "type": "openai",
                        "status": "disabled",
                        "supportedModels": [],
                        "errorMessage": "quota exceeded",
                    }
                },
            ],
            "pageInfo": {"hasNextPage": False},
            "totalCount": 2,
        }


class FakeModelsAPI:
    def __init__(self):
        self.list_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return {
            "edges": [
                {
                    "node": {
                        "id": "m1",
                        "developer": "openai",
                        "modelID": "gpt-4o-mini",
                        "type": "chat",
                        "status": "enabled",
                        "associatedChannelCount": 1,
                    }
                },
                {
                    "node": {
                        "id": "m2",
                        "developer": "openai",
                        "modelID": "gpt-4",
                        "type": "chat",
                        "status": "disabled",
                        "associatedChannelCount": 0,
                    }
                },
            ],
            "pageInfo": {"hasNextPage": False},
            "totalCount": 2,
        }

    def unassociated_channels(self):
        return [{"channel": {"id": "2", "name": "broken"}, "models": ["gpt-4"]}]


class FakeUsageAPI:
    def __init__(self):
        self.success_kwargs = None

    def overview(self):
        return {"totalRequests": 10, "failedRequests": 1}

    def channel_success_rates(self, **kwargs):
        self.success_kwargs = kwargs
        return [
            {"channelId": "1", "channelName": "healthy", "successRate": 0.99},
            {"channelId": "2", "channelName": "broken", "successRate": 0.5},
        ]


class FakeRequestsAPI:
    def __init__(self):
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return {
            "edges": [
                {
                    "node": {
                        "id": "r1",
                        "createdAt": "2026-06-09T00:00:00Z",
                        "modelID": "gpt-4o-mini",
                        "status": "failed",
                        "metricsLatencyMs": 1200,
                        "executions": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "e1",
                                        "errorMessage": "upstream timeout",
                                    }
                                }
                            ]
                        },
                    }
                }
            ],
            "pageInfo": {"hasNextPage": False},
            "totalCount": 1,
        }


class FakeInventoryClient:
    def __init__(self):
        self.channels = FakeChannelsAPI()
        self.models = FakeModelsAPI()
        self.requests = FakeRequestsAPI()
        self.usage = FakeUsageAPI()


class FakeAuthAPI:
    def status(self):
        return {"ok": True}

    def whoami(self):
        return {"id": "user-1"}


class FakeConnectionAPI:
    def list(self, **_kwargs):
        return {"edges": [], "pageInfo": {"hasNextPage": False}, "totalCount": 0}


class FakeSmokeClient:
    def __init__(self):
        self.auth = FakeAuthAPI()
        self.inventory = InventoryAPI(FakeInventoryClient())
        self.requests = FakeConnectionAPI()
        self.usage_logs = FakeConnectionAPI()
        self.traces = FakeConnectionAPI()
        self.diagnostics = DiagnosticsAPI(FakeInventoryClient())


