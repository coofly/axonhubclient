import json
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import BytesIO, StringIO, TextIOWrapper
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


class ChannelCLITest(unittest.TestCase):
    def test_help_output_reconfigures_non_utf8_stream(self):
        stdout_buffer = BytesIO()
        stdout = TextIOWrapper(stdout_buffer, encoding="cp1252")
        stderr_buffer = BytesIO()
        stderr = TextIOWrapper(stderr_buffer, encoding="cp1252")

        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
            stdout.flush()

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("AxonHub Admin API 管理客户端", stdout_buffer.getvalue().decode("utf-8"))

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

        with patch("axonhub_client.cli_helpers.discover_supported_models", return_value=["model-a", "model-b"]) as discover:
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
