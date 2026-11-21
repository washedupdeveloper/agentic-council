"""Tests for the direct OpenAI-compatible reviewer adapter."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from council.agents.base import AgentOptions
from council.agents.direct import (
    DirectAdapter,
    DirectConfig,
    config_from_env,
    direct_runner,
)
from council.sample import ReviewerMissing

ENDPOINT = "https://api.example.test/v1/chat/completions"


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def config(model: str = "deepseek-v4.1-flash-1017", key: str = "secret") -> DirectConfig:
    return DirectConfig(base_url="https://api.example.test/v1", model=model, api_key=key)


class ConfigTests(unittest.TestCase):
    def test_requires_model_and_key(self) -> None:
        with self.assertRaises(ReviewerMissing) as caught:
            config_from_env({})
        self.assertIn("COUNCIL_DIRECT_MODEL", str(caught.exception))
        self.assertIn("COUNCIL_DIRECT_API_KEY", str(caught.exception))

    def test_reads_the_environment_with_a_surplus_default(self) -> None:
        parsed = config_from_env(
            {
                "COUNCIL_DIRECT_MODEL": "claude-fable-5.2",
                "COUNCIL_DIRECT_API_KEY": "k",
                "COUNCIL_DIRECT_MAX_TOKENS": "4096",
            }
        )
        self.assertEqual(parsed.model, "claude-fable-5.2")
        self.assertEqual(parsed.max_tokens, 4096)
        self.assertTrue(parsed.base_url.startswith("https://api.surplusintelligence.ai"))

    def test_bad_max_tokens_is_a_config_error(self) -> None:
        with self.assertRaises(ReviewerMissing):
            config_from_env(
                {
                    "COUNCIL_DIRECT_MODEL": "m",
                    "COUNCIL_DIRECT_API_KEY": "k",
                    "COUNCIL_DIRECT_MAX_TOKENS": "many",
                }
            )


class IdentityTests(unittest.TestCase):
    def test_key_is_not_part_of_the_identity(self) -> None:
        adapter = DirectAdapter()
        with mock.patch.dict(
            "os.environ",
            {
                "COUNCIL_DIRECT_MODEL": "m",
                "COUNCIL_DIRECT_API_KEY": "first",
                "COUNCIL_DIRECT_BASE_URL": "https://api.example.test/v1",
            },
            clear=True,
        ):
            first = adapter.identity(AgentOptions())
            os.environ["COUNCIL_DIRECT_API_KEY"] = "second"
            second = adapter.identity(AgentOptions())
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.agent, "direct")
        self.assertEqual(first.profile, "m")

    def test_model_and_endpoint_change_the_identity(self) -> None:
        adapter = DirectAdapter()
        with mock.patch.dict(
            "os.environ",
            {
                "COUNCIL_DIRECT_MODEL": "m1",
                "COUNCIL_DIRECT_API_KEY": "k",
                "COUNCIL_DIRECT_BASE_URL": "https://api.example.test/v1",
            },
            clear=True,
        ):
            one = adapter.identity(AgentOptions())
            os.environ["COUNCIL_DIRECT_MODEL"] = "m2"
            two = adapter.identity(AgentOptions())
            os.environ["COUNCIL_DIRECT_MODEL"] = "m1"
            os.environ["COUNCIL_DIRECT_BASE_URL"] = "https://other.test/v1"
            three = adapter.identity(AgentOptions())
        self.assertNotEqual(one.sha256, two.sha256)
        self.assertNotEqual(one.sha256, three.sha256)


class RunnerTests(unittest.TestCase):
    def test_posts_one_chat_completion(self) -> None:
        seen: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["headers"] = dict(request.header_items())
            seen["timeout"] = timeout
            return FakeResponse(
                json.dumps({"choices": [{"message": {"content": "review text"}}]})
            )

        runner = direct_runner(config(), timeout=42)
        with mock.patch("council.agents.direct.urllib.request.urlopen", fake_urlopen):
            answer = runner("the prompt")

        self.assertEqual(answer, "review text")
        self.assertEqual(seen["url"], ENDPOINT)
        self.assertEqual(seen["timeout"], 42)
        body = seen["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["model"], "deepseek-v4.1-flash-1017")
        self.assertEqual(body["messages"], [{"role": "user", "content": "the prompt"}])
        headers = seen["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers.get("Authorization"), "Bearer secret")

    def test_http_error_becomes_an_oserror_with_the_status(self) -> None:
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"error":"slow down"}')
            )

        with mock.patch("council.agents.direct.urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(OSError) as caught:
                direct_runner(config())("prompt")
        self.assertIn("429", str(caught.exception))
        self.assertIn("slow down", str(caught.exception))

    def test_malformed_body_is_an_oserror(self) -> None:
        with mock.patch(
            "council.agents.direct.urllib.request.urlopen",
            lambda request, timeout=None: FakeResponse("not json"),
        ):
            with self.assertRaises(OSError):
                direct_runner(config())("prompt")

    def test_empty_answer_is_rejected(self) -> None:
        with mock.patch(
            "council.agents.direct.urllib.request.urlopen",
            lambda request, timeout=None: FakeResponse(
                json.dumps({"choices": [{"message": {"content": "   "}}]})
            ),
        ):
            with self.assertRaises(OSError):
                direct_runner(config())("prompt")


class AvailabilityTests(unittest.TestCase):
    def test_unconfigured_is_unavailable_with_a_reason(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            available, detail = DirectAdapter().available(AgentOptions())
        self.assertFalse(available)
        self.assertIn("COUNCIL_DIRECT_MODEL", detail)

    def test_configured_is_available(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "COUNCIL_DIRECT_MODEL": "m",
                "COUNCIL_DIRECT_API_KEY": "k",
                "COUNCIL_DIRECT_BASE_URL": "https://api.example.test/v1",
            },
            clear=True,
        ):
            available, detail = DirectAdapter().available(AgentOptions())
        self.assertTrue(available)
        self.assertIn("model=m", detail)


if __name__ == "__main__":
    unittest.main()
