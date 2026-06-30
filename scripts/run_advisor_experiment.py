#!/usr/bin/env python3
"""Run the full advisor audit experiment: every prompt arm, repeated end to end.

Each repetition uses a fresh cache directory, so it makes real API calls from
scratch. This guards against transient connection issues and measures stability:
if the valid rate per arm is consistent across repetitions, the result is not an
artifact of one flaky run. Every repetition records wall-clock time, retries, and
call counts; the consolidated record persists to a timestamped experiment file
that the review dashboard reads.

Reviewers reproduce the experiment with their own keys by setting provider
credentials in .env and running `make advisor-experiment`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from collect_advisor_runs import (
    CallBudget,
    CollectionConfig,
    environment_fingerprint,
    file_sha256,
    load_scenarios,
    model_label,
    run_collection,
)
from dotenv import load_dotenv

from arenawealth.experiments.llm_clients import build_llm_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCENARIOS_PATH = ROOT / "paper" / "data" / "adversarial_scenarios.json"
EXPERIMENTS_ROOT = ROOT / "exports" / "experiments"


def valid_rate(audits: list[dict]) -> float:
    runs = sum(audit["runs"] for audit in audits)
    valid = sum(audit["valid_runs"] for audit in audits)
    return valid / runs if runs else 0.0


def run_cell(
    scenarios: list[dict],
    provider: str,
    arm: str,
    runs: int,
    cache_root: Path,
    delay: float,
    attempts: int,
    backoff: float,
    max_calls: int,
) -> dict:
    """One (repetition, arm) cell: collect, audit, and time it."""
    client = build_llm_client(provider, None)
    config = CollectionConfig(
        arm=arm,
        live=True,
        delay_seconds=delay,
        attempts=attempts,
        backoff_seconds=backoff,
        cache_root=cache_root,
    )
    budget = CallBudget(max_calls)
    started = time.monotonic()
    audits, records = run_collection(
        scenarios, provider, client.model, config, budget, client, runs
    )
    collected = [record for record in records if record.get("status") == "collected"]
    return {
        "arm": arm,
        "model": client.model,
        "valid_rate": round(valid_rate(audits), 4),
        "scenarios": len(audits),
        "live_calls": budget.used,
        "retries": sum(record.get("attempts", 1) - 1 for record in collected),
        "wall_clock_seconds": round(time.monotonic() - started, 2),
        "audits": audits,
    }


def stability_summary(cells: list[dict], arms: list[str]) -> list[dict]:
    """Mean and spread of the valid rate per arm across repetitions."""
    summary = []
    for arm in arms:
        rates = [cell["valid_rate"] for cell in cells if cell["arm"] == arm]
        summary.append(
            {
                "arm": arm,
                "repetitions": len(rates),
                "valid_rate_mean": round(statistics.fmean(rates), 4) if rates else 0.0,
                "valid_rate_min": min(rates) if rates else 0.0,
                "valid_rate_max": max(rates) if rates else 0.0,
                "valid_rate_stdev": round(statistics.pstdev(rates), 4) if len(rates) > 1 else 0.0,
            }
        )
    return summary


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="azure", choices=("azure", "openai", "anthropic"))
    parser.add_argument("--arms", default="bare,policy,scaffold", help="Comma-separated arms.")
    parser.add_argument("--runs", type=int, default=3, help="Repeated runs per scenario.")
    parser.add_argument(
        "--repetitions", type=int, default=3, help="Full from-scratch repetitions."
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Seconds between live calls."
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument(
        "--max-calls", type=int, default=200, help="Call cap per arm per repetition."
    )
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_PATH)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    arms = [arm.strip() for arm in arguments.arms.split(",") if arm.strip()]
    scenarios = load_scenarios(arguments.scenarios)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = arguments.out or (EXPERIMENTS_ROOT / f"advisor_{arguments.provider}_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now(UTC)
    started_clock = time.monotonic()
    cells: list[dict] = []
    for repetition in range(1, arguments.repetitions + 1):
        for arm in arms:
            cache_root = out_dir / "cache" / f"rep{repetition}"
            cell = run_cell(
                scenarios,
                arguments.provider,
                arm,
                arguments.runs,
                cache_root,
                arguments.delay,
                arguments.attempts,
                arguments.backoff,
                arguments.max_calls,
            )
            cell["repetition"] = repetition
            cells.append(cell)
            print(
                f"rep{repetition} {arm:9s} valid_rate={cell['valid_rate']:.2f} "
                f"calls={cell['live_calls']} retries={cell['retries']} "
                f"{cell['wall_clock_seconds']:.0f}s"
            )

    experiment = {
        "provider": arguments.provider,
        "model": model_label(arguments.provider, None),
        "arms": arms,
        "runs_per_scenario": arguments.runs,
        "repetitions": arguments.repetitions,
        "scenarios": len(scenarios),
        "scenarios_file": str(arguments.scenarios),
        "scenarios_sha256": file_sha256(arguments.scenarios),
        "stability": stability_summary(cells, arms),
        "cells": [
            {key: value for key, value in cell.items() if key != "audits"} for cell in cells
        ],
        "wall_clock_seconds": round(time.monotonic() - started_clock, 2),
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "environment": environment_fingerprint(),
    }
    (out_dir / "experiment.json").write_text(json.dumps(experiment, indent=2), encoding="utf-8")
    print(f"\nwrote {out_dir}/experiment.json in {experiment['wall_clock_seconds']:.0f}s")
    for row in experiment["stability"]:
        print(
            f"  {row['arm']:9s} valid_rate {row['valid_rate_mean']:.2f} "
            f"(min {row['valid_rate_min']:.2f}, max {row['valid_rate_max']:.2f}, "
            f"stdev {row['valid_rate_stdev']:.3f})"
        )


if __name__ == "__main__":
    main()
