import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from axonhub_client import queries
from axonhub_client.cli import (
    SESSION_FILENAME,
    _handle_logout,
    _handle_login,
    _handle_delete_channels,
    _handle_delete_disabled_channel_api_keys,
    _handle_delete_models,
    _handle_model_rule_action,
    _handle_set_model_rules,
    _handle_enable_selected_channel_api_keys,
    _make_client,
    build_parser,
    load_bulk_ordering_input,
    load_bulk_create_models_input,
    load_channels_import_payload,
    load_create_model_input,
    load_update_model_input,
    load_session,
    main,
    _validate_login_base_url,
    _validate_login_field,
    build_create_channel_input,
    normalize_bulk_create_input,
    save_session,
    sanitize,
)
from axonhub_client.exceptions import ConfigurationError, GraphQLError, HTTPError, SESSION_RELOGIN_MESSAGE


__all__ = [
    "_assert_field_not_selected",
    "FakeAPIKeysAPI",
    "FakeAPIKeysClient",
    "FakeRequestsAPI",
    "FakeRequestsClient",
    "FakeUsageLogsAPI",
    "FakeUsageLogsClient",
    "FakeTracesAPI",
    "FakeTracesClient",
    "FakeDiagnosticsAPI",
    "FakeDiagnosticsClient",
    "FakeSmokeTestAPI",
    "FakeSmokeTestClient",
    "TempCwd",
    "TempConfig",
    "FakeLoginAuthAPI",
    "FakeLoginClient",
    "FakeAuthErrorClient",
]


def _assert_field_not_selected(test_case: unittest.TestCase, query: str, field: str) -> None:
    for line in query.splitlines():
        stripped = line.strip()
        test_case.assertNotEqual(stripped, field)
        test_case.assertFalse(stripped.startswith(f"{field} "))
        test_case.assertFalse(stripped.startswith(f"{field} {{"))


class FakeAPIKeysAPI:
    def __init__(self) -> None:
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {"edges": [], "totalCount": 0}

    def get(self, api_key_id):
        self.calls.append(("get", {"id": api_key_id}))
        return {"id": api_key_id}

    def quota_usage(self, api_key_id):
        self.calls.append(("quota_usage", {"id": api_key_id}))
        return []

    def profile_templates(self, **kwargs):
        self.calls.append(("profile_templates", kwargs))
        return {"edges": [], "totalCount": 0}


class FakeAPIKeysClient:
    def __init__(self) -> None:
        self.api_keys = FakeAPIKeysAPI()


class FakeRequestsAPI:
    def __init__(self) -> None:
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {"edges": [], "totalCount": 0}

    def get(self, request_id, *, include_content=False):
        self.calls.append(("get", {"id": request_id, "include_content": include_content}))
        return {"id": request_id}

    def executions(self, request_id, **kwargs):
        self.calls.append(("executions", {"id": request_id, **kwargs}))
        return {"edges": [], "totalCount": 0}


class FakeRequestsClient:
    def __init__(self) -> None:
        self.requests = FakeRequestsAPI()


class FakeUsageLogsAPI:
    def __init__(self) -> None:
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {"edges": [], "totalCount": 0}

    def get(self, usage_log_id):
        self.calls.append(("get", {"id": usage_log_id}))
        return {"id": usage_log_id}


class FakeUsageLogsClient:
    def __init__(self) -> None:
        self.usage_logs = FakeUsageLogsAPI()


class FakeTracesAPI:
    def __init__(self) -> None:
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {"edges": [], "totalCount": 0}

    def get(self, trace_id):
        self.calls.append(("get", {"id": trace_id}))
        return {"id": trace_id}


class FakeTracesClient:
    def __init__(self) -> None:
        self.traces = FakeTracesAPI()


class FakeDiagnosticsAPI:
    def __init__(self) -> None:
        self.calls = []

    def channel_health(self, **kwargs):
        self.calls.append(("channel_health", kwargs))
        return {"channels": []}


class FakeDiagnosticsClient:
    def __init__(self) -> None:
        self.diagnostics = FakeDiagnosticsAPI()


class FakeSmokeTestAPI:
    def __init__(self) -> None:
        self.calls = []

    def run(self):
        self.calls.append(("run", {}))
        return {"ok": True}


class FakeSmokeTestClient:
    def __init__(self) -> None:
        self.smoke_test = FakeSmokeTestAPI()


class TempCwd:
    def __enter__(self):
        self.previous = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        return Path(self.tmp.name)

    def __exit__(self, exc_type, exc, tb):
        os.chdir(self.previous)
        self.tmp.cleanup()


class TempConfig:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name) / "config"
        self.patcher = patch("axonhub_client.cli_session_output.user_config_dir", return_value=self.config_dir)
        self.patcher.start()
        return self.config_dir

    def __exit__(self, exc_type, exc, tb):
        self.patcher.stop()
        self.tmp.cleanup()


class FakeLoginAuthAPI:
    def __init__(self) -> None:
        self.calls = []

    def login(self, **kwargs):
        self.calls.append(kwargs)
        return {"token": "session-token", "user": {"id": "user-1", "email": kwargs["email"]}}


class FakeLoginClient:
    def __init__(self) -> None:
        self.auth = FakeLoginAuthAPI()


class FakeAuthErrorClient:
    class Auth:
        def whoami(self):
            raise GraphQLError("unauthenticated", is_auth_error=True)

        def status(self):
            raise HTTPError("unauthorized", status_code=401)

    def __init__(self) -> None:
        self.auth = self.Auth()

