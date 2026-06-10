import unittest

from axonhub_client.client import AxonHubClient, DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from axonhub_client.discovery import discover_supported_models, normalize_channel_type
from axonhub_client.exceptions import ConfigurationError, GraphQLError
from axonhub_client.transport import GraphQLTransport, extract_operation_name
from tests.transport_fakes import *


class ModelAndAPIKeyClientTest(unittest.TestCase):
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

