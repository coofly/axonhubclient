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


class TransportTest(unittest.TestCase):
    def test_extract_operation_name(self):
        self.assertEqual(extract_operation_name("\nquery Me { me { id } }"), "Me")
        self.assertEqual(extract_operation_name("mutation CreateThing { ok }"), "CreateThing")
        self.assertIsNone(extract_operation_name("{ me { id } }"))

    def test_execute_sets_url_headers_and_operation_name(self):
        session = FakeSession(FakeResponse(body={"data": {"me": {"id": "1"}}}))
        transport = GraphQLTransport("https://example.com/app", token="secret", session=session, project_id="p1")

        data = transport.execute("query Me { me { id } }")

        self.assertEqual(data, {"me": {"id": "1"}})
        request = session.posts[0]
        self.assertEqual(request["url"], "https://example.com/app/admin/graphql")
        self.assertEqual(request["json"]["operationName"], "Me")
        self.assertEqual(request["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(request["headers"]["X-Project-ID"], "p1")

    def test_graphql_auth_error(self):
        session = FakeSession(
            FakeResponse(
                body={"errors": [{"message": "unauthenticated", "extensions": {"code": "UNAUTHENTICATED"}}]}
            )
        )
        transport = GraphQLTransport("https://example.com", session=session)

        with self.assertRaises(GraphQLError) as ctx:
            transport.execute("query Me { me { id } }")

        self.assertTrue(ctx.exception.is_auth_error)

    def test_post_json_uses_rest_url(self):
        session = FakeSession(FakeResponse(body={"token": "jwt"}))
        transport = GraphQLTransport("https://example.com/app", session=session)

        data = transport.post_json("/admin/auth/signin", {"email": "admin@example.com", "password": "pw"})

        self.assertEqual(data, {"token": "jwt"})
        request = session.posts[0]
        self.assertEqual(request["url"], "https://example.com/app/admin/auth/signin")
        self.assertEqual(request["json"], {"email": "admin@example.com", "password": "pw"})

    def test_discover_supported_models_reads_openai_models(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "object": "list",
                    "data": [
                        {"id": "model-a"},
                        {"id": "model-b"},
                        {"id": "model-a"},
                    ],
                }
            )
        )

        models = discover_supported_models(
            channel_type="newapi_channel_conn",
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            timeout=12,
            session=session,
        )

        self.assertEqual(normalize_channel_type("newapi_channel_conn"), "openai")
        self.assertEqual(models, ["model-a", "model-b"])
        request = session.gets[0]
        self.assertEqual(request["url"], "https://api.example.com/v1/models")
        self.assertEqual(request["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(request["timeout"], 12)

    def test_discover_supported_models_rejects_unsupported_type(self):
        with self.assertRaises(ConfigurationError):
            discover_supported_models(
                channel_type="anthropic",
                base_url="https://api.example.com",
                api_key="sk-test",
            )

    def test_inventory_summary_aggregates_assets_and_attention_items(self):
        fake_client = FakeInventoryClient()
        inventory = InventoryAPI(fake_client)

        result = inventory.summary(channel_first=50, model_first=60, success_window="week", success_limit=5)

        self.assertEqual(fake_client.channels.list_kwargs, {"first": 50})
        self.assertEqual(fake_client.models.list_kwargs, {"first": 60})
        self.assertEqual(fake_client.usage.success_kwargs, {"time_window": "week", "limit": 5})
        self.assertEqual(result["channels"]["byStatus"], {"enabled": 1, "disabled": 1})
        self.assertEqual(result["models"]["byStatus"], {"enabled": 1, "disabled": 1})
        self.assertEqual(result["attention"]["channelsWithErrors"], 1)
        self.assertEqual(result["attention"]["channelsWithoutModels"], 1)
        self.assertEqual(result["attention"]["lowSuccessChannels"], 1)
        self.assertEqual(result["attention"]["modelsWithoutAssociations"], 1)
        self.assertEqual(result["attention"]["unassociatedChannelModelEntries"], 1)

    def test_create_channel_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"createChannel": {"id": "1", "name": "test"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        input_ = {
            "type": "openai",
            "baseURL": "https://api.openai.com/v1",
            "name": "test",
            "credentials": {"apiKeys": ["sk-test"]},
            "supportedModels": ["gpt-4o-mini"],
            "manualModels": ["gpt-4o-mini"],
            "defaultTestModel": "gpt-4o-mini",
        }

        result = client.channels.create(input_)

        self.assertEqual(result, {"id": "1", "name": "test"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "CreateChannel")
        self.assertEqual(request["json"]["variables"], {"input": input_})

    def test_bulk_create_channels_executes_mutation(self):
        session = FakeSession(
            FakeResponse(body={"data": {"bulkCreateChannels": [{"id": "1", "name": "test-a"}, {"id": "2", "name": "test-b"}]}})
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        input_ = {
            "type": "openai",
            "baseURL": "https://api.openai.com/v1",
            "name": "test",
            "apiKeys": ["sk-1", "sk-2"],
            "supportedModels": ["gpt-4o-mini"],
            "defaultTestModel": "gpt-4o-mini",
        }

        result = client.channels.bulk_create(input_)

        self.assertEqual(result, [{"id": "1", "name": "test-a"}, {"id": "2", "name": "test-b"}])
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "BulkCreateChannels")
        self.assertEqual(request["json"]["variables"], {"input": input_})

    def test_bulk_import_channels_executes_mutation(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "bulkImportChannels": {
                            "success": True,
                            "created": 1,
                            "failed": 0,
                            "errors": [],
                            "channels": [{"id": "1", "name": "test"}],
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        input_ = {
            "channels": [
                {
                    "type": "openai",
                    "name": "test",
                    "baseURL": "https://api.openai.com/v1",
                    "apiKey": "sk-test",
                    "supportedModels": ["gpt-4o-mini"],
                    "defaultTestModel": "gpt-4o-mini",
                }
            ]
        }

        result = client.channels.bulk_import(input_)

        self.assertTrue(result["success"])
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "BulkImportChannels")
        self.assertEqual(request["json"]["variables"], {"input": input_})

    def test_update_channel_executes_mutation(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "updateChannel": {
                            "id": "1",
                            "name": "test",
                            "orderingWeight": 42,
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.update("1", {"orderingWeight": 42})

        self.assertEqual(result, {"id": "1", "name": "test", "orderingWeight": 42})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "UpdateChannel")
        self.assertEqual(request["json"]["variables"], {"id": "1", "input": {"orderingWeight": 42}})

    def test_set_channel_status_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"updateChannelStatus": {"id": "1", "status": "enabled"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.set_status("1", "enabled")

        self.assertEqual(result, {"id": "1", "status": "enabled"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "UpdateChannelStatus")
        self.assertEqual(request["json"]["variables"], {"id": "1", "status": "enabled"})

    def test_bulk_update_channel_ordering_executes_mutation(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "bulkUpdateChannelOrdering": {
                            "success": True,
                            "updated": 2,
                            "channels": [{"id": "1", "orderingWeight": 42}],
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.bulk_update_ordering({"channels": [{"id": "1", "orderingWeight": 42}]})

        self.assertTrue(result["success"])
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "BulkUpdateChannelOrdering")
        self.assertEqual(request["json"]["variables"], {"input": {"channels": [{"id": "1", "orderingWeight": 42}]}})

    def test_save_channel_endpoints_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"saveChannelEndpoints": {"id": "1", "name": "test"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        endpoints = [{"apiFormat": "openai", "path": "/v1/chat/completions"}]

        result = client.channels.save_endpoints("1", endpoints)

        self.assertEqual(result, {"id": "1", "name": "test"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "SaveChannelEndpoints")
        self.assertEqual(request["json"]["variables"], {"input": {"channelID": "1", "endpoints": endpoints}})

    def test_test_channel_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"testChannel": {"success": True, "latency": 12.3}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.test("1", model_id="gpt-4o-mini", proxy={"type": "ENVIRONMENT"})

        self.assertEqual(result, {"success": True, "latency": 12.3})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "TestChannel")
        self.assertEqual(
            request["json"]["variables"],
            {"input": {"channelID": "1", "modelID": "gpt-4o-mini", "proxy": {"type": "ENVIRONMENT"}}},
        )

    def test_test_channel_api_keys_executes_mutation(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "testChannelAPIKeys": {
                            "channelID": "1",
                            "total": 1,
                            "successCount": 1,
                            "failedCount": 0,
                            "results": [{"keyPrefix": "sk-...", "success": True, "latency": 10, "disabled": False}],
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.test_api_keys("1", model_id="gpt-4o-mini")

        self.assertEqual(result["total"], 1)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "TestChannelAPIKeys")
        self.assertEqual(request["json"]["variables"], {"channelID": "1", "modelID": "gpt-4o-mini"})

    def test_sync_channel_models_executes_mutation(self):
        session = FakeSession(
            FakeResponse(body={"data": {"syncChannelModels": {"channelID": "1", "supportedModels": ["gpt-4o-mini"]}}})
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.sync_models("1", pattern="gpt-.*")

        self.assertEqual(result, {"channelID": "1", "supportedModels": ["gpt-4o-mini"]})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "SyncChannelModels")
        self.assertEqual(request["json"]["variables"], {"channelID": "1", "pattern": "gpt-.*"})

    def test_disable_enable_channels_execute_mutations(self):
        for method_name, response_key, operation_name in (
            ("disable", "bulkDisableChannels", "BulkDisableChannels"),
            ("enable", "bulkEnableChannels", "BulkEnableChannels"),
        ):
            session = FakeSession(FakeResponse(body={"data": {response_key: True}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = getattr(client.channels, method_name)(["1", "2"])

            self.assertTrue(result)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], {"ids": ["1", "2"]})

    def test_archive_recover_delete_channels_execute_mutations(self):
        for method_name, response_key, operation_name in (
            ("archive", "bulkArchiveChannels", "BulkArchiveChannels"),
            ("recover", "bulkRecoverChannels", "BulkRecoverChannels"),
            ("delete", "bulkDeleteChannels", "BulkDeleteChannels"),
        ):
            session = FakeSession(FakeResponse(body={"data": {response_key: True}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = getattr(client.channels, method_name)(["1", "2"])

            self.assertTrue(result)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], {"ids": ["1", "2"]})

    def test_delete_single_channel_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"deleteChannel": True}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.delete("1")

        self.assertTrue(result)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "DeleteChannel")
        self.assertEqual(request["json"]["variables"], {"id": "1"})

    def test_channel_api_key_single_key_mutations_execute(self):
        for method_name, response_key, operation_name in (
            ("disable_api_key", "disableChannelAPIKey", "DisableChannelAPIKey"),
            ("enable_api_key", "enableChannelAPIKey", "EnableChannelAPIKey"),
        ):
            session = FakeSession(FakeResponse(body={"data": {response_key: True}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = getattr(client.channels, method_name)("1", "sk-test")

            self.assertTrue(result)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], {"channelID": "1", "key": "sk-test"})

    def test_enable_all_channel_api_keys_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"enableAllChannelAPIKeys": True}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.channels.enable_all_api_keys("1")

        self.assertTrue(result)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "EnableAllChannelAPIKeys")
        self.assertEqual(request["json"]["variables"], {"channelID": "1"})

    def test_selected_channel_api_key_mutations_execute(self):
        for method_name, response_key, operation_name in (
            ("enable_selected_api_keys", "enableSelectedChannelAPIKeys", "EnableSelectedChannelAPIKeys"),
            ("delete_disabled_api_keys", "deleteDisabledChannelAPIKeys", "DeleteDisabledChannelAPIKeys"),
        ):
            response = True if response_key == "enableSelectedChannelAPIKeys" else {"success": True, "message": "deleted"}
            session = FakeSession(FakeResponse(body={"data": {response_key: response}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = getattr(client.channels, method_name)("1", ["sk-a", "sk-b"])

            self.assertEqual(result, response)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], {"channelID": "1", "keys": ["sk-a", "sk-b"]})

    def test_get_model_executes_query(self):
        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "1", "modelID": "gpt-4o-mini"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.get("1")

        self.assertEqual(result, {"id": "1", "modelID": "gpt-4o-mini"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetModel")
        self.assertEqual(request["json"]["variables"], {"id": "1"})

    def test_get_model_by_model_id_uses_where_filter(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "models": {
                            "edges": [{"node": {"id": "1", "modelID": "gpt-4o-mini"}}],
                            "pageInfo": {},
                            "totalCount": 1,
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.get_by_model_id("gpt-4o-mini")

        self.assertEqual(result, {"id": "1", "modelID": "gpt-4o-mini"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetModels")
        self.assertEqual(request["json"]["variables"], {"first": 1, "where": {"modelID": "gpt-4o-mini"}})

    def test_create_model_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"createModel": {"id": "1", "modelID": "gpt-4o-mini"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        input_ = {"developer": "openai", "modelID": "gpt-4o-mini", "name": "GPT-4o mini"}

        result = client.models.create(input_)

        self.assertEqual(result, {"id": "1", "modelID": "gpt-4o-mini"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "CreateModel")
        self.assertEqual(request["json"]["variables"], {"input": input_})

    def test_bulk_create_models_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"bulkCreateModels": [{"id": "1"}]}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        inputs = [{"developer": "openai", "modelID": "gpt-4o-mini"}]

        result = client.models.bulk_create(inputs)

        self.assertEqual(result, [{"id": "1"}])
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "BulkCreateModels")
        self.assertEqual(request["json"]["variables"], {"inputs": inputs})

    def test_update_model_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"updateModel": {"id": "1", "name": "new"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.update("1", {"name": "new"})

        self.assertEqual(result, {"id": "1", "name": "new"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "UpdateModel")
        self.assertEqual(request["json"]["variables"], {"id": "1", "input": {"name": "new"}})

    def test_model_status_mutations_execute(self):
        for method_name, response_key, operation_name in (
            ("archive", "bulkArchiveModels", "BulkArchiveModels"),
            ("disable", "bulkDisableModels", "BulkDisableModels"),
            ("enable", "bulkEnableModels", "BulkEnableModels"),
            ("recover", "bulkEnableModels", "BulkEnableModels"),
        ):
            session = FakeSession(FakeResponse(body={"data": {response_key: True}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = getattr(client.models, method_name)(["1", "2"])

            self.assertTrue(result)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], {"ids": ["1", "2"]})

    def test_set_model_status_executes_mutation(self):
        session = FakeSession(FakeResponse(body={"data": {"updateModelStatus": True}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.set_status("1", "enabled")

        self.assertTrue(result)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "UpdateModelStatus")
        self.assertEqual(request["json"]["variables"], {"id": "1", "status": "enabled"})

    def test_delete_model_executes_single_and_bulk_mutations(self):
        for argument, response_key, operation_name, variables in (
            ("1", "deleteModel", "DeleteModel", {"id": "1"}),
            (["1", "2"], "bulkDeleteModels", "BulkDeleteModels", {"ids": ["1", "2"]}),
        ):
            session = FakeSession(FakeResponse(body={"data": {response_key: True}}))
            client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

            result = client.models.delete(argument)

            self.assertTrue(result)
            request = session.posts[0]
            self.assertEqual(request["json"]["operationName"], operation_name)
            self.assertEqual(request["json"]["variables"], variables)

    def test_api_keys_list_executes_safe_query(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "apiKeys": {
                            "edges": [{"node": {"id": "ak1", "name": "prod", "status": "enabled"}}],
                            "pageInfo": {},
                            "totalCount": 1,
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.api_keys.list(
            first=50,
            after="cursor-1",
            status="enabled",
            type_="service_account",
            name="prod",
            project_id="project-1",
            user_id="user-1",
        )

        self.assertEqual(result["totalCount"], 1)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetAPIKeys")
        self.assertEqual(
            request["json"]["variables"],
            {
                "first": 50,
                "after": "cursor-1",
                "where": {
                    "status": "enabled",
                    "type": "service_account",
                    "nameContainsFold": "prod",
                    "projectID": "project-1",
                    "userID": "user-1",
                },
            },
        )

    def test_api_keys_list_excludes_noauth_by_default(self):
        session = FakeSession(FakeResponse(body={"data": {"apiKeys": {"edges": [], "pageInfo": {}, "totalCount": 0}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        client.api_keys.list()

        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetAPIKeys")
        self.assertEqual(request["json"]["variables"], {"first": 100, "where": {"typeNotIn": ["noauth"]}})

    def test_get_api_key_executes_safe_detail_query(self):
        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "ak1", "name": "prod"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.api_keys.get("ak1")

        self.assertEqual(result, {"id": "ak1", "name": "prod"})
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetAPIKey")
        self.assertEqual(request["json"]["variables"], {"id": "ak1"})

    def test_api_key_quota_usage_executes_query(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "apiKeyQuotaUsages": [
                            {"profileName": "default", "usage": {"requestCount": 3, "totalTokens": 10, "totalCost": 0.01}}
                        ]
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.api_keys.quota_usage("ak1")

        self.assertEqual(result[0]["profileName"], "default")
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "APIKeyQuotaUsages")
        self.assertEqual(request["json"]["variables"], {"apiKeyId": "ak1"})

    def test_api_key_profile_templates_executes_query(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "apiKeyProfileTemplates": {
                            "edges": [{"node": {"id": "tpl1", "name": "default"}}],
                            "pageInfo": {},
                            "totalCount": 1,
                        }
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.api_keys.profile_templates(first=25, project_id="project-1", name="default")

        self.assertEqual(result["totalCount"], 1)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "APIKeyProfileTemplates")
        self.assertEqual(
            request["json"]["variables"],
            {"first": 25, "where": {"projectID": "project-1", "nameContainsFold": "default"}},
        )

    def test_model_rules_read_settings_associations(self):
        associations = [{"type": "model", "modelId": {"modelId": "gpt-4o-mini"}}]
        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "1", "settings": {"associations": associations}}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.rules("1")

        self.assertEqual(result, associations)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetModel")

    def test_set_model_rules_preserves_other_settings(self):
        associations = [{"type": "model", "modelId": {"modelId": "gpt-4o-mini"}}]
        response = {
            "data": {
                "node": {"id": "1", "settings": {"disableDeveloperSettingsInheritance": True, "associations": []}},
                "updateModel": {"id": "1", "settings": {"associations": associations}},
            }
        }
        session = FakeSession(FakeResponse(body=response))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.set_rules("1", associations)

        self.assertEqual(result["id"], "1")
        request = session.posts[1]
        self.assertEqual(request["json"]["operationName"], "UpdateModel")
        self.assertEqual(
            request["json"]["variables"],
            {
                "id": "1",
                "input": {
                    "settings": {
                        "disableDeveloperSettingsInheritance": True,
                        "associations": associations,
                    }
                },
            },
        )

    def test_add_model_rule_normalizes_priorities(self):
        response = {
            "data": {
                "node": {
                    "id": "1",
                    "settings": {
                        "disableDeveloperSettingsInheritance": True,
                        "associations": [
                            {"type": "model", "priority": 10, "modelId": {"modelId": "a"}},
                            {"type": "model", "priority": 20, "modelId": {"modelId": "c"}},
                        ],
                    },
                },
                "updateModel": {"id": "1"},
            }
        }
        session = FakeSession(FakeResponse(body=response))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.add_rule("1", {"type": "model", "modelId": {"modelId": "b"}}, position=2)

        self.assertEqual(result["id"], "1")
        associations = session.posts[1]["json"]["variables"]["input"]["settings"]["associations"]
        self.assertEqual([item["modelId"]["modelId"] for item in associations], ["a", "b", "c"])
        self.assertEqual([item["priority"] for item in associations], [0, 1, 2])

    def test_model_rule_disable_and_reorder_edit_by_one_based_index(self):
        response = {
            "data": {
                "node": {
                    "id": "1",
                    "settings": {
                        "associations": [
                            {"type": "model", "priority": 1, "modelId": {"modelId": "b"}},
                            {"type": "model", "priority": 0, "modelId": {"modelId": "a"}},
                        ],
                    },
                },
                "updateModel": {"id": "1"},
            }
        }

        session = FakeSession(FakeResponse(body=response))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        client.models.set_rule_disabled("1", 2, True)
        disabled_associations = session.posts[1]["json"]["variables"]["input"]["settings"]["associations"]
        self.assertTrue(disabled_associations[1]["disabled"])

        session = FakeSession(FakeResponse(body=response))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        client.models.reorder_rule("1", 2, 1)
        reordered = session.posts[1]["json"]["variables"]["input"]["settings"]["associations"]
        self.assertEqual([item["modelId"]["modelId"] for item in reordered], ["b", "a"])
        self.assertEqual([item["priority"] for item in reordered], [0, 1])

    def test_remove_model_rule_edits_by_one_based_index(self):
        response = {
            "data": {
                "node": {
                    "id": "1",
                    "settings": {
                        "associations": [
                            {"type": "model", "priority": 0, "modelId": {"modelId": "a"}},
                            {"type": "model", "priority": 1, "modelId": {"modelId": "b"}},
                        ],
                    },
                },
                "updateModel": {"id": "1"},
            }
        }
        session = FakeSession(FakeResponse(body=response))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        client.models.remove_rule("1", 1)

        associations = session.posts[1]["json"]["variables"]["input"]["settings"]["associations"]
        self.assertEqual([item["modelId"]["modelId"] for item in associations], ["b"])
        self.assertEqual(associations[0]["priority"], 0)

    def test_model_channels_executes_query_from_associations(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "queryModelChannelConnections": [
                            {
                                "priority": 1,
                                "channel": {"id": "10", "name": "openai", "type": "openai", "status": "enabled"},
                                "models": [{"requestModel": "gpt-4o-mini", "actualModel": "gpt-4o-mini", "source": "model"}],
                            }
                        ]
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        associations = [{"type": "model", "priority": 1, "modelId": {"modelId": "gpt-4o-mini"}}]

        result = client.models.channels(associations=associations)

        self.assertEqual(result[0]["channel"]["name"], "openai")
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "QueryModelChannelConnections")
        self.assertEqual(request["json"]["variables"], {"associations": associations})

    def test_unassociated_channels_executes_query(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "queryUnassociatedChannels": [
                            {"channel": {"id": "1", "name": "test", "type": "openai", "status": "enabled"}, "models": ["gpt-4"]}
                        ]
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.unassociated_channels()

        self.assertEqual(result[0]["models"], ["gpt-4"])
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "QueryUnassociatedChannels")
        self.assertEqual(request["json"]["variables"], {})

    def test_fastest_models_executes_query(self):
        session = FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "fastestModels": [
                            {
                                "modelId": "gpt-4o-mini",
                                "modelName": "GPT-4o mini",
                                "throughput": 100.0,
                                "tokensCount": 1000,
                                "latencyMs": 10.0,
                                "requestCount": 3,
                            }
                        ]
                    }
                }
            )
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.models.fastest(time_window="month", limit=10)

        self.assertEqual(result[0]["modelId"], "gpt-4o-mini")
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetFastestModels")
        self.assertEqual(request["json"]["variables"], {"input": {"timeWindow": "month", "limit": 10}})

    def test_requests_list_executes_query_with_filters(self):
        session = FakeSession(FakeResponse(body={"data": {"requests": {"edges": [], "totalCount": 0}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.requests.list(
            first=10,
            after="cursor-1",
            status_in=["failed"],
            source_in=["api"],
            channel_id="channel-1",
            project_id="project-1",
            model_id="gpt-4o-mini",
            trace_id="trace-node-1",
            created_after="2026-06-01T00:00:00Z",
            created_before="2026-06-09T00:00:00Z",
        )

        self.assertEqual(result["totalCount"], 0)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetRequests")
        self.assertEqual(
            request["json"]["variables"],
            {
                "first": 10,
                "after": "cursor-1",
                "orderBy": {"field": "CREATED_AT", "direction": "DESC"},
                "where": {
                    "statusIn": ["failed"],
                    "sourceIn": ["api"],
                    "channelID": "channel-1",
                    "projectID": "project-1",
                    "modelID": "gpt-4o-mini",
                    "traceID": "trace-node-1",
                    "createdAtGTE": "2026-06-01T00:00:00Z",
                    "createdAtLTE": "2026-06-09T00:00:00Z",
                },
            },
        )

    def test_request_get_uses_content_query_only_when_requested(self):
        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "r1"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        self.assertEqual(client.requests.get("r1"), {"id": "r1"})
        self.assertEqual(session.posts[0]["json"]["operationName"], "GetRequest")

        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "r1", "requestBody": {}}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        self.assertEqual(client.requests.get("r1", include_content=True)["id"], "r1")
        self.assertEqual(session.posts[0]["json"]["operationName"], "GetRequestWithContent")

    def test_request_executions_executes_query(self):
        session = FakeSession(
            FakeResponse(body={"data": {"node": {"executions": {"edges": [], "totalCount": 0}}}})
        )
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        result = client.requests.executions("r1", first=5, status_in=["failed"], channel_id="channel-1")

        self.assertEqual(result["totalCount"], 0)
        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetRequestExecutions")
        self.assertEqual(
            request["json"]["variables"],
            {
                "first": 5,
                "orderBy": {"field": "CREATED_AT", "direction": "DESC"},
                "requestID": "r1",
                "where": {"statusIn": ["failed"], "channelID": "channel-1"},
            },
        )

    def test_usage_logs_list_and_get_execute_queries(self):
        session = FakeSession(FakeResponse(body={"data": {"usageLogs": {"edges": [], "totalCount": 0}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        client.usage_logs.list(first=5, source_in=["api"], request_id="r1", channel_id="channel-1")

        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetUsageLogs")
        self.assertEqual(
            request["json"]["variables"],
            {
                "first": 5,
                "orderBy": {"field": "CREATED_AT", "direction": "DESC"},
                "where": {"sourceIn": ["api"], "requestID": "r1", "channelID": "channel-1"},
            },
        )

        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "u1"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))
        self.assertEqual(client.usage_logs.get("u1"), {"id": "u1"})
        self.assertEqual(session.posts[0]["json"]["operationName"], "GetUsageLog")

    def test_traces_list_maps_request_filter(self):
        session = FakeSession(FakeResponse(body={"data": {"traces": {"edges": [], "totalCount": 0}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        client.traces.list(
            first=5,
            trace_id="at-1",
            thread_id="thread-1",
            request_id="request-1",
            project_id="project-1",
            created_after="2026-06-01T00:00:00Z",
            created_before="2026-06-09T00:00:00Z",
        )

        request = session.posts[0]
        self.assertEqual(request["json"]["operationName"], "GetTraces")
        self.assertEqual(
            request["json"]["variables"],
            {
                "first": 5,
                "orderBy": {"field": "CREATED_AT", "direction": "DESC"},
                "where": {
                    "traceID": "at-1",
                    "threadID": "thread-1",
                    "hasRequestsWith": [{"id": "request-1"}],
                    "projectID": "project-1",
                    "createdAtGTE": "2026-06-01T00:00:00Z",
                    "createdAtLTE": "2026-06-09T00:00:00Z",
                },
            },
        )

    def test_trace_get_executes_query(self):
        session = FakeSession(FakeResponse(body={"data": {"node": {"id": "t1"}}}))
        client = AxonHubClient(GraphQLTransport("https://example.com", token="secret", session=session))

        self.assertEqual(client.traces.get("t1"), {"id": "t1"})
        self.assertEqual(session.posts[0]["json"]["operationName"], "GetTrace")

    def test_diagnostics_channel_health_aggregates_recent_failures(self):
        client = FakeInventoryClient()
        diagnostics = DiagnosticsAPI(client)

        result = diagnostics.channel_health(first=2, time_window="week", min_success_rate=0.95, recent_failures=3)

        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["critical"], 1)
        broken = [item for item in result["channels"] if item["id"] == "2"][0]
        self.assertIn("low_success_rate", broken["issues"])
        self.assertIn("upstream timeout", broken["recentErrorReasons"])
        self.assertEqual(client.requests.list_calls[0], {"first": 3, "status_in": ["failed"], "channel_id": "1"})

    def test_smoke_test_run_collects_read_only_steps(self):
        result = SmokeTestAPI(FakeSmokeClient()).run()

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "read-only")
        self.assertEqual(
            [step["name"] for step in result["steps"]],
            [
                "auth.status",
                "auth.whoami",
                "inventory.summary",
                "requests.list",
                "usage_logs.list",
                "traces.list",
                "diagnostics.channel_health",
            ],
        )


if __name__ == "__main__":
    unittest.main()
