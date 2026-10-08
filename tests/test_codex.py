"""Codex subprocess and saved-login boundaries; no live inference in tests."""
import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend import codex
from backend.runtime import ModelAdapter, model_config
from tools import codex as launcher

ENV = {"OFFICE_ENABLE_MODEL": "true", "OFFICE_MODEL_PROTOCOL": "codex_cli", "OFFICE_MODEL_NAME": "gpt-6.1-sol", "OFFICE_CODEX_TIMEOUT_SECONDS": "300", "OFFICE_MODEL_URL": "", "OFFICE_MODEL_KEY": "fake-secret"}
PAYLOAD = {"instructions_md": "ROLE", "task": {"goal": "PRIVATE-GOAL"}}


def stream(content="Ответ Codex", usage=None):
    return (json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": content}}, ensure_ascii=False) + "\n" + json.dumps({"type": "turn.completed", "usage": usage}) + "\n").encode("utf-8")


class CodexSetupCase(unittest.TestCase):
    def test_environment_removes_api_credentials_without_mutating_source(self):
        source = {"PATH": "path", "CODEX_HOME": "saved-home", **{key: "fake-secret" for key in codex.API_ENV}}
        result = codex.child_environment(source)
        self.assertEqual(result, {"PATH": "path", "CODEX_HOME": "saved-home"})
        self.assertIn("OPENAI_API_KEY", source)

    def test_explicit_path_must_be_existing_absolute_native_executable(self):
        for path in ("relative.exe", str(Path(tempfile.gettempdir()) / "not-a-real-codex.exe")):
            self.assertIsNone(codex.find_cli({"OFFICE_CODEX_PATH": path}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codex.exe"
            path.touch()
            self.assertEqual(codex.find_cli({"OFFICE_CODEX_PATH": str(path)}), str(path))

    def test_login_status_is_captured_and_auth_errors_do_not_leak(self):
        with patch.object(codex.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"Logged in using ChatGPT", stderr=b"fake-secret")) as run:
            self.assertEqual(codex.check_login("codex", {"OFFICE_MODEL_KEY": "fake-secret"}), "chatgpt")
        self.assertNotIn("fake-secret", str(run.call_args.kwargs["env"]))
        with patch.object(codex.subprocess, "run", side_effect=OSError("fake-secret")):
            self.assertEqual(codex.check_login("codex"), "unavailable")

    def test_office_command_restricts_tools_and_keeps_context_out_of_arguments(self):
        command = codex.office_command("codex", "/scratch", "OFFICE-POLICY", ENV)
        self.assertIn("read-only", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertIn("project_doc_max_bytes=0", command)
        self.assertIn("shell_tool", command)
        self.assertIn("apps", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("fake-secret", str(command))
        self.assertNotIn("PRIVATE-GOAL", str(command))
        for model in ("--dangerously-bypass-approvals-and-sandbox", "bad model", "fake-secret\nvalue"):
            with self.assertRaises(ValueError):
                codex.model_option({"OFFICE_MODEL_NAME": model})

    def test_usage_does_not_double_count_cached_tokens(self):
        result = codex.parse_result(stream(usage={"input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 5}))
        self.assertEqual(result["usage"], {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105})
        self.assertIsNone(result["cost"])
        for usage in (None, {"input_tokens": True, "output_tokens": 5}, {"input_tokens": -1, "output_tokens": 5}):
            self.assertIsNone(codex.parse_result(stream(usage=usage))["usage"])

    def test_incomplete_error_malformed_or_tool_stream_is_rejected(self):
        outputs = [b"invalid fake-secret", b'[]', b'{"type":1}', b'{"type":"turn.failed","error":{"message":"fake-secret"}}', b'{"type":"item.started","item":{"type":"command_execution"}}', b'{"type":"turn.completed"}', stream(content=""), b"x" * (codex.MAX_RESULT_BYTES + 1)]
        for output in outputs:
            with self.subTest(prefix=output[:30]), self.assertRaises(ValueError) as raised:
                codex.parse_result(output)
            self.assertNotIn("fake-secret", str(raised.exception))

    def test_startup_notice_requires_successful_turn_and_runtime_errors_remain_fatal(self):
        notice = b'{"type":"item.completed","item":{"type":"error","message":"Optional code mode disabled"}}\n'
        self.assertEqual(codex.parse_result(notice + stream())["content"], "Ответ Codex")
        for data in (notice, b'{"type":"turn.started"}\n' + notice + stream()):
            with self.assertRaises(ValueError):
                codex.parse_result(data)

    def test_launcher_check_never_starts_model_execution(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), patch.object(launcher, "find_cli", return_value="codex"), patch.object(launcher, "check_login", return_value="chatgpt"), patch.object(launcher.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--check", "--env-file", str(Path(directory) / ".env")]), 0)
        run.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())["ready_for_codex"])
        self.assertFalse(json.loads(output.getvalue())["provider_access_verified"])

    def test_launcher_requires_chatgpt_and_existing_project(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), patch.object(launcher, "find_cli", return_value="codex"), patch.object(launcher, "check_login", return_value="api_key"), patch.object(launcher.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(["--start", "--env-file", str(Path(directory) / ".env")]), 1)
        run.assert_not_called()

    def test_interactive_launch_is_scoped_and_does_not_receive_api_keys(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"OPENAI_API_KEY": "fake-secret", "OFFICE_MODEL_NAME": "gpt-6.1-sol"}, clear=True), patch.object(launcher, "find_cli", return_value="codex"), patch.object(launcher, "check_login", return_value="chatgpt"), patch.object(launcher.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(launcher.main(["--start", "--env-file", str(Path(directory) / ".env"), "--project", directory]), 0)
        self.assertIn("workspace-write", run.call_args.args[0])
        self.assertIn("on-request", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"].get("OPENAI_API_KEY"), None)
        self.assertNotIn("fake-secret", output.getvalue())


class CodexRuntimeCase(unittest.IsolatedAsyncioTestCase):
    async def test_saved_chatgpt_dispatch_uses_stdin_scratch_and_safe_environment(self):
        async def runner(command, directory, env, timeout, prompt=None):
            self.assertTrue(Path(directory).is_dir())
            self.assertNotIn("fake-secret", str(env))
            if command[1:3] == ["login", "status"]:
                return 0, b"Logged in using ChatGPT", b""
            self.assertEqual(json.loads(prompt), PAYLOAD)
            self.assertNotIn("PRIVATE-GOAL", str(command))
            self.assertEqual(timeout, 300)
            return 0, stream(usage={"input_tokens": 10, "output_tokens": 2}), b""
        with patch.dict(os.environ, ENV), patch("backend.runtime.find_codex", return_value="codex"), patch.object(codex, "find_cli", return_value="codex"), patch.object(codex, "run_cli", side_effect=runner) as run:
            self.assertTrue(model_config()["available"])
            result = await ModelAdapter().execute(PAYLOAD, {})
        self.assertEqual(run.await_count, 2)
        self.assertEqual(result["usage"]["total_tokens"], 12)

    async def test_invalid_settings_stop_before_any_subprocess(self):
        for value in ("fake-secret", "29", "1801"):
            with patch.dict(os.environ, {**ENV, "OFFICE_CODEX_TIMEOUT_SECONDS": value}), patch.object(codex, "find_cli", return_value="codex"), patch.object(codex, "run_cli") as run, self.assertRaises(ValueError) as raised:
                await codex.CodexAdapter().execute(PAYLOAD, "POLICY")
            run.assert_not_called()
            self.assertNotIn("fake-secret", str(raised.exception))

    async def test_non_chatgpt_login_and_failed_execution_do_not_fall_back(self):
        for results in ([(0, b"Logged in using an API key fake-secret", b"")], [(0, b"Logged in using ChatGPT", b""), (1, b"fake-secret", b"fake-secret")]):
            with patch.dict(os.environ, ENV), patch.object(codex, "find_cli", return_value="codex"), patch.object(codex, "run_cli", side_effect=results), self.assertRaises(ValueError) as raised:
                await codex.CodexAdapter().execute(PAYLOAD, "POLICY")
            self.assertNotIn("fake-secret", str(raised.exception))

    async def test_timeout_and_shutdown_cancel_kill_the_owned_process(self):
        for error in (asyncio.TimeoutError(), asyncio.CancelledError()):
            process = SimpleNamespace(communicate=AsyncMock(side_effect=[error, (b"", b"")]), kill=unittest.mock.Mock())
            with patch.object(codex.asyncio, "create_subprocess_exec", return_value=process):
                with self.assertRaises(asyncio.CancelledError if isinstance(error, asyncio.CancelledError) else ValueError):
                    await codex.run_cli(["codex"], "/scratch", {}, 1, b"goal")
            process.kill.assert_called_once()
            self.assertEqual(process.communicate.await_count, 2)
