"""Unit tests for provider-agnostic advisor collection clients."""

import json

import pytest
from scripts.collect_advisor_runs import (
    CallBudget,
    CollectionConfig,
    cache_path,
    collect_run,
    legacy_cache_path,
    model_label,
    prompt_hash,
    safe_slug,
    validate_cached_prompt,
)

from arenawealth.experiments.llm_clients import (
    AnthropicMessagesClient,
    AzureOpenAIClient,
    OpenAIChatClient,
    _anthropic_text,
    build_llm_client,
)


def test_azure_client_uses_deployment_from_environment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat")

    client = AzureOpenAIClient.from_env()

    assert client.provider == "azure"
    assert client.model == "chat"
    assert client.api_version


def test_openai_client_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIChatClient.from_env("gpt-4o")


def test_anthropic_client_keeps_model_and_version(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("ANTHROPIC_VERSION", "2023-06-01")

    client = AnthropicMessagesClient.from_env()

    assert client.provider == "anthropic"
    assert client.model == "claude-test"
    assert client.api_version == "2023-06-01"


def test_build_llm_client_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unsupported LLM provider"):
        build_llm_client("local")


def test_anthropic_text_extracts_text_blocks():
    body = {
        "content": [
            {"type": "text", "text": '{"tickers":["MA"]}'},
            {"type": "tool_use", "name": "ignored"},
        ]
    }

    assert _anthropic_text(body) == '{"tickers":["MA"]}'


def test_cache_path_separates_provider_and_model(tmp_path):
    path = cache_path("azure", "chat/test", "quality additions", 2, "policy", tmp_path)

    assert path == tmp_path / "azure" / "chat_test" / "policy" / "quality_additions__run2.json"


def test_cache_path_separates_prompt_arms(tmp_path):
    bare = cache_path("azure", "chat", "s", 1, "bare", tmp_path)
    scaffold = cache_path("azure", "chat", "s", 1, "scaffold", tmp_path)

    assert bare != scaffold


def test_collect_run_reaudits_legacy_cache_with_prompt_drift(tmp_path):
    scenario = {
        "name": "legacy pilot",
        "cash": 900.0,
        "allowed_tickers": ["TSM"],
        "owned_tickers": [],
        "max_recommendations": 1,
        "available_fact_ids": [],
        "amounts_required": True,
    }
    frozen_prompt = "preserved pilot prompt"
    path = legacy_cache_path("azure", "chat", scenario["name"], 1, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "status": "collected",
                "prompt": frozen_prompt,
                "prompt_hash": prompt_hash(frozen_prompt),
                "parsed": {"tickers": ["TSM"], "amounts": [900.0], "cited_fact_ids": []},
            }
        ),
        encoding="utf-8",
    )

    record = collect_run(
        scenario,
        "azure",
        "chat",
        1,
        CollectionConfig(arm="policy", cache_root=tmp_path),
        CallBudget(1),
        None,
    )

    assert record["status"] == "collected"
    assert record["frozen_prompt_record"] is True


def test_cached_prompt_hash_mismatch_is_rejected(tmp_path):
    path = tmp_path / "run.json"
    record = {"prompt": "changed", "prompt_hash": prompt_hash("original")}

    with pytest.raises(ValueError, match="cached prompt hash mismatch"):
        validate_cached_prompt(record, path)


def test_model_label_defaults_from_provider_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")

    assert model_label("azure", None) == "chat"
    assert model_label("openai", None) == "gpt-test"
    assert model_label("anthropic", None) == "claude-test"
    assert safe_slug("model / x") == "model_x"


def test_model_label_uses_current_final_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    assert model_label("openai", None) == "gpt-5.5"
    assert model_label("anthropic", None) == "claude-opus-4-8"


def test_prompt_hash_changes_when_prompt_changes():
    assert prompt_hash("prompt v1") != prompt_hash("prompt v2")
    assert prompt_hash("prompt v1") == prompt_hash("prompt v1")
