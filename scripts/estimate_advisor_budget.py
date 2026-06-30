#!/usr/bin/env python3
"""Estimate advisor LLM experiment cost without making provider calls."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from arenawealth.experiments.llm_budget import (
    DEFAULT_PROVIDER_MODELS,
    BudgetEstimate,
    ProviderModel,
    calls_for_plan,
    estimate_budget,
    format_usd,
    normalize_provider_model,
    total_cost,
)
from arenawealth.experiments.llm_clients import ADVISOR_MAX_OUTPUT_TOKENS

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "paper" / "data" / "ai_advisor_scenarios.json"
load_dotenv(ROOT / ".env")


def load_scenarios(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"]


def parse_provider_models(value: str | None) -> list[ProviderModel]:
    if not value:
        return list(DEFAULT_PROVIDER_MODELS)
    provider_models = []
    for item in value.split(","):
        provider, separator, model = item.partition(":")
        if not separator:
            raise ValueError("provider model entries must use provider:model")
        provider_models.append(normalize_provider_model(provider, model))
    return provider_models


def estimate_as_json(estimates: list[BudgetEstimate]) -> list[dict]:
    rows = []
    for estimate in estimates:
        row = asdict(estimate)
        row["input_cost_usd"] = str(estimate.input_cost_usd)
        row["output_cost_usd"] = str(estimate.output_cost_usd)
        row["total_cost_usd"] = str(estimate.total_cost_usd)
        rows.append(row)
    return rows


def print_table(estimates: list[BudgetEstimate]) -> None:
    header = (
        f"{'provider':<10} {'model':<22} {'calls':>5} {'input_tok':>10} "
        f"{'output_tok':>10} {'input':>10} {'output':>10} {'max_total':>10}"
    )
    print(header)
    print("-" * len(header))
    for estimate in estimates:
        print(
            f"{estimate.provider:<10} {estimate.model:<22} {estimate.calls:>5} "
            f"{estimate.input_tokens:>10} {estimate.output_tokens:>10} "
            f"{format_usd(estimate.input_cost_usd):>10} "
            f"{format_usd(estimate.output_cost_usd):>10} "
            f"{format_usd(estimate.total_cost_usd):>10}"
        )
    print("-" * len(header))
    print(
        f"{'total':<10} {'':<22} {'':>5} {'':>10} {'':>10} {'':>10} {'':>10} "
        f"{format_usd(total_cost(estimates)):>10}"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument("--runs", type=int, default=3, help="Repeated runs per scenario.")
    parser.add_argument(
        "--providers",
        help="Comma-separated provider:model list. Defaults to final OpenAI + Anthropic.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=ADVISOR_MAX_OUTPUT_TOKENS)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    scenarios = load_scenarios(arguments.scenarios)
    provider_models = parse_provider_models(arguments.providers)
    estimates = estimate_budget(
        scenarios,
        provider_models,
        runs=arguments.runs,
        max_output_tokens=arguments.max_output_tokens,
    )
    if arguments.json:
        payload = {
            "scenario_count": len(scenarios),
            "runs_per_scenario": arguments.runs,
            "provider_count": len(provider_models),
            "planned_calls": calls_for_plan(len(scenarios), arguments.runs, len(provider_models)),
            "max_output_tokens_per_call": arguments.max_output_tokens,
            "estimates": estimate_as_json(estimates),
            "total_cost_usd": str(total_cost(estimates)),
        }
        print(json.dumps(payload, indent=2))
        return

    print("Advisor LLM budget estimate. No provider calls were made.")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Runs per scenario: {arguments.runs}")
    print(f"Providers: {len(provider_models)}")
    print(f"Planned calls: {calls_for_plan(len(scenarios), arguments.runs, len(provider_models))}")
    print(f"Max output tokens per call: {arguments.max_output_tokens}")
    print_table(estimates)
    print("Estimate uses prompt characters / 4 for input tokens and the max output token cap.")


if __name__ == "__main__":
    main()
