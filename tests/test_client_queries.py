import json
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from axonhub_client import queries
from axonhub_client.cli import (
    SESSION_FILENAME,
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


class QuerySafetyAndSessionTest(unittest.TestCase):
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
