"""Cost estimation for advisor LLM experiments.

The estimator is deliberately offline. It uses the frozen scenarios and the
configured output cap to estimate a conservative upper bound before any paid
provider call is authorized.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from arenawealth.experiments.advisor_prompts import build_prompt
from arenawealth.experiments.llm_clients import (
    ADVISOR_MAX_OUTPUT_TOKENS,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
)

MILLION_TOKENS = Decimal("1000000")


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal


@dataclass(frozen=True)
class ProviderModel:
    provider: str
    model: str


@dataclass(frozen=True)
class BudgetEstimate:
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    input_cost_usd: Decimal
    output_cost_usd: Decimal

    @property
    def total_cost_usd(self) -> Decimal:
        return self.input_cost_usd + self.output_cost_usd


# Pricing snapshot verified on 2026-06-19. Re-check provider pricing before a
# final paid collection.
PRICING: dict[tuple[str, str], ModelPricing] = {
    ("openai", "gpt-5.5"): ModelPricing(
        provider="openai",
        model="gpt-5.5",
        input_usd_per_mtok=Decimal("5.00"),
        output_usd_per_mtok=Decimal("30.00"),
    ),
    ("openai", "gpt-5.5-pro"): ModelPricing(
        provider="openai",
        model="gpt-5.5-pro",
        input_usd_per_mtok=Decimal("30.00"),
        output_usd_per_mtok=Decimal("180.00"),
    ),
    ("anthropic", "claude-opus-4-8"): ModelPricing(
        provider="anthropic",
        model="claude-opus-4-8",
        input_usd_per_mtok=Decimal("5.00"),
        output_usd_per_mtok=Decimal("25.00"),
    ),
    ("anthropic", "claude-sonnet-4-6"): ModelPricing(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_usd_per_mtok=Decimal("3.00"),
        output_usd_per_mtok=Decimal("15.00"),
    ),
    ("anthropic", "claude-haiku-4-5"): ModelPricing(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_usd_per_mtok=Decimal("1.00"),
        output_usd_per_mtok=Decimal("5.00"),
    ),
}

DEFAULT_PROVIDER_MODELS = (
    ProviderModel("openai", DEFAULT_OPENAI_MODEL),
    ProviderModel("anthropic", DEFAULT_ANTHROPIC_MODEL),
)


def normalize_provider_model(provider: str, model: str) -> ProviderModel:
    return ProviderModel(provider=provider.strip().lower(), model=model.strip())


def pricing_for(provider_model: ProviderModel) -> ModelPricing:
    key = (provider_model.provider, provider_model.model)
    if key not in PRICING:
        supported = ", ".join(f"{provider}:{model}" for provider, model in sorted(PRICING))
        raise ValueError(
            f"no pricing for {provider_model.provider}:{provider_model.model}; "
            f"supported: {supported}"
        )
    return PRICING[key]


def estimate_text_tokens(text: str, characters_per_token: Decimal = Decimal("4")) -> int:
    """Approximate tokenizer cost conservatively enough for budget planning."""
    if characters_per_token <= 0:
        raise ValueError("characters_per_token must be positive")
    return int((Decimal(len(text)) / characters_per_token).to_integral_value(ROUND_CEILING))


def estimate_input_tokens(
    scenarios: Iterable[dict],
    runs: int,
    characters_per_token: Decimal = Decimal("4"),
) -> int:
    if runs < 1:
        raise ValueError("runs must be positive")
    prompt_tokens = [
        estimate_text_tokens(build_prompt(scenario), characters_per_token)
        for scenario in scenarios
    ]
    return sum(prompt_tokens) * runs


def estimate_budget(
    scenarios: Iterable[dict],
    provider_models: Iterable[ProviderModel],
    runs: int,
    max_output_tokens: int = ADVISOR_MAX_OUTPUT_TOKENS,
) -> list[BudgetEstimate]:
    scenario_list = list(scenarios)
    if runs < 1:
        raise ValueError("runs must be positive")
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")
    calls = len(scenario_list) * runs
    input_tokens = estimate_input_tokens(scenario_list, runs)
    output_tokens = calls * max_output_tokens
    estimates = []
    for provider_model in provider_models:
        pricing = pricing_for(provider_model)
        input_cost = Decimal(input_tokens) * pricing.input_usd_per_mtok / MILLION_TOKENS
        output_cost = Decimal(output_tokens) * pricing.output_usd_per_mtok / MILLION_TOKENS
        estimates.append(
            BudgetEstimate(
                provider=pricing.provider,
                model=pricing.model,
                calls=calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_cost_usd=input_cost,
                output_cost_usd=output_cost,
            )
        )
    return estimates


def total_cost(estimates: Iterable[BudgetEstimate]) -> Decimal:
    return sum((estimate.total_cost_usd for estimate in estimates), Decimal("0"))


def format_usd(amount: Decimal) -> str:
    rounded = amount.quantize(Decimal("0.0001"))
    if rounded < Decimal("0.01"):
        return f"${rounded}"
    return f"${amount.quantize(Decimal('0.01'))}"


def calls_for_plan(scenario_count: int, runs: int, provider_count: int) -> int:
    return scenario_count * runs * provider_count
