import unittest

from axonhub_client.client import AxonHubClient, DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from axonhub_client.discovery import discover_supported_models, normalize_channel_type
from axonhub_client.exceptions import ConfigurationError, GraphQLError
from axonhub_client.transport import GraphQLTransport, extract_operation_name
from tests.transport_fakes import *


class ChannelClientTest(unittest.TestCase):
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

