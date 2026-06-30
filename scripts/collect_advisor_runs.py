#!/usr/bin/env python3
"""Collect repeated advisor outputs for the frozen audit scenarios.

Budget-guarded and cached. Each (model, scenario, run) result is written to a
JSON cache and never re-requested, so a small call budget is spent once and the
audit then runs offline forever. The default mode is a dry run that makes zero
API calls and reports what it would request; live collection requires an
explicit flag, provider credentials in the environment, and stays under
--max-calls.

Usage:
    # Dry run: shows the plan, makes no calls.
    python scripts/collect_advisor_runs.py --provider azure --model chat --runs 3

    # Live: needs provider credentials, uses cache, and respects the call cap.
    python scripts/collect_advisor_runs.py \
      --provider azure --model chat --runs 3 --live --max-calls 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from arenawealth.experiments.advisor_prompts import PROMPT_ARMS, build_prompt, parse_response
from arenawealth.experiments.ai_advisor import (
    AdvisorRecommendation,
    AdvisorScenario,
    evaluate_run_set,
)
from arenawealth.experiments.llm_clients import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    AdvisorLLMClient,
    LLMCompletion,
    build_llm_client,
)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCENARIOS_PATH = ROOT / "paper" / "data" / "ai_advisor_scenarios.json"
CACHE_ROOT = ROOT / "exports" / "advisor_runs"


class CallBudget:
    """Hard cap on live API calls. Raises rather than silently overspending."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise RuntimeError(f"call budget of {self.limit} exhausted")
        self.used += 1


@dataclass(frozen=True)
class CollectionConfig:
    """Scalar knobs for one collection run, grouped to keep signatures small."""

    arm: str = "policy"
    temperature: float = 1.0
    live: bool = False
    delay_seconds: float = 0.0
    attempts: int = 3
    backoff_seconds: float = 2.0
    cache_root: Path = CACHE_ROOT


@dataclass(frozen=True)
class CallOutcome:
    completion: LLMCompletion
    attempts: int
    latency_seconds: float


_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


def complete_with_retry(
    client: AdvisorLLMClient,
    prompt: str,
    temperature: float,
    attempts: int,
    backoff_seconds: float,
) -> CallOutcome:
    """Call the model, retrying only transient failures.

    Connection errors, timeouts, and 429/5xx responses are retried with linear
    backoff. A non-transient response (for example 400 or 401) is re-raised at
    once, so a real error surfaces instead of being masked.
    """
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            completion = client.complete(prompt, temperature)
            return CallOutcome(completion, attempt, time.monotonic() - started)
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in _TRANSIENT_STATUS:
                raise
            last_error = error
        except httpx.TransportError as error:
            last_error = error
        if attempt < attempts:
            time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"model call failed after {attempts} attempts") from last_error


