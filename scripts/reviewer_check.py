"""One-command reviewer self-check.

Re-derives the paper's headline numbers from the frozen artifact data and
prints a pass/fail line for each, so a reviewer confirms reproduction without
reading any code. Run with: make review
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

from arenawealth.experiments.advisor_prompts import build_prompt, parse_response

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "paper" / "data" / "adversarial_runs"
SCENARIOS = ROOT / "paper" / "data" / "adversarial_scenarios.json"

# What the paper claims, checked against the frozen runs (Section 3).
EXPECTED_VALIDITY = {
    ("openai", "gpt-5.5", "bare"): 0.59,
    ("openai", "gpt-5.5", "policy"): 0.98,
    ("openai", "gpt-5.5", "scaffold"): 1.00,
    ("anthropic", "claude-opus-4-8", "bare"): 0.51,
    ("anthropic", "claude-opus-4-8", "policy"): 0.93,
    ("anthropic", "claude-opus-4-8", "scaffold"): 0.97,
}
RUNS_PER_ARM = 120
# Scenario-clustered bootstrap for the validity confidence interval (Section 3):
# runs are correlated within a scenario, so the resampling unit is the scenario,
# not the run. Fixed seed and resample count make the interval reproducible.
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260629


@dataclass(frozen=True)
class Check:
    ok: bool
    title: str
    detail: str


def arm_validity(provider: str, model: str, arm: str) -> tuple[float, int, int]:
    """Return (valid_rate, total_runs, truncated_runs) for one arm."""
    arm_dir = RUNS / provider / model / arm
    summary = json.loads((arm_dir / "audit_summary.json").read_text())
    total = sum(row["runs"] for row in summary)
    valid = sum(row["valid_runs"] for row in summary)
    manifest = json.loads((arm_dir / "run_manifest.json").read_text())
    return valid / total, total, manifest.get("truncated_runs", -1)


def arm_validity_ci(provider: str, model: str, arm: str) -> tuple[float, float]:
    """95% scenario-clustered bootstrap interval for one arm's validity rate."""
    arm_dir = RUNS / provider / model / arm
    summary = json.loads((arm_dir / "audit_summary.json").read_text())
    scenarios = [(row["valid_runs"], row["runs"]) for row in summary]
    rng = random.Random(BOOTSTRAP_SEED)  # per-arm seed: order-independent
    rates = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [scenarios[rng.randrange(len(scenarios))] for _ in scenarios]
        valid = sum(v for v, _ in sample)
        total = sum(t for _, t in sample)
        rates.append(valid / total)
    rates.sort()
    lo = rates[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = rates[int(0.975 * BOOTSTRAP_RESAMPLES)]
    return lo, hi


def check_validity_gradient() -> Check:
    lines: list[str] = []
    ok = True
    for (provider, model, arm), expected in EXPECTED_VALIDITY.items():
        rate, total, truncated = arm_validity(provider, model, arm)
        lo, hi = arm_validity_ci(provider, model, arm)
        arm_ok = round(rate, 2) == expected and total == RUNS_PER_ARM and truncated == 0
        ok = ok and arm_ok
        mark = "ok" if arm_ok else "MISMATCH"
        lines.append(
            f"      {model:16s} {arm:9s} {rate:.2f} (paper {expected:.2f}), "
            f"95% CI [{lo:.2f}, {hi:.2f}], {total} runs, truncated={truncated}  [{mark}]"
        )
    return Check(
        ok,
        "Validity gradient matches the paper (bare, policy, computed scaffold)",
        "\n".join(lines),
    )


def check_no_truncation() -> Check:
    bad = [
        f"{model}/{arm}"
        for (provider, model, arm) in EXPECTED_VALIDITY
        if arm_validity(provider, model, arm)[2] != 0
    ]
    return Check(
        not bad,
        "No completion was truncated by the token budget",
        "all arms truncated=0" if not bad else f"truncated arms: {bad}",
    )


def check_prompt_hashes() -> Check:
    """Verify every frozen prompt and parsed model response."""
    scenarios = {
        scenario["name"]: scenario
        for scenario in json.loads(SCENARIOS.read_text())["scenarios"]
    }
    paths = sorted(RUNS.glob("**/*__run*.json"))
    mismatches = []
    for path in paths:
        record = json.loads(path.read_text())
        prompt = record.get("prompt", "")
        actual = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        arm = path.parent.name
        scenario_name = path.stem.rsplit("__run", 1)[0]
        expected = hashlib.sha256(
            build_prompt(scenarios[scenario_name], arm).encode("utf-8")
        ).hexdigest()
        try:
            reparsed = {
                key: list(value)
                for key, value in parse_response(record["raw_response"]).items()
            }
        except (KeyError, TypeError, ValueError):
            reparsed = None
        if (
            actual != record.get("prompt_hash")
            or actual != expected
            or reparsed != record.get("parsed")
        ):
            mismatches.append(path.relative_to(ROOT).as_posix())
    expected_records = 2 * 3 * 24 * 5
    ok = len(paths) == expected_records and not mismatches
    detail = (
        f"{len(paths)} prompts and raw responses match the current protocol"
        if ok
        else f"expected {expected_records}, found {len(paths)}; mismatches: {mismatches[:5]}"
    )
    return Check(ok, "Frozen request/response provenance is intact", detail)


def render(checks: list[Check]) -> bool:
    print("ActionAudit -- reviewer self-check\n")
    for check in checks:
        symbol = "[PASS]" if check.ok else "[FAIL]"
        print(f"{symbol} {check.title}")
        if check.detail:
            print(check.detail)
    all_ok = all(check.ok for check in checks)
    print("\n" + ("All checks passed." if all_ok else "Some checks FAILED."))
    print("See REVIEWER_GUIDE.md for the full paper-to-artifact map.")
    return all_ok


def main() -> None:
    checks = [check_validity_gradient(), check_no_truncation(), check_prompt_hashes()]
    raise SystemExit(0 if render(checks) else 1)


if __name__ == "__main__":
    main()
