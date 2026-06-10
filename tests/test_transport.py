import unittest

from axonhub_client.client import AxonHubClient, DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from axonhub_client.discovery import discover_supported_models, normalize_channel_type
from axonhub_client.exceptions import ConfigurationError, GraphQLError
from axonhub_client.transport import GraphQLTransport, extract_operation_name
from tests.transport_fakes import *


class TransportCoreTest(unittest.TestCase):
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

