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
        self.patcher = patch("axonhub_client.cli.user_config_dir", return_value=self.config_dir)
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


class QuerySafetyTest(unittest.TestCase):
    def test_channel_queries_do_not_request_sensitive_fields(self):
        for query in (
            queries.QUERY_CHANNELS,
            queries.GET_CHANNEL,
            queries.ALL_CHANNEL_SUMMARYS,
            queries.CREATE_CHANNEL,
            queries.BULK_CREATE_CHANNELS,
            queries.BULK_IMPORT_CHANNELS,
            queries.UPDATE_CHANNEL,
            queries.UPDATE_CHANNEL_STATUS,
            queries.SAVE_CHANNEL_ENDPOINTS,
            queries.DELETE_CHANNEL,
            queries.TEST_CHANNEL,
            queries.TEST_CHANNEL_API_KEYS,
            queries.SYNC_CHANNEL_MODELS,
            queries.BULK_ARCHIVE_CHANNELS,
            queries.BULK_DISABLE_CHANNELS,
            queries.BULK_ENABLE_CHANNELS,
            queries.BULK_RECOVER_CHANNELS,
            queries.BULK_DELETE_CHANNELS,
            queries.BULK_UPDATE_CHANNEL_ORDERING,
            queries.DISABLE_CHANNEL_API_KEY,
            queries.ENABLE_CHANNEL_API_KEY,
            queries.ENABLE_ALL_CHANNEL_API_KEYS,
            queries.ENABLE_SELECTED_CHANNEL_API_KEYS,
            queries.DELETE_DISABLED_CHANNEL_API_KEYS,
            queries.MODELS,
            queries.GET_MODEL,
            queries.CREATE_MODEL,
            queries.BULK_CREATE_MODELS,
            queries.UPDATE_MODEL,
            queries.UPDATE_MODEL_STATUS,
            queries.DELETE_MODEL,
            queries.BULK_ARCHIVE_MODELS,
            queries.BULK_DISABLE_MODELS,
            queries.BULK_ENABLE_MODELS,
            queries.BULK_DELETE_MODELS,
            queries.QUERY_MODEL_CHANNEL_CONNECTIONS,
            queries.QUERY_UNASSOCIATED_CHANNELS,
            queries.FASTEST_MODELS,
        ):
            self.assertNotIn("credentials", query)
            self.assertNotIn("apiKey", query)
            self.assertNotIn("apiKeys", query)
            self.assertNotIn("disabledAPIKeys", query)
            self.assertNotIn("password", query)

    def test_api_key_queries_do_not_select_raw_key_field(self):
        for query in (
            queries.API_KEYS,
            queries.GET_API_KEY,
            queries.API_KEY_QUOTA_USAGES,
            queries.API_KEY_PROFILE_TEMPLATES,
            queries.REQUESTS,
            queries.GET_REQUEST,
            queries.GET_REQUEST_WITH_CONTENT,
            queries.REQUEST_EXECUTIONS,
            queries.USAGE_LOGS,
            queries.GET_USAGE_LOG,
            queries.TRACES,
            queries.GET_TRACE,
        ):
            self.assertNotIn("credentials", query)
            self.assertNotIn("disabledAPIKeys", query)
            self.assertNotIn("password", query)
            _assert_field_not_selected(self, query, "key")

    def test_request_get_default_does_not_select_content_fields(self):
        for field in ("requestHeaders", "requestBody", "responseBody", "responseChunks"):
            _assert_field_not_selected(self, queries.GET_REQUEST, field)

    def test_request_get_with_content_selects_content_fields(self):
        self.assertIn("requestHeaders", queries.GET_REQUEST_WITH_CONTENT)
        self.assertIn("requestBody", queries.GET_REQUEST_WITH_CONTENT)
        self.assertIn("responseBody", queries.GET_REQUEST_WITH_CONTENT)
        self.assertIn("responseChunks", queries.GET_REQUEST_WITH_CONTENT)

    def test_sanitize_redacts_sensitive_keys(self):
        data = {
            "key": "secret",
            "token": "secret",
            "nested": {"apiKey": "secret", "name": "visible"},
            "variables": {"keys": ["sk-a", "sk-b"]},
            "items": [{"password": "secret"}],
        }

        self.assertEqual(
            sanitize(data),
            {
                "key": "***REDACTED***",
                "token": "***REDACTED***",
                "nested": {"apiKey": "***REDACTED***", "name": "visible"},
                "variables": {"keys": "***REDACTED***"},
                "items": [{"password": "***REDACTED***"}],
            },
        )

    def test_login_placeholder_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            _validate_login_field("email", "REPLACE_WITH_ADMIN_EMAIL")

        with self.assertRaises(ConfigurationError):
            _validate_login_field("password", "<password>")

        with self.assertRaises(ConfigurationError):
            _validate_login_base_url("https://axonhub.example.com")

    def test_missing_session_requires_login(self):
        with TempConfig():
            with self.assertRaisesRegex(ConfigurationError, "请先运行 axonhubclient auth login"):
                load_session()

    def test_invalid_session_requires_complete_fields(self):
        with TempConfig() as config_dir:
            config_dir.mkdir(parents=True)
            (config_dir / SESSION_FILENAME).write_text(
                '{"schemaVersion": 1, "baseUrl": "https://axonhub.test"}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "缺少 token"):
                load_session()

    def test_login_writes_session_without_password(self):
        fake_client = FakeLoginClient()
        args = Namespace(
            url="https://axonhub.test/",
            username="admin@example.com",
            password="secret-password",
            timeout=30,
        )

        with TempConfig() as config_dir:
            with patch("axonhub_client.cli.AxonHubClient.from_config", return_value=fake_client) as from_config:
                result = _handle_login(None, args)

            session_text = (config_dir / SESSION_FILENAME).read_text(encoding="utf-8")
            session = json.loads(session_text)

        from_config.assert_called_once_with("https://axonhub.test/", timeout=30)
        self.assertEqual(fake_client.auth.calls, [{"email": "admin@example.com", "password": "secret-password"}])
        self.assertTrue(result["success"])
        self.assertEqual(result["baseUrl"], "https://axonhub.test")
        self.assertNotIn("adminToken", result)
        self.assertEqual(session["baseUrl"], "https://axonhub.test")
        self.assertEqual(session["token"], "session-token")
        self.assertEqual(session["user"]["email"], "admin@example.com")
        self.assertNotIn("secret-password", session_text)

    def test_login_prompts_for_missing_fields(self):
        fake_client = FakeLoginClient()
        args = Namespace(url=None, username=None, password=None, timeout=30)

        with TempConfig():
            with patch("builtins.input", side_effect=["https://axonhub.test", "admin@example.com"]):
                with patch("getpass.getpass", return_value="secret-password") as getpass_mock:
                    with patch("axonhub_client.cli.AxonHubClient.from_config", return_value=fake_client):
                        _handle_login(None, args)

        getpass_mock.assert_called_once()
        self.assertEqual(fake_client.auth.calls, [{"email": "admin@example.com", "password": "secret-password"}])

    def test_logout_removes_saved_session(self):
        with TempConfig() as config_dir:
            save_session(
                {
                    "schemaVersion": 1,
                    "baseUrl": "https://axonhub.test",
                    "token": "session-token",
                    "savedAt": "2026-06-10T00:00:00Z",
                }
            )

            result = _handle_logout(None, Namespace())

            self.assertTrue(result["success"])
            self.assertFalse((config_dir / SESSION_FILENAME).exists())

    def test_make_client_reads_session_file(self):
        args = Namespace(timeout=12, context_project_id="project-1")

        with TempConfig():
            save_session(
                {
                    "schemaVersion": 1,
                    "baseUrl": "https://axonhub.test",
                    "token": "session-token",
                    "user": {"id": "user-1"},
                    "savedAt": "2026-06-10T00:00:00Z",
                }
            )
            with patch("axonhub_client.cli.AxonHubClient.from_config", return_value="client") as from_config:
                client = _make_client(args)

        self.assertEqual(client, "client")
        from_config.assert_called_once_with(
            "https://axonhub.test",
            admin_token="session-token",
            timeout=12,
            project_id="project-1",
        )

    def test_main_prompts_relogin_on_session_auth_errors(self):
        with TempConfig():
            save_session(
                {
                    "schemaVersion": 1,
                    "baseUrl": "https://axonhub.test",
                    "token": "expired-token",
                    "user": {"id": "user-1"},
                    "savedAt": "2026-06-10T00:00:00Z",
                }
            )
            stderr = StringIO()
            with patch("axonhub_client.cli.AxonHubClient.from_config", return_value=FakeAuthErrorClient()):
                with redirect_stderr(stderr):
                    code = main(["auth", "whoami"])

        self.assertEqual(code, 1)
        self.assertIn(SESSION_RELOGIN_MESSAGE, stderr.getvalue())

    def test_main_prompts_relogin_on_rest_auth_errors(self):
        with TempConfig():
            save_session(
                {
                    "schemaVersion": 1,
                    "baseUrl": "https://axonhub.test",
                    "token": "expired-token",
                    "user": {"id": "user-1"},
                    "savedAt": "2026-06-10T00:00:00Z",
                }
            )
            stderr = StringIO()
            with patch("axonhub_client.cli.AxonHubClient.from_config", return_value=FakeAuthErrorClient()):
                with redirect_stderr(stderr):
                    code = main(["auth", "status"])

        self.assertEqual(code, 1)
        self.assertIn(SESSION_RELOGIN_MESSAGE, stderr.getvalue())

    def test_build_create_channel_input_from_api_key_args(self):
        args = Namespace(
            type="openai",
            name="test-openai",
            channel_base_url="https://api.openai.com/v1",
            api_keys=["sk-a\nsk-b"],
            oauth_api_key=None,
            gcp_region=None,
            gcp_project_id=None,
            gcp_json=None,
            supported_models=["gpt-4o-mini,gpt-4.1-mini"],
            manual_models=None,
            default_test_model=None,
            tags=["cheap,us"],
            auto_sync_supported_models=False,
            auto_sync_model_pattern="",
            ordering_weight=10,
            remark="测试渠道",
            stream_policy="unlimited",
            settings_json=None,
            endpoints_json=None,
        )

        input_ = build_create_channel_input(args)

        self.assertEqual(input_["type"], "openai")
        self.assertEqual(input_["credentials"], {"apiKeys": ["sk-a", "sk-b"]})
        self.assertEqual(input_["supportedModels"], ["gpt-4o-mini", "gpt-4.1-mini"])
        self.assertEqual(input_["manualModels"], [])
        self.assertEqual(input_["defaultTestModel"], "gpt-4o-mini")
        self.assertEqual(input_["tags"], ["cheap", "us"])
        self.assertEqual(input_["policies"], {"stream": "unlimited"})

    def test_build_create_channel_input_discovers_supported_models(self):
        args = Namespace(
            type="newapi_channel_conn",
            name="test-newapi",
            channel_base_url="https://api.example.com/v1",
            api_keys=["sk-a\nsk-b"],
            oauth_api_key=None,
            gcp_region=None,
            gcp_project_id=None,
            gcp_json=None,
            supported_models=None,
            manual_models=None,
            default_test_model=None,
            tags=None,
            auto_sync_supported_models=True,
            auto_sync_model_pattern="",
            ordering_weight=None,
            remark=None,
            stream_policy=None,
            settings_json=None,
            endpoints_json=None,
            timeout=12,
        )

        with patch("axonhub_client.cli.discover_supported_models", return_value=["model-a", "model-b"]) as discover:
            input_ = build_create_channel_input(args)

        discover.assert_called_once_with(
            channel_type="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-a",
            timeout=12,
        )
        self.assertEqual(input_["type"], "openai")
        self.assertEqual(input_["supportedModels"], ["model-a", "model-b"])
        self.assertEqual(input_["manualModels"], [])
        self.assertEqual(input_["defaultTestModel"], "model-a")

    def test_build_create_channel_input_keeps_explicit_manual_models(self):
        args = Namespace(
            type="openai",
            name="test-openai",
            channel_base_url="https://api.openai.com/v1",
            api_keys=["sk-a"],
            oauth_api_key=None,
            gcp_region=None,
            gcp_project_id=None,
            gcp_json=None,
            supported_models=["gpt-4o-mini,gpt-4.1-mini"],
            manual_models=["gpt-4.1-mini"],
            default_test_model=None,
            tags=None,
            auto_sync_supported_models=False,
            auto_sync_model_pattern="",
            ordering_weight=None,
            remark=None,
            stream_policy=None,
            settings_json=None,
            endpoints_json=None,
        )

        input_ = build_create_channel_input(args)

        self.assertEqual(input_["supportedModels"], ["gpt-4o-mini", "gpt-4.1-mini"])
        self.assertEqual(input_["manualModels"], ["gpt-4.1-mini"])

    def test_old_write_confirmation_flags_are_rejected(self):
        parser = build_parser()

        old_argvs = [
            ["--base-url", "https://axonhub.test", "channels", "list"],
            ["--login-config", "login.json", "channels", "list"],
            ["channels", "delete", "channel-1", "--apply"],
            ["channels", "delete", "channel-1", "--confirm-delete"],
            ["models", "delete", "model-1", "--apply"],
            ["channels", "bulk-create"],
            ["models", "set-status", "model-1", "--status", "enabled"],
            [
                "channels",
                "create",
                "--type",
                "openai",
                "--name",
                "old-env",
                "--upstream-base-url",
                "https://api.example.com/v1",
                "--api-key-env",
                "UPSTREAM_KEY",
            ],
            ["channels", "keys", "disable", "channel-1", "--key-env", "TARGET_KEY"],
            ["channels", "keys", "enable-selected", "channel-1", "--keys-env", "TARGET_KEYS"],
        ]

        for argv in old_argvs:
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_consolidated_cli_names_parse(self):
        parser = build_parser()
        argvs = [
            ["channels", "create-many", "--input-json", "{}"],
            ["channels", "status", "channel-1", "enabled", "--confirm"],
            ["channels", "reorder", "--input-json", '{"channels": []}'],
            ["channels", "endpoints", "set", "channel-1", "--endpoints-json", "[]"],
            ["channels", "keys", "test", "channel-1", "--model", "gpt-4o-mini"],
            ["channels", "keys", "disable", "channel-1", "--key", "sk-target"],
            ["channels", "keys", "enable-all", "channel-1", "--confirm"],
            ["channels", "keys", "enable-selected", "channel-1", "--key", "sk-a", "--key", "sk-b"],
            ["channels", "keys", "prune-disabled", "channel-1", "--key", '["sk-a","sk-b"]'],
            ["channels", "models", "sync", "channel-1", "--pattern", "gpt-.*"],
            [
                "channels",
                "create",
                "--type",
                "openai",
                "--name",
                "auto-models",
                "--upstream-base-url",
                "https://api.example.com/v1",
                "--api-key",
                "sk-upstream",
            ],
            ["auth", "login", "--url", "https://axonhub.test", "--username", "admin@example.com", "--password", "pw"],
            ["models", "create-many", "--input-json", "[]"],
            ["models", "status", "model-1", "enabled", "--confirm"],
            ["models", "rules", "list", "model-1"],
            ["models", "rules", "preview", "model-1"],
            ["models", "rules", "replace", "model-1", "--associations-json", "[]"],
            ["models", "rules", "add", "model-1", "--association-json", "{}"],
            ["models", "rules", "unassociated"],
        ]

        for argv in argvs:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(hasattr(args, "handler"))

    def test_delete_channel_dry_run_describes_high_risk_mutation(self):
        args = Namespace(ids=["channel-1", "channel-1", "channel-2"], confirm=False)

        result = _handle_delete_channels(object(), args)

        self.assertEqual(result["operation"], "BulkDeleteChannels")
        self.assertEqual(result["variables"], {"ids": ["channel-1", "channel-2"]})
        self.assertIn("不可逆", result["effect"])

    def test_delete_disabled_channel_api_keys_dry_run_describes_high_risk_mutation(self):
        args = Namespace(id="channel-1", keys=["sk-a", "sk-a", "sk-b"], confirm=False)

        result = _handle_delete_disabled_channel_api_keys(object(), args)

        self.assertEqual(result["operation"], "DeleteDisabledChannelAPIKeys")
        self.assertEqual(result["variables"], {"channelID": "channel-1", "keys": ["sk-a", "sk-b"]})
        self.assertIn("高风险", result["effect"])

    def test_enable_selected_channel_api_keys_reads_json_arg(self):
        args = Namespace(id="channel-1", keys=['["sk-a", "sk-b"]'], confirm=False)

        result = _handle_enable_selected_channel_api_keys(object(), args)

        self.assertEqual(result["operation"], "EnableSelectedChannelAPIKeys")
        self.assertEqual(result["variables"], {"channelID": "channel-1", "keys": ["sk-a", "sk-b"]})

    def test_normalize_bulk_create_input_supports_snake_case(self):
        payload = {
            "type": "openai",
            "name": "bulk-openai",
            "base_url": "https://api.openai.com/v1",
            "api_keys": ["sk-a", "sk-b"],
            "supported_models": ["gpt-4o-mini"],
            "default_test_model": "gpt-4o-mini",
            "tags": ["prod"],
            "ordering_weight": 100,
        }

        input_ = normalize_bulk_create_input(payload)

        self.assertEqual(input_["baseURL"], "https://api.openai.com/v1")
        self.assertEqual(input_["apiKeys"], ["sk-a", "sk-b"])
        self.assertEqual(input_["supportedModels"], ["gpt-4o-mini"])
        self.assertEqual(input_["defaultTestModel"], "gpt-4o-mini")
        self.assertEqual(input_["orderingWeight"], 100)

    def test_load_channels_import_payload_normalizes_records(self):
        payload = [
            {
                "type": "openai",
                "name": "import-openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-a",
                "supported_models": ["gpt-4o-mini"],
                "default_test_model": "gpt-4o-mini",
            }
        ]

        input_ = load_channels_import_payload(json.dumps(payload), None)

        self.assertEqual(
            input_,
            {
                "channels": [
                    {
                        "type": "openai",
                        "name": "import-openai",
                        "baseURL": "https://api.openai.com/v1",
                        "apiKey": "sk-a",
                        "supportedModels": ["gpt-4o-mini"],
                        "defaultTestModel": "gpt-4o-mini",
                    }
                ]
            },
        )

    def test_load_bulk_ordering_input_accepts_array(self):
        payload = [
            {"id": "channel-1", "ordering_weight": 10},
            {"id": "channel-2", "orderingWeight": 20},
        ]

        input_ = load_bulk_ordering_input(json.dumps(payload), None)

        self.assertEqual(
            input_,
            {"channels": [{"id": "channel-1", "orderingWeight": 10}, {"id": "channel-2", "orderingWeight": 20}]},
        )

    def test_load_create_model_input_normalizes_snake_case(self):
        payload = {
            "developer": "openai",
            "model_id": "gpt-4o-mini",
            "type": "chat",
            "name": "GPT-4o mini",
            "icon": "OpenAI",
            "group": "openai",
            "model_card": {
                "reasoning": {"supported": False, "default": False},
                "toolCall": True,
                "temperature": True,
                "modalities": {"input": ["text"], "output": ["text"]},
                "cost": {"input": 0.15, "output": 0.6, "cacheRead": 0, "cacheWrite": 0},
                "limit": {"context": 128000, "output": 16384},
            },
            "settings": {"disableDeveloperSettingsInheritance": False, "associations": []},
        }

        input_ = load_create_model_input(json.dumps(payload), None)

        self.assertEqual(input_["modelID"], "gpt-4o-mini")
        self.assertIn("modelCard", input_)
        self.assertNotIn("model_id", input_)
        self.assertNotIn("model_card", input_)

    def test_load_create_model_input_rejects_status(self):
        payload = {
            "developer": "openai",
            "modelID": "gpt-4o-mini",
            "name": "GPT-4o mini",
            "icon": "OpenAI",
            "group": "openai",
            "modelCard": {},
            "settings": {"associations": []},
            "status": "enabled",
        }

        with self.assertRaises(ConfigurationError):
            load_create_model_input(json.dumps(payload), None)

    def test_load_bulk_create_models_input_accepts_array_and_object(self):
        model = {
            "developer": "openai",
            "modelID": "gpt-4o-mini",
            "name": "GPT-4o mini",
            "icon": "OpenAI",
            "group": "openai",
            "modelCard": {},
            "settings": {"associations": []},
        }

        self.assertEqual(load_bulk_create_models_input(json.dumps([model]), None), [model])
        self.assertEqual(load_bulk_create_models_input(json.dumps({"models": [model]}), None), [model])

    def test_load_update_model_input_normalizes_clear_remark(self):
        input_ = load_update_model_input('{"model_id":"gpt-4o-mini","clear_remark":true}', None)

        self.assertEqual(input_, {"modelID": "gpt-4o-mini", "clearRemark": True})

    def test_delete_model_dry_run_describes_high_risk_mutation(self):
        args = Namespace(ids=["model-1", "model-1", "model-2"], confirm=False)

        result = _handle_delete_models(object(), args)

        self.assertEqual(result["operation"], "BulkDeleteModels")
        self.assertEqual(result["variables"], {"ids": ["model-1", "model-2"]})
        self.assertIn("不可逆", result["effect"])

    def test_set_model_rules_dry_run_preserves_existing_settings(self):
        associations = [{"type": "model", "modelId": {"modelId": "gpt-4o-mini"}}]
        args = Namespace(id="1", model_id=False, associations_json=json.dumps(associations), associations_file=None, confirm=False)

        result = _handle_set_model_rules(object(), args)

        self.assertEqual(result["operation"], "UpdateModel")
        self.assertTrue(result["variables"]["preserveExistingSettings"])
        self.assertEqual(result["variables"]["input"], {"settings": {"associations": associations}})

    def test_model_rules_add_dry_run_uses_nested_action(self):
        association = {"type": "model", "modelId": {"modelId": "gpt-4o-mini"}}
        args = Namespace(
            id="1",
            rule_action="add",
            model_id=False,
            association_json=json.dumps(association),
            association_file=None,
            index=None,
            position=2,
            from_index=None,
            to_index=None,
            confirm=False,
        )

        result = _handle_model_rule_action(object(), args)

        self.assertEqual(result["operation"], "UpdateModel")
        self.assertEqual(result["variables"]["ruleAction"], "add")
        self.assertEqual(result["variables"]["association"], association)
        self.assertEqual(result["variables"]["position"], 2)
        self.assertTrue(result["variables"]["normalizePriorities"])

    def test_model_rules_remove_requires_index(self):
        args = Namespace(
            id="1",
            rule_action="remove",
            model_id=False,
            association_json=None,
            association_file=None,
            index=None,
            position=None,
            from_index=None,
            to_index=None,
            confirm=False,
        )

        with self.assertRaises(ConfigurationError):
            _handle_model_rule_action(object(), args)

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
