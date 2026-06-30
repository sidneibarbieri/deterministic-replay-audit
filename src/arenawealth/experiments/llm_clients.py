"""Provider clients for collecting advisor benchmark runs.

The benchmark itself is provider-agnostic. This module keeps the HTTP details at
the collection boundary so Azure pilots, OpenAI runs, and Anthropic runs produce
the same cached record shape for the deterministic offline audit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

# Generous so the cap never binds. For reasoning models the OpenAI
# `max_completion_tokens` budget covers *reasoning + visible output together*, so a
# tight value (e.g. 500) lets internal reasoning starve the answer and we would
# measure truncation, not model behavior. Non-reasoning models stop well before
# this ceiling, so a shared high value keeps every model on an equal footing while
# guaranteeing no completion is cut off. Truncation is asserted to be zero in the
# collected runs.
ADVISOR_MAX_OUTPUT_TOKENS = 4000
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    usage: dict[str, Any]
    # True when the provider stopped the completion at the token ceiling rather
    # than because the model finished. A truncated run measures the cap, not the
    # model, so the collector records this and the audit asserts it never happens.
    truncated: bool = False


class AdvisorLLMClient(Protocol):
    # Read-only members so frozen dataclasses and Azure's computed `model`
    # property satisfy the protocol.
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def complete(self, prompt: str, temperature: float) -> LLMCompletion:
        """Return one completion. HTTP errors are intentionally not masked."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"missing environment variable: {name}")
    return value


def _optional_model(cli_model: str | None, primary_env: str, fallback: str) -> str:
    return cli_model or os.getenv(primary_env) or fallback


@dataclass(frozen=True)
class AzureOpenAIClient:
    endpoint: str
    api_key: str
    api_version: str
    deployment: str

    provider: str = "azure"

    @property
    def model(self) -> str:
        return self.deployment

    @classmethod
    def from_env(cls, model: str | None = None) -> AzureOpenAIClient:
        deployment = (
            model or os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_OPENAI_MODEL")
        )
        if not deployment:
            raise RuntimeError(
                "missing Azure deployment: set AZURE_OPENAI_DEPLOYMENT or pass --model"
            )
        return cls(
            endpoint=_require_env("AZURE_OPENAI_ENDPOINT").rstrip("/"),
            api_key=_require_env("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            deployment=deployment,
        )

    def complete(self, prompt: str, temperature: float) -> LLMCompletion:
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
        response = httpx.post(
            url,
            params={"api-version": self.api_version},
            headers={"api-key": self.api_key, "content-type": "application/json"},
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": ADVISOR_MAX_OUTPUT_TOKENS,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        return LLMCompletion(
            text=body["choices"][0]["message"]["content"],
            usage=body.get("usage", {}),
            truncated=_chat_truncated(body),
        )


@dataclass(frozen=True)
class OpenAIChatClient:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    provider: str = "openai"

    @classmethod
    def from_env(cls, model: str | None = None) -> OpenAIChatClient:
        return cls(
            api_key=_require_env("OPENAI_API_KEY"),
            model=_optional_model(model, "OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        )

    def complete(self, prompt: str, temperature: float) -> LLMCompletion:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_completion_tokens": ADVISOR_MAX_OUTPUT_TOKENS,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        return LLMCompletion(
            text=body["choices"][0]["message"]["content"],
            usage=body.get("usage", {}),
            truncated=_chat_truncated(body),
        )


@dataclass(frozen=True)
class AnthropicMessagesClient:
    api_key: str
    model: str
    api_version: str = "2023-06-01"
    base_url: str = "https://api.anthropic.com"
    provider: str = "anthropic"

    @classmethod
    def from_env(cls, model: str | None = None) -> AnthropicMessagesClient:
        return cls(
            api_key=_require_env("ANTHROPIC_API_KEY"),
            model=_optional_model(model, "ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            api_version=os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/"),
        )

    def complete(self, prompt: str, temperature: float) -> LLMCompletion:
        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": ADVISOR_MAX_OUTPUT_TOKENS,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        return LLMCompletion(
            text=_anthropic_text(body),
            usage=body.get("usage", {}),
            truncated=body.get("stop_reason") == "max_tokens",
        )


def _chat_truncated(body: dict[str, Any]) -> bool:
    """True when an OpenAI/Azure chat completion stopped at the token ceiling."""
    choices = body.get("choices") or [{}]
    return bool(choices[0].get("finish_reason") == "length")


def _anthropic_text(body: dict[str, Any]) -> str:
    blocks = body.get("content", [])
    texts = [
        str(block["text"])
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block
    ]
    if not texts:
        raise ValueError("Anthropic response did not include a text block")
    return "\n".join(texts)


def build_llm_client(provider: str, model: str | None = None) -> AdvisorLLMClient:
    normalized = provider.strip().lower()
    if normalized == "azure":
        return AzureOpenAIClient.from_env(model)
    if normalized == "openai":
        return OpenAIChatClient.from_env(model)
    if normalized == "anthropic":
        return AnthropicMessagesClient.from_env(model)
    raise ValueError(f"unsupported LLM provider: {provider}")