def load_scenarios(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"]


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("._") or "unnamed"


def cache_path(
    provider: str,
    model: str,
    scenario_name: str,
    run_index: int,
    arm: str = "policy",
    cache_root: Path = CACHE_ROOT,
) -> Path:
    return (
        cache_root
        / safe_slug(provider)
        / safe_slug(model)
        / safe_slug(arm)
        / f"{safe_slug(scenario_name)}__run{run_index}.json"
    )


def legacy_cache_path(
    provider: str,
    model: str,
    scenario_name: str,
    run_index: int,
    cache_root: Path = CACHE_ROOT,
) -> Path:
    """Return the pre-prompt-arm cache path used by the preserved pilot runs."""
    return (
        cache_root
        / safe_slug(provider)
        / safe_slug(model)
        / f"{safe_slug(scenario_name)}__run{run_index}.json"
    )


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def validate_cached_prompt(record: dict, path: Path) -> None:
    """Verify that a frozen record's prompt still matches its stored hash."""
    prompt = record.get("prompt")
    stored_hash = record.get("prompt_hash")
    if not isinstance(prompt, str) or not isinstance(stored_hash, str):
        raise ValueError(f"cached record lacks prompt provenance: {path}")
    actual_hash = prompt_hash(prompt)
    if actual_hash != stored_hash:
        raise ValueError(
            f"cached prompt hash mismatch in {path}: expected {stored_hash}, got {actual_hash}"
        )


def model_label(provider: str, model: str | None) -> str:
    if model:
        return model
    normalized = provider.strip().lower()
    if normalized == "azure":
        return (
            os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_MODEL")
            or "azure-model"
        )
    if normalized == "openai":
        return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    if normalized == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    return "unknown-model"


def collect_run(
    scenario: dict,
    provider: str,
    model: str,
    run_index: int,
    config: CollectionConfig,
    budget: CallBudget,
    client: AdvisorLLMClient | None,
) -> dict:
    """Return the cached run if present; otherwise request it when live."""
    prompt = build_prompt(scenario, config.arm)
    current_prompt_hash = prompt_hash(prompt)
    path = cache_path(provider, model, scenario["name"], run_index, config.arm, config.cache_root)
    candidates = [path]
    if config.arm == "policy":
        candidates.append(
            legacy_cache_path(provider, model, scenario["name"], run_index, config.cache_root)
        )
    for candidate in candidates:
        if candidate.exists():
            cached = json.loads(candidate.read_text(encoding="utf-8"))
            if cached.get("prompt_hash") == current_prompt_hash:
                validate_cached_prompt(cached, candidate)
                return cached
            if not config.live and cached.get("status") == "collected":
                validate_cached_prompt(cached, candidate)
                cached["frozen_prompt_record"] = True
                return cached
    if not config.live:
        return {
            "status": "would_call",
            "provider": provider,
            "model": model,
            "arm": config.arm,
            "scenario": scenario["name"],
            "run_index": run_index,
            "prompt_hash": current_prompt_hash,
        }
    if client is None:
        raise RuntimeError("live collection requires a provider client")
    budget.spend()
    outcome = complete_with_retry(
        client, prompt, config.temperature, config.attempts, config.backoff_seconds
    )
    record = {
        "status": "collected",
        "provider": provider,
        "model": model,
        "arm": config.arm,
        "scenario": scenario["name"],
        "run_index": run_index,
        "temperature": config.temperature,
        "prompt": prompt,
        "prompt_hash": current_prompt_hash,
        "raw_response": outcome.completion.text,
        "usage": outcome.completion.usage,
        "truncated": outcome.completion.truncated,
        "attempts": outcome.attempts,
        "latency_seconds": round(outcome.latency_seconds, 3),
        "collected_utc": datetime.now(UTC).isoformat(),
    }
    # A malformed reply is a measured outcome, not a crash: record it and mark
    # the run unparseable so the audit counts it as invalid.
    try:
        record["parsed"] = parse_response(outcome.completion.text)
    except ValueError as error:
        record["parsed"] = {"tickers": [], "cited_fact_ids": []}
        record["parse_error"] = str(error)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    if config.delay_seconds > 0:
        time.sleep(config.delay_seconds)
    return record


def scenario_from_dict(raw: dict) -> AdvisorScenario:
    return AdvisorScenario(
        name=raw["name"],
        cash=raw["cash"],
        allowed_tickers=tuple(raw["allowed_tickers"]),
        owned_tickers=tuple(raw["owned_tickers"]),
        policy_tickers=tuple(raw.get("policy_tickers", ())),
        concentration_blocked_tickers=tuple(
            raw.get("concentration_blocked_tickers", ())
        ),
        available_fact_ids=tuple(raw.get("available_fact_ids", ())),
        max_recommendations=raw.get("max_recommendations", 3),
        add_only=raw.get("add_only", True),
        amounts_required=raw.get("amounts_required", False),
    )


def audit_collected(scenario: dict, model: str, records: list[dict]) -> dict | None:
    """Run the offline audit over the cached model outputs for one scenario."""
    usable = [record for record in records if record.get("status") == "collected"]
    if not usable:
        return None
    recommendations = tuple(
        AdvisorRecommendation(
            run_id=f"{model}_{scenario['name']}_{record['run_index']}",
            tickers=tuple(record["parsed"]["tickers"]),
            amounts=tuple(record["parsed"].get("amounts", ())),
            cited_fact_ids=tuple(record["parsed"]["cited_fact_ids"]),
        )
        for record in usable
    )
    report = evaluate_run_set(scenario_from_dict(scenario), model, recommendations)
    return asdict(report)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("azure", "openai", "anthropic"),
        default=os.getenv("ADVISOR_LLM_PROVIDER", "azure"),
    )
    parser.add_argument("--model", help="Provider model or Azure deployment. Defaults to env.")
    parser.add_argument("--runs", type=int, default=3, help="Repeated runs per scenario.")
    parser.add_argument("--max-calls", type=int, default=10, help="Hard cap on live API calls.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature. 1.0 is the provider default; some models reject other values.",
    )
    parser.add_argument("--arm", choices=PROMPT_ARMS, default="policy", help="Prompt arm.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait after each live call, to stay under provider rate limits.",
    )
    parser.add_argument(
        "--attempts", type=int, default=3, help="Max attempts per call on transient failures."
    )
    parser.add_argument(
        "--backoff", type=float, default=2.0, help="Linear backoff seconds between retries."
    )
    parser.add_argument("--live", action="store_true", help="Make real API calls; off by default.")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument("--cache-root", type=Path, default=CACHE_ROOT)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for regenerated audit summaries. Defaults to the cache arm directory.",
    )
    return parser.parse_args()


