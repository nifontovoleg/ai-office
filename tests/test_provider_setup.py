"""Offline configuration and credential-boundary checks; no model requests."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from tools import opencode


class ProviderSetupCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="office-provider-setup-")
        self.env_file = Path(self.temp.name) / ".env"

    def tearDown(self):
        self.temp.cleanup()

    def test_templates_are_disabled_and_contain_no_key(self):
        for path in (opencode.ROOT / ".env.example", opencode.ROOT / "config/openai.env.example", opencode.ROOT / "config/proxyapi.env.example", opencode.ROOT / "config/claude.env.example"):
            values = dotenv_values(path, interpolate=False)
            self.assertEqual(values["OFFICE_ENABLE_MODEL"], "false")
            self.assertFalse(values["OFFICE_MODEL_KEY"])
            settings = opencode.load_settings(path, {})
            self.assertFalse(opencode.summary(settings, None)["ready_for_opencode"])

    def test_proxy_model_namespace_and_responses_sdk_are_consistent(self):
        settings = opencode.load_settings(opencode.ROOT / "config/proxyapi.env.example", {})
        config = json.loads(Path(settings["OPENCODE_CONFIG"]).read_text())
        self.assertEqual(settings["OPENCODE_MODEL"], "proxyapi/openai/gpt-6.1-sol")
        self.assertEqual(config["provider"]["proxyapi"]["npm"], "@ai-sdk/openai")
        self.assertEqual(config["enabled_providers"], ["proxyapi"])

    def test_environment_overrides_local_file_without_interpolating_secret(self):
        self.env_file.write_text("OFFICE_MODEL_KEY='fake-${UNCHANGED}'\nOPENCODE_PROVIDER=openai\n")
        settings = opencode.load_settings(self.env_file, {})
        self.assertEqual(settings["OFFICE_MODEL_KEY"], "fake-${UNCHANGED}")
        settings = opencode.load_settings(self.env_file, {"OFFICE_MODEL_KEY": "fake-from-environment"})
        self.assertEqual(settings["OFFICE_MODEL_KEY"], "fake-from-environment")

    def test_untrusted_url_credentials_queries_and_non_https_are_rejected(self):
        for url in ("http://remote.example/v1", "https://user:fake-secret@example.test/v1", "https://example.test/v1?key=fake-secret", "https://example.test/v1#fake-secret", "https://example.test/v1/responses"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                opencode.load_settings(self.env_file, {"OPENCODE_BASE_URL": url})

    def test_mismatched_or_unregistered_models_are_rejected(self):
        for model in ("proxyapi/openai/gpt-6.1-sol", "openai/unregistered-model", ""):
            with self.subTest(model=model), self.assertRaises(ValueError):
                opencode.load_settings(self.env_file, {"OPENCODE_MODEL": model})

    def test_safe_summary_never_contains_key_and_never_claims_verified_access(self):
        settings = opencode.load_settings(self.env_file, {"OFFICE_MODEL_KEY": "fake-private-key"})
        result = opencode.summary(settings, "opencode")
        self.assertTrue(result["ready_for_opencode"])
        self.assertFalse(result["provider_access_verified"])
        self.assertNotIn("fake-private-key", json.dumps(result))

    def test_check_does_not_launch_any_process(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(opencode, "find_cli", return_value=None), patch.object(opencode.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(opencode.main(["--check", "--env-file", str(self.env_file)]), 0)
        run.assert_not_called()

    def test_start_without_key_does_not_launch(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(opencode, "find_cli", return_value="opencode"), patch.object(opencode.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(opencode.main(["--start", "--env-file", str(self.env_file)]), 1)
        run.assert_not_called()

    def test_invalid_configuration_error_does_not_echo_secret(self):
        self.env_file.write_text("OPENCODE_BASE_URL=https://user:fake-private-key@example.test/v1\n")
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(output):
            self.assertEqual(opencode.main(["--check", "--env-file", str(self.env_file)]), 1)
        self.assertNotIn("fake-private-key", output.getvalue())

    def test_explicit_start_passes_key_only_in_child_environment(self):
        self.env_file.write_text("OFFICE_MODEL_KEY=fake-private-key\n")
        with patch.dict("os.environ", {"OPENCODE_CONFIG_CONTENT": "untrusted override"}, clear=True), patch.object(opencode, "find_cli", return_value="opencode"), patch.object(opencode.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            run.return_value.returncode = 0
            self.assertEqual(opencode.main(["--start", "--env-file", str(self.env_file), "--project", self.temp.name]), 0)
        command = run.call_args.args[0]
        child_env = run.call_args.kwargs["env"]
        self.assertNotIn("fake-private-key", str(command))
        self.assertNotIn("fake-private-key", output.getvalue())
        self.assertEqual(child_env["OFFICE_MODEL_KEY"], "fake-private-key")
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", child_env)

    def test_chatgpt_template_uses_live_picker_without_api_overrides(self):
        settings = opencode.load_settings(opencode.ROOT / ".env.example", {
            "OPENCODE_PROVIDER": "openai", "OPENCODE_AUTH": "chatgpt",
            "OFFICE_MODEL_KEY": "fake-private-key", "OPENAI_API_KEY": "fake-api-key",
            "OPENCODE_CONFIG_CONTENT": "untrusted override",
        })
        result = opencode.summary(settings, "opencode")
        self.assertTrue(result["ready_for_opencode"])
        self.assertEqual(result["auth_method"], "chatgpt")
        self.assertFalse(result["key_present"])
        self.assertFalse(result["authentication_verified"])
        config = json.loads(Path(settings["OPENCODE_CONFIG"]).read_text())
        self.assertEqual(config["enabled_providers"], ["openai"])
        self.assertNotIn("provider", config)
        self.assertNotIn("model", config)
        self.assertNotIn("small_model", config)
        self.assertEqual(config["permission"]["edit"], "ask")
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", settings)

    def test_chatgpt_start_needs_no_key_and_never_injects_api_credentials(self):
        self.env_file.write_text("OPENCODE_AUTH=chatgpt\nOFFICE_MODEL_KEY=fake-private-key\n")
        inherited = {"OPENAI_API_KEY": "fake-api-key", "CODEX_API_KEY": "fake-codex-key",
                     "OPENAI_BASE_URL": "https://example.test/v1"}
        with patch.dict("os.environ", inherited, clear=True), patch.object(opencode, "find_cli", return_value="opencode"), patch.object(opencode.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            run.return_value.returncode = 0
            self.assertEqual(opencode.main(["--start", "--env-file", str(self.env_file), "--project", self.temp.name]), 0)
        self.assertEqual(run.call_args.args[0], ["opencode", str(Path(self.temp.name).resolve())])
        child_env = run.call_args.kwargs["env"]
        for key in ("OFFICE_MODEL_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENCODE_MODEL", "OPENCODE_SMALL_MODEL"):
            self.assertNotIn(key, child_env)
        self.assertIn("/connect", output.getvalue())
        self.assertNotIn("fake-", output.getvalue())

    def test_unknown_auth_or_chatgpt_with_another_provider_is_rejected(self):
        for inherited in ({"OPENCODE_AUTH": "unknown"}, {"OPENCODE_AUTH": "chatgpt", "OPENCODE_PROVIDER": "anthropic"}):
            with self.subTest(inherited=inherited), self.assertRaises(ValueError):
                opencode.load_settings(self.env_file, inherited)

    def test_free_template_pins_main_and_small_models_and_public_auth(self):
        inherited = {"OFFICE_MODEL_KEY": "fake-private-key", "OPENCODE_API_KEY": "fake-zen-key",
                     "OPENCODE_CONFIG_CONTENT": "untrusted override"}
        settings = opencode.load_settings(opencode.ROOT / ".env.example", inherited)
        state = opencode.summary(settings, "opencode")
        self.assertTrue(state["ready_for_opencode"])
        self.assertEqual(state["auth_method"], "free")
        self.assertFalse(state["key_present"])
        self.assertFalse(state["provider_access_verified"])
        config = json.loads(settings["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(config["model"], "opencode/big-pickle")
        self.assertEqual(config["small_model"], "opencode/big-pickle")
        self.assertEqual(config["enabled_providers"], ["opencode"])
        self.assertEqual(config["provider"]["opencode"]["whitelist"], ["big-pickle"])
        self.assertEqual(config["provider"]["opencode"]["options"]["apiKey"], "public")
        self.assertEqual(config["provider"]["opencode"]["options"]["baseURL"], "https://opencode.ai/zen/v1")
        self.assertNotIn("fake-", str(settings))
        self.assertEqual(inherited["OFFICE_MODEL_KEY"], "fake-private-key")

    def test_free_launch_forces_big_pickle_without_account_key(self):
        self.env_file.write_text("OPENCODE_PROVIDER=opencode\nOPENCODE_AUTH=free\n")
        with patch.dict("os.environ", {}, clear=True), patch.object(opencode, "find_cli", return_value="opencode"), patch.object(opencode.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            self.assertEqual(opencode.main(["--start", "--env-file", str(self.env_file), "--project", self.temp.name]), 0)
        self.assertEqual(run.call_args.args[0][-2:], ["--model", "opencode/big-pickle"])
        self.assertNotIn("OFFICE_MODEL_KEY", run.call_args.kwargs["env"])
        self.assertEqual(json.loads(run.call_args.kwargs["env"]["OPENCODE_CONFIG_CONTENT"])["small_model"], "opencode/big-pickle")

    def test_free_mode_rejects_paid_model_and_wrong_provider(self):
        for inherited in ({"OPENCODE_PROVIDER": "opencode", "OPENCODE_AUTH": "free", "OPENCODE_SMALL_MODEL": "opencode/gpt-6.1-sol"}, {"OPENCODE_AUTH": "free", "OPENCODE_PROVIDER": "openai"}):
            with self.subTest(inherited=inherited), self.assertRaises(ValueError):
                opencode.load_settings(self.env_file, inherited)
