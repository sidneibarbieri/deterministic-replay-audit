#!/usr/bin/env python3
"""Collect the frontier audit as one interleaved, multi-run campaign.

Every (model, arm, scenario, run) cell is collected in one globally shuffled
order, so temporal or model-version drift is spread across the bare/policy/
scaffold arms rather than aligned with any one: the global shuffle distributes
each arm and model roughly uniformly along the order, which mitigates -- it does
not eliminate -- drift confounding. This is global randomization, not local or
paired interleaving (a scenario's three arms are not adjacent; their median
separation is hundreds of positions). Collection may span more than one session
if resumed; the cache makes that lossless and the consolidated manifest records
each session, so the spread can be checked after the fact.

The per-cell collector is reused unchanged, so cells are cached, budget-guarded,
and byte-identical in layout to the existing frozen audit; the only new artifact
is a campaign manifest that records the seed, the realized interleaved order, and
the single window. Dry by default: it prints the interleaved plan and makes no
calls. Live collection needs an explicit flag, provider credentials, and a cap.

Usage:
    # Dry run: shows the interleaved plan over all cells, makes no calls.
    python scripts/run_interleaved_campaign.py --model azure: --runs 5

    # Live validation on the free Azure test bed, capped:
    python scripts/run_interleaved_campaign.py --model azure: --runs 5 \
        --live --max-calls 12

    # Final paid campaign (two frontier models), interleaved:
    python scripts/run_interleaved_campaign.py \
        --model openai:gpt-5.5 --model anthropic:claude-opus-4-8 \
        --runs 5 --live --max-calls 720 --cache-root paper/data/adversarial_runs
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from collect_advisor_runs import (
    CallBudget,
    CollectionConfig,
    audit_collected,
    collect_run,
    environment_fingerprint,
    file_sha256,
    load_scenarios,
    model_label,
    safe_slug,
    write_outputs,
)
from dotenv import load_dotenv

from arenawealth.experiments.advisor_prompts import PROMPT_ARMS
from arenawealth.experiments.llm_clients import AdvisorLLMClient, build_llm_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCENARIOS_PATH = ROOT / "paper" / "data" / "adversarial_scenarios.json"
CAMPAIGN_ROOT = ROOT / "exports" / "interleaved_campaign"
DEFAULT_SEED = 20260629


@dataclass(frozen=True)
class ModelSpec:
    """One model under test, identified by provider and resolved label."""

    provider: str
    label: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.label}"


@dataclass(frozen=True)
class CallUnit:
    """A single cell of the campaign grid, before it is collected."""

    spec: ModelSpec
    arm: str
    scenario_index: int
    run_index: int


def parse_model_specs(values: list[str], live: bool) -> tuple[
    list[ModelSpec], dict[str, AdvisorLLMClient | None]
]:
    """Resolve ``provider:model`` strings into specs, building live clients once.

    An empty model (``azure:``) defers to the provider's env default. Clients are
    built only in live mode; the label is read from the client so the manifest
    records exactly the deployment that answered.
    """
    specs: list[ModelSpec] = []
    clients: dict[str, AdvisorLLMClient | None] = {}
    for value in values:
        provider, _, model = value.partition(":")
        provider = provider.strip().lower()
        model = model.strip() or None
        client = build_llm_client(provider, model) if live else None
        label = client.model if client is not None else model_label(provider, model)
        spec = ModelSpec(provider=provider, label=label)
        specs.append(spec)
        clients[spec.key] = client
    return specs, clients


def build_units(
    specs: list[ModelSpec], arms: list[str], scenario_count: int, runs: int
) -> list[CallUnit]:
    return [
        CallUnit(spec, arm, scenario_index, run_index)
        for spec in specs
        for arm in arms
        for scenario_index in range(scenario_count)
        for run_index in range(1, runs + 1)
    ]


def interleaved_order(units: list[CallUnit], seed: int) -> list[CallUnit]:
    """Deterministic shuffle: the same seed yields the same interleaved order."""
    order = list(units)
    random.Random(seed).shuffle(order)
    return order


def collect_campaign(
    order: list[CallUnit],
    scenarios: list[dict],
    arm_configs: dict[str, CollectionConfig],
    clients: dict[str, AdvisorLLMClient | None],
    budget: CallBudget,
) -> tuple[list[dict], list[dict]]:
    """Run every cell in interleaved order; return (records, ordered call log)."""
    records: list[dict] = []
    call_log: list[dict] = []
    for position, unit in enumerate(order, start=1):
        scenario = scenarios[unit.scenario_index]
        record = collect_run(
            scenario,
            unit.spec.provider,
            unit.spec.label,
            unit.run_index,
            arm_configs[unit.arm],
            budget,
            clients[unit.spec.key],
        )
        records.append(record)
        call_log.append(
            {
                "position": position,
                "provider": unit.spec.provider,
                "model": unit.spec.label,
                "arm": unit.arm,
                "scenario": scenario["name"],
                "run_index": unit.run_index,
                "status": record.get("status"),
                "collected_utc": record.get("collected_utc"),
                "latency_seconds": record.get("latency_seconds"),
            }
        )
    return records, call_log


def write_arm_summaries(
    records: list[dict],
    scenarios_by_name: dict[str, dict],
    specs: list[ModelSpec],
    arms: list[str],
    cache_root: Path,
) -> dict[str, dict]:
    """Audit each (model, arm) group and write summaries in the frozen layout."""
    arm_results: dict[str, dict] = {}
    for spec in specs:
        for arm in arms:
            cell_records = [
                record
                for record in records
                if record.get("provider") == spec.provider
                and record.get("model") == spec.label
                and record.get("arm") == arm
            ]
            by_scenario: dict[str, list[dict]] = {}
            for record in cell_records:
                by_scenario.setdefault(record["scenario"], []).append(record)
            audits = [
                audit
                for name, group in by_scenario.items()
                if (audit := audit_collected(scenarios_by_name[name], spec.label, group))
                is not None
            ]
            if not audits:
                continue
            total = sum(audit["runs"] for audit in audits)
            valid = sum(audit["valid_runs"] for audit in audits)
            truncated = sum(1 for r in cell_records if r.get("truncated"))
            out_dir = (
                cache_root / safe_slug(spec.provider) / safe_slug(spec.label) / safe_slug(arm)
            )
            write_outputs(out_dir, audits, {"truncated_runs": truncated})
            arm_results[f"{spec.key}/{arm}"] = {
                "valid_runs": valid,
                "total_runs": total,
                "valid_rate": round(valid / total, 4) if total else 0.0,
                "truncated_runs": truncated,
            }
    return arm_results


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        default=None,
        help="Repeatable provider:model under test, e.g. openai:gpt-5.5. "
        "Empty model (azure:) uses the provider env default.",
    )
    parser.add_argument("--arms", default="bare,policy,scaffold", help="Comma-separated arms.")
    parser.add_argument("--runs", type=int, default=5, help="Repeated runs per scenario.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Interleaving seed.")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds between live calls.")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--max-calls", type=int, default=12, help="Hard cap on live API calls.")
    parser.add_argument(
        "--limit-cells",
        type=int,
        default=0,
        help="Collect only the first N cells of the interleaved order (0 = all). "
        "Use for a live smoke that validates the path without running the full grid.",
    )
    parser.add_argument("--live", action="store_true", help="Make real API calls; off by default.")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument("--cache-root", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    arms = [arm.strip() for arm in arguments.arms.split(",") if arm.strip()]
    unknown = [arm for arm in arms if arm not in PROMPT_ARMS]
    if unknown:
        raise SystemExit(f"unknown prompt arms {unknown}; choose from {sorted(PROMPT_ARMS)}")
    model_values = arguments.models or ["azure:"]
    scenarios = load_scenarios(arguments.scenarios)
    scenarios_by_name = {scenario["name"]: scenario for scenario in scenarios}
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    cache_root = arguments.cache_root or (CAMPAIGN_ROOT / stamp / "cache")

    specs, clients = parse_model_specs(model_values, arguments.live)
    arm_configs = {
        arm: CollectionConfig(
            arm=arm,
            temperature=arguments.temperature,
            live=arguments.live,
            delay_seconds=arguments.delay,
            attempts=arguments.attempts,
            backoff_seconds=arguments.backoff,
            cache_root=cache_root,
        )
        for arm in arms
    }
    units = build_units(specs, arms, len(scenarios), arguments.runs)
    order = interleaved_order(units, arguments.seed)
    if arguments.limit_cells > 0:
        order = order[: arguments.limit_cells]
    budget = CallBudget(arguments.max_calls)

    print(
        f"campaign: {len(specs)} model(s) x {len(arms)} arm(s) x {len(scenarios)} scenario(s) "
        f"x {arguments.runs} run(s) = {len(units)} cells, interleaved with seed {arguments.seed}"
    )
    if not arguments.live:
        for entry in order[:6]:
            name = scenarios[entry.scenario_index]["name"]
            print(f"  would call {entry.spec.key} {entry.arm} {name} run{entry.run_index}")
        print(f"  ... ({len(order)} cells total). Dry run: no API calls made.")
        return

    started = datetime.now(UTC)
    started_clock = time.monotonic()
    records, call_log = collect_campaign(order, scenarios, arm_configs, clients, budget)
    duration = time.monotonic() - started_clock

    campaign_dir = arguments.cache_root or (CAMPAIGN_ROOT / stamp)
    arm_results = write_arm_summaries(records, scenarios_by_name, specs, arms, cache_root)
    collected = [record for record in records if record.get("status") == "collected"]
    manifest = {
        "seed": arguments.seed,
        "interleaved": True,
        "models": [spec.key for spec in specs],
        "arms": arms,
        "runs_per_scenario": arguments.runs,
        "scenarios": len(scenarios),
        "scenarios_file": str(arguments.scenarios),
        "scenarios_sha256": file_sha256(arguments.scenarios),
        "temperature": arguments.temperature,
        "planned_cells": len(units),
        "live_calls": budget.used,
        "collected_cells": len(collected),
        "truncated_runs": sum(1 for record in collected if record.get("truncated")),
        "arm_results": arm_results,
        "call_log": call_log,
        "wall_clock_seconds": round(duration, 3),
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "environment": environment_fingerprint(),
    }
    campaign_dir.mkdir(parents=True, exist_ok=True)
    (campaign_dir / "campaign_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"live calls used: {budget.used} / {arguments.max_calls}")
    for key, result in arm_results.items():
        rate = result["valid_rate"]
        print(f"  {key:32s} {rate:.2f} ({result['valid_runs']}/{result['total_runs']})")
    print(f"wrote {campaign_dir}/campaign_manifest.json in {duration:.1f}s")


if __name__ == "__main__":
    main()
