"""Unit tests for offline advisor LLM budget estimation."""

from decimal import Decimal

import pytest

from arenawealth.experiments.llm_budget import (
    ProviderModel,
    calls_for_plan,
    estimate_budget,
    estimate_text_tokens,
    format_usd,
    pricing_for,
)

SCENARIOS = [
    {
        "name": "demo",
        "cash": 1000.0,
        "allowed_tickers": ["MA", "ADBE"],
        "owned_tickers": ["MSFT"],
        "available_fact_ids": ["fact_a"],
        "max_recommendations": 2,
    }
]


def test_pricing_contains_final_model_choices():
    openai_pricing = pricing_for(ProviderModel("openai", "gpt-5.5"))
    anthropic_pricing = pricing_for(ProviderModel("anthropic", "claude-opus-4-8"))

    assert openai_pricing.output_usd_per_mtok == Decimal("30.00")
    assert anthropic_pricing.input_usd_per_mtok == Decimal("5.00")


def test_unknown_pricing_fails_closed():
    with pytest.raises(ValueError, match="no pricing"):
        pricing_for(ProviderModel("openai", "unknown-model"))


def test_token_estimate_rounds_up():
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("abcde") == 2


def test_budget_scales_with_runs_and_providers():
    estimates = estimate_budget(
        SCENARIOS,
        [
            ProviderModel("openai", "gpt-5.5"),
            ProviderModel("anthropic", "claude-opus-4-8"),
        ],
        runs=3,
        max_output_tokens=500,
    )

    assert len(estimates) == 2
    assert estimates[0].calls == 3
    assert estimates[0].output_tokens == 1500
    assert all(estimate.total_cost_usd > Decimal("0") for estimate in estimates)

    # Cost scales with runs for a fixed provider, independent of which provider is pricier.
    single_run = estimate_budget(
        SCENARIOS, [ProviderModel("openai", "gpt-5.5")], runs=3, max_output_tokens=500
    )
    more_runs = estimate_budget(
        SCENARIOS, [ProviderModel("openai", "gpt-5.5")], runs=6, max_output_tokens=500
    )
    assert more_runs[0].total_cost_usd > single_run[0].total_cost_usd


def test_rejects_invalid_run_count():
    with pytest.raises(ValueError, match="runs"):
        estimate_budget(SCENARIOS, [ProviderModel("openai", "gpt-5.5")], runs=0)


def test_call_plan_and_formatting():
    assert calls_for_plan(scenario_count=3, runs=3, provider_count=2) == 18
    assert format_usd(Decimal("0.004321")) == "$0.0043"
    assert format_usd(Decimal("0.044321")) == "$0.04"
