import json
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from axonhub_client import queries
from axonhub_client.cli import (
    _handle_delete_channels,
    _handle_delete_disabled_channel_api_keys,
    _handle_delete_models,
    _handle_enable_selected_channel_api_keys,
    _handle_login,
    _handle_logout,
    _handle_model_rule_action,
    _handle_set_model_rules,
    _make_client,
    _validate_login_base_url,
    _validate_login_field,
    build_create_channel_input,
    build_parser,
    load_bulk_create_models_input,
    load_bulk_ordering_input,
    load_channels_import_payload,
    load_create_model_input,
    load_session,
    load_update_model_input,
    main,
    normalize_bulk_create_input,
    sanitize,
    save_session,
)
from axonhub_client.exceptions import ConfigurationError, SESSION_RELOGIN_MESSAGE
from tests.cli_fakes import *


class ObservabilityCLITest(unittest.TestCase):
    def test_api_keys_list_cli_maps_filters(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "api-keys",
                "list",
                "--first",
                "50",
                "--after",
                "cursor-1",
                "--status",
                "enabled",
                "--type",
                "service_account",
                "--name",
                "prod",
                "--project-id",
                "project-1",
                "--user-id",
                "user-1",
            ]
        )
        client = FakeAPIKeysClient()

        result = args.handler(client, args)

        self.assertEqual(result, {"edges": [], "totalCount": 0})
        self.assertEqual(
            client.api_keys.calls,
            [
                (
                    "list",
                    {
                        "first": 50,
                        "after": "cursor-1",
                        "status": "enabled",
                        "type_": "service_account",
                        "name": "prod",
                        "project_id": "project-1",
                        "user_id": "user-1",
                    },
                )
            ],
        )

    def test_api_keys_read_cli_commands_call_client(self):
        parser = build_parser()
        client = FakeAPIKeysClient()
        expected_calls = [
            ("get", {"id": "api-key-1"}),
            ("quota_usage", {"id": "api-key-1"}),
            ("profile_templates", {"first": 25, "project_id": "project-1", "name": "default"}),
        ]

        for argv in (
            ["api-keys", "get", "api-key-1"],
            ["api-keys", "quota", "api-key-1"],
            ["api-keys", "templates", "--first", "25", "--project-id", "project-1", "--name", "default"],
        ):
            args = parser.parse_args(argv)
            args.handler(client, args)

        self.assertEqual(client.api_keys.calls, expected_calls)

    def test_request_cli_commands_call_client(self):
        parser = build_parser()
        client = FakeRequestsClient()

        args = parser.parse_args(
            [
                "requests",
                "list",
                "--first",
                "25",
                "--after",
                "cursor-1",
                "--status",
                "failed",
                "--source",
                "api",
                "--channel-id",
                "channel-1",
                "--project-id",
                "project-1",
                "--model",
                "gpt-4o-mini",
                "--trace-id",
                "trace-1",
                "--created-after",
                "2026-06-01T00:00:00Z",
                "--created-before",
                "2026-06-09T00:00:00Z",
            ]
        )
        args.handler(client, args)
        args = parser.parse_args(["requests", "get", "request-1", "--include-content"])
        args.handler(client, args)
        args = parser.parse_args(["requests", "executions", "request-1", "--status", "failed", "--channel-id", "channel-1"])
        args.handler(client, args)

        self.assertEqual(
            client.requests.calls,
            [
                (
                    "list",
                    {
                        "first": 25,
                        "after": "cursor-1",
                        "status_in": ["failed"],
                        "source_in": ["api"],
                        "channel_id": "channel-1",
                        "project_id": "project-1",
                        "model_id": "gpt-4o-mini",
                        "trace_id": "trace-1",
                        "created_after": "2026-06-01T00:00:00Z",
                        "created_before": "2026-06-09T00:00:00Z",
                    },
                ),
                ("get", {"id": "request-1", "include_content": True}),
                (
                    "executions",
                    {
                        "id": "request-1",
                        "first": 100,
                        "after": None,
                        "status_in": ["failed"],
                        "channel_id": "channel-1",
                    },
                ),
            ],
        )

    def test_usage_logs_cli_commands_call_client(self):
        parser = build_parser()
        client = FakeUsageLogsClient()

        args = parser.parse_args(
            [
                "usage",
                "logs",
                "list",
                "--first",
                "25",
                "--request-id",
                "request-1",
                "--source",
                "api",
                "--channel-id",
                "channel-1",
                "--project-id",
                "project-1",
                "--model",
                "gpt-4o-mini",
            ]
        )
        args.handler(client, args)
        args = parser.parse_args(["usage", "logs", "get", "usage-1"])
        args.handler(client, args)

        self.assertEqual(
            client.usage_logs.calls,
            [
                (
                    "list",
                    {
                        "first": 25,
                        "after": None,
                        "source_in": ["api"],
                        "channel_id": "channel-1",
                        "project_id": "project-1",
                        "request_id": "request-1",
                        "model_id": "gpt-4o-mini",
                        "created_after": None,
                        "created_before": None,
                    },
                ),
                ("get", {"id": "usage-1"}),
            ],
        )

    def test_traces_cli_maps_request_filter(self):
        parser = build_parser()
        client = FakeTracesClient()

        args = parser.parse_args(
            [
                "traces",
                "list",
                "--first",
                "10",
                "--trace-id",
                "at-1",
                "--thread-id",
                "thread-1",
                "--request-id",
                "request-1",
                "--project-id",
                "project-1",
                "--created-after",
                "2026-06-01T00:00:00Z",
                "--created-before",
                "2026-06-09T00:00:00Z",
            ]
        )
        args.handler(client, args)
        args = parser.parse_args(["traces", "get", "trace-node-1"])
        args.handler(client, args)

        self.assertEqual(
            client.traces.calls,
            [
                (
                    "list",
                    {
                        "first": 10,
                        "after": None,
                        "trace_id": "at-1",
                        "thread_id": "thread-1",
                        "request_id": "request-1",
                        "project_id": "project-1",
                        "created_after": "2026-06-01T00:00:00Z",
                        "created_before": "2026-06-09T00:00:00Z",
                    },
                ),
                ("get", {"id": "trace-node-1"}),
            ],
        )

    def test_diagnostics_and_smoke_cli_commands_call_client(self):
        parser = build_parser()
        diagnostics_client = FakeDiagnosticsClient()
        args = parser.parse_args(
            [
                "diagnostics",
                "channel-health",
                "--channel-id",
                "channel-1",
                "--limit",
                "10",
                "--window",
                "week",
                "--min-success-rate",
                "0.9",
                "--recent-failures",
                "3",
            ]
        )
        args.handler(diagnostics_client, args)
        self.assertEqual(
            diagnostics_client.diagnostics.calls,
            [
                (
                    "channel_health",
                    {
                        "channel_id": "channel-1",
                        "first": 10,
                        "time_window": "week",
                        "min_success_rate": 0.9,
                        "recent_failures": 3,
                    },
                )
            ],
        )

        smoke_client = FakeSmokeTestClient()
        args = parser.parse_args(["smoke", "read-only"])
        self.assertEqual(args.handler(smoke_client, args), {"ok": True})
        self.assertEqual(smoke_client.smoke_test.calls, [("run", {})])


if __name__ == "__main__":
    unittest.main()
