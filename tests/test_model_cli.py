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


class ModelCLITest(unittest.TestCase):
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

