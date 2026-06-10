import unittest

from axonhub_client.client import AxonHubClient, DiagnosticsAPI, InventoryAPI, SmokeTestAPI
from axonhub_client.discovery import discover_supported_models, normalize_channel_type
from axonhub_client.exceptions import ConfigurationError, GraphQLError
from axonhub_client.transport import GraphQLTransport, extract_operation_name
from tests.transport_fakes import *


class ObservabilityClientTest(unittest.TestCase):
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
