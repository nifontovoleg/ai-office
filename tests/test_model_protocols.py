"""Native Claude protocol contracts using HTTP MockTransport only."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from backend.runtime import ModelAdapter, model_config

CLAUDE_ENV = {
    "OFFICE_ENABLE_MODEL": "true",
    "OFFICE_MODEL_PROTOCOL": "anthropic_messages",
    "OFFICE_MODEL_URL": "https://api.anthropic.com/v1/messages",
    "OFFICE_MODEL_NAME": "claude-sonnet-5-5",
    "OFFICE_MODEL_KEY": "fake-private-key",
    "OFFICE_MODEL_MAX_TOKENS": "8192",
    "OFFICE_MODEL_TIMEOUT_SECONDS": "120",
}
PAYLOAD = {"instructions_md": "ROLE-INSTRUCTION", "task": {"goal": "TASK-CONTEXT"}}


class ClaudeProtocolCase(unittest.IsolatedAsyncioTestCase):
    async def execute_response(self, response, overrides=None):
        with patch.dict(os.environ, {**CLAUDE_ENV, **(overrides or {})}):
            return await ModelAdapter(httpx.MockTransport(lambda request: response)).execute(PAYLOAD, {})

    async def test_native_auth_system_context_text_blocks_and_reported_cache_usage(self):
        def responder(request):
            self.assertEqual(str(request.url), CLAUDE_ENV["OFFICE_MODEL_URL"])
            self.assertEqual(request.headers["x-api-key"], "fake-private-key")
            self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
            self.assertNotIn("authorization", request.headers)
            body = json.loads(request.content)
            self.assertEqual(body["model"], "claude-sonnet-5-5")
            self.assertEqual(body["max_tokens"], 8192)
            self.assertIn("ROLE-INSTRUCTION", body["system"])
            self.assertEqual(len(body["messages"]), 1)
            self.assertEqual(body["messages"][0]["role"], "user")
            self.assertNotIn("instructions_md", json.loads(body["messages"][0]["content"]))
            self.assertNotIn("fake-private-key", request.content.decode())
            return httpx.Response(200, json={"content": [{"type": "thinking", "thinking": "hidden"}, {"type": "text", "text": "First"}, {"type": "text", "text": "Second"}], "stop_reason": "end_turn", "usage": {"input_tokens": 20, "cache_read_input_tokens": 30, "cache_creation_input_tokens": 10, "output_tokens": 5}})
        with patch.dict(os.environ, CLAUDE_ENV):
            result = await ModelAdapter(httpx.MockTransport(responder)).execute(PAYLOAD, {})
        self.assertEqual(result["content"], "First\n\nSecond")
        self.assertEqual(result["usage"], {"prompt_tokens": 60, "completion_tokens": 5, "total_tokens": 65})
        self.assertIsNone(result["cost"])

    async def test_native_invalid_json_structure_and_empty_text_are_rejected(self):
        for data in ({}, {"content": "bad"}, {"content": [None]}, {"content": [{"type": "text", "text": 7}]}, {"content": [{"type": "thinking", "thinking": "no text"}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                await self.execute_response(httpx.Response(200, json=data))

    async def test_native_auth_errors_and_redirects_do_not_disclose_key_or_body(self):
        for response in (httpx.Response(401, text="fake-private-key"), httpx.Response(302, headers={"location": "https://example.test/fake-private-key"})):
            with self.subTest(status=response.status_code), self.assertRaises(ValueError) as raised:
                await self.execute_response(response)
            self.assertNotIn("fake-private-key", str(raised.exception))

    async def test_truncated_claude_result_is_not_treated_as_complete(self):
        with self.assertRaisesRegex(ValueError, "лимита токенов"):
            await self.execute_response(httpx.Response(200, json={"content": [{"type": "text", "text": "Partial"}], "stop_reason": "max_tokens"}))

    async def test_invalid_native_usage_is_not_invented(self):
        for usage in (None, {"input_tokens": -1, "output_tokens": 5}, {"input_tokens": True, "output_tokens": 5}, {"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": "bad"}):
            result = await self.execute_response(httpx.Response(200, json={"content": [{"type": "text", "text": "Result"}], "usage": usage}))
            self.assertIsNone(result["usage"])

    async def test_invalid_limits_and_unsupported_protocol_do_not_call_provider(self):
        for overrides in ({"OFFICE_MODEL_MAX_TOKENS": "fake-private-key"}, {"OFFICE_MODEL_MAX_TOKENS": "0"}, {"OFFICE_MODEL_TIMEOUT_SECONDS": "601"}, {"OFFICE_MODEL_PROTOCOL": "unsupported"}):
            with self.subTest(overrides=overrides), patch.dict(os.environ, {**CLAUDE_ENV, **overrides}), self.assertRaises(ValueError) as raised:
                await ModelAdapter(httpx.MockTransport(lambda request: self.fail("No HTTP request expected"))).execute(PAYLOAD, {})
            self.assertNotIn("fake-private-key", str(raised.exception))

    async def test_health_metadata_discloses_protocol_without_endpoint_or_key(self):
        with patch.dict(os.environ, CLAUDE_ENV):
            state = model_config()
        self.assertTrue(state["available"])
        self.assertEqual(state["protocol"], "anthropic_messages")
        self.assertFalse(state["verified"])
        self.assertNotIn("fake-private-key", json.dumps(state))
        self.assertNotIn("api.anthropic.com", json.dumps(state))
