"""OpenAI-compatible direct reviewer: one HTTP request per sample.

The Hermes adapter boots an agent process per sample, which is the right
default because it inherits the profile's model and tools. This adapter exists
for deployments that want a single model call with no agent boot: a review
sample is one prompt in, one answer out, and the shipped reviewer prompt
forbids tool calls anyway.

Configuration is environment-only so the adapter can be selected by name
without extending the CLI's option bag:

  COUNCIL_DIRECT_BASE_URL   default https://api.surplusintelligence.ai/v1
  COUNCIL_DIRECT_MODEL      required; the model id at that endpoint
  COUNCIL_DIRECT_API_KEY    required; sent as a bearer token
  COUNCIL_DIRECT_MAX_TOKENS optional; default 8192

The identity is the model, the endpoint and the prompt version. A key change
does not change the identity; a model or endpoint change does.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..sample import ReviewerMissing, Runner
from .base import AgentIdentity, AgentOptions

DEFAULT_BASE_URL = "https://api.surplusintelligence.ai/v1"
PROMPT_VERSION = "council-direct-v1"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.0


@dataclass(frozen=True, slots=True)
class DirectConfig:
    base_url: str
    model: str
    api_key: str
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def config_from_env(env: dict[str, str] | None = None) -> DirectConfig:
    source = os.environ if env is None else env
    base_url = (source.get("COUNCIL_DIRECT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    model = (source.get("COUNCIL_DIRECT_MODEL") or "").strip()
    api_key = (source.get("COUNCIL_DIRECT_API_KEY") or "").strip()
    missing = [
        name
        for name, value in (
            ("COUNCIL_DIRECT_MODEL", model),
            ("COUNCIL_DIRECT_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise ReviewerMissing(f"direct reviewer is not configured: {', '.join(missing)}")
    try:
        max_tokens = int(source.get("COUNCIL_DIRECT_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    except ValueError as exc:
        raise ReviewerMissing("COUNCIL_DIRECT_MAX_TOKENS must be an integer") from exc
    return DirectConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
    )


def direct_runner(config: DirectConfig, *, timeout: int = 900) -> Runner:
    """Return a prompt -> answer callable that speaks Chat Completions."""

    def run(prompt: str) -> str:
        payload = {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        request = urllib.request.Request(
            config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            finally:
                exc.close()
            raise OSError(
                f"direct {config.model} HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OSError(f"direct {config.model}: {exc}") from exc
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise OSError(
                f"direct {config.model} returned no assistant message"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise OSError(f"direct {config.model} returned an empty answer")
        return content

    return run


def _identity(config: DirectConfig) -> AgentIdentity:
    material = "|".join(
        (config.model, config.base_url, PROMPT_VERSION, f"{config.temperature:g}")
    )
    return AgentIdentity(
        agent="direct",
        profile=config.model,
        source=config.base_url,
        sha256=hashlib.sha256(material.encode("utf-8")).hexdigest()[:16],
    )


class DirectAdapter:
    """One OpenAI-compatible endpoint, selected as `--agent direct`."""

    name = "direct"
    description = "OpenAI-compatible endpoint, one request per sample"
    profile_required = False
    default_binary = ""

    def runner(self, options: AgentOptions) -> Runner:
        return direct_runner(config_from_env(), timeout=options.timeout)

    def identity(self, options: AgentOptions) -> AgentIdentity:
        return _identity(config_from_env())

    def available(self, options: AgentOptions) -> tuple[bool, str]:
        try:
            config = config_from_env()
        except (ReviewerMissing, OSError, ValueError) as exc:
            return False, str(exc)
        return True, f"{config.base_url}  model={config.model}"
