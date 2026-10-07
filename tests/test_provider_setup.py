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
        for path in (opencode.ROOT / ".env.example", opencode.ROOT / "config/proxyapi.env.example", opencode.ROOT / "config/claude.env.example"):
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