def run_collection(
    scenarios: list[dict],
    provider: str,
    model: str,
    config: CollectionConfig,
    budget: CallBudget,
    client: AdvisorLLMClient | None,
    runs: int,
) -> tuple[list[dict], list[dict]]:
    """Collect and audit every scenario; return (audit reports, raw records)."""
    audits: list[dict] = []
    records: list[dict] = []
    for scenario in scenarios:
        scenario_records = [
            collect_run(scenario, provider, model, index, config, budget, client)
            for index in range(1, runs + 1)
        ]
        records.extend(scenario_records)
        audit = audit_collected(scenario, model, scenario_records)
        if audit is not None:
            audits.append(audit)
    return audits, records


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_fingerprint() -> dict:
    """Versions that affect reproducibility, recorded with each experiment."""
    return {"python": sys.version.split()[0], "platform": sys.platform}


def write_outputs(out_dir: Path, audits: list[dict], manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit_summary.json").write_text(json.dumps(audits, indent=2), encoding="utf-8")
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    arguments = parse_arguments()
    scenarios = load_scenarios(arguments.scenarios)
    model = model_label(arguments.provider, arguments.model)
    client = build_llm_client(arguments.provider, arguments.model) if arguments.live else None
    if client is not None:
        model = client.model
    config = CollectionConfig(
        arm=arguments.arm,
        temperature=arguments.temperature,
        live=arguments.live,
        delay_seconds=arguments.delay,
        attempts=arguments.attempts,
        backoff_seconds=arguments.backoff,
        cache_root=arguments.cache_root,
    )
    budget = CallBudget(arguments.max_calls)
    planned = len(scenarios) * arguments.runs
    if arguments.live and planned > arguments.max_calls:
        # Cached runs do not spend budget, so this is a ceiling, not a guarantee.
        print(f"note: {planned} runs planned, budget {arguments.max_calls}; cached runs are free.")

    started = datetime.now(UTC)
    started_clock = time.monotonic()
    audits, records = run_collection(
        scenarios, arguments.provider, model, config, budget, client, arguments.runs
    )
    duration_seconds = time.monotonic() - started_clock

    print(f"live calls used: {budget.used} / {arguments.max_calls}")
    if not audits:
        print(
            "no audits produced: nothing cached and no live calls. "
            "Re-run with --live and credentials, or point --cache-root at cached runs."
        )
        return
    collected = [record for record in records if record.get("status") == "collected"]
    truncated_runs = sum(1 for record in collected if record.get("truncated"))
    frozen_prompt_records = sum(1 for record in collected if record.get("frozen_prompt_record"))
    manifest = {
        "provider": arguments.provider,
        "model": model,
        "arm": config.arm,
        "temperature": config.temperature,
        "runs_per_scenario": arguments.runs,
        "scenarios": len(scenarios),
        "scenarios_file": str(arguments.scenarios),
        "scenarios_sha256": file_sha256(arguments.scenarios),
        "live_calls": budget.used,
        "truncated_runs": truncated_runs,
        "frozen_prompt_records": frozen_prompt_records,
        "retries": sum(record.get("attempts", 1) - 1 for record in collected),
        "total_latency_seconds": round(sum(r.get("latency_seconds", 0.0) for r in collected), 3),
        "wall_clock_seconds": round(duration_seconds, 3),
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "environment": environment_fingerprint(),
    }
    out_dir = arguments.out_dir or (
        arguments.cache_root
        / safe_slug(arguments.provider)
        / safe_slug(model)
        / safe_slug(config.arm)
    )
    write_outputs(out_dir, audits, manifest)
    if truncated_runs:
        print(
            f"WARNING: {truncated_runs} run(s) hit the token ceiling and were truncated. "
            "These measure the cap, not the model; raise ADVISOR_MAX_OUTPUT_TOKENS and re-run."
        )
    if frozen_prompt_records:
        print(
            f"verified {frozen_prompt_records} frozen prompt record(s) against their stored hashes"
        )
    source = "live + cache" if arguments.live else "cache only (no API calls)"
    print(
        f"wrote {out_dir}/audit_summary.json + run_manifest.json from {source} "
        f"in {duration_seconds:.1f}s ({budget.used} calls, {manifest['retries']} retries)"
    )


if __name__ == "__main__":
    main()
