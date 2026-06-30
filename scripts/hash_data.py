#!/usr/bin/env python3
"""Hash the tracked data inputs so reviewers can verify integrity.

The figures and tables are regenerated from a small set of tracked inputs. This
script records their SHA-256 digests in a manifest and, by default, checks the
current files against it. A reviewer can confirm in one command that the data
producing the artifact's results is exactly what shipped.

Usage:
    python scripts/hash_data.py            # verify against the manifest
    python scripts/hash_data.py --write    # (re)generate the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "paper" / "data" / "DATA_HASHES.txt"
STATIC_INPUTS = (
    "tests/fixtures/seed_portfolio_broker.csv",
    "paper/data/returns_matrix.csv",
    "paper/data/price_backtest_reference.json",
    "paper/data/ai_advisor_scenarios.json",
    "paper/data/ai_advisor_audit_reference.json",
    "paper/data/adversarial_scenarios.json",
)
ADVISOR_RUNS = ROOT / "paper" / "data" / "advisor_runs"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_inputs() -> tuple[str, ...]:
    run_files = [
        path.relative_to(ROOT).as_posix()
        for runs_root in (
            ADVISOR_RUNS,
            ROOT / "paper" / "data" / "adversarial_runs",
        )
        for path in sorted(runs_root.glob("**/*.json"))
        if path.is_file()
    ]
    return (*STATIC_INPUTS, *run_files)


def current_digests() -> dict[str, str]:
    return {name: sha256(ROOT / name) for name in tracked_inputs()}


def write_manifest() -> None:
    lines = [f"{digest}  {name}" for name, digest in current_digests().items()]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST} ({len(lines)} entries)")


def read_manifest() -> dict[str, str]:
    digests: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        digests[name.strip()] = digest
    return digests


def verify() -> int:
    expected = read_manifest()
    actual = current_digests()
    expected_names = set(expected)
    actual_names = set(actual)
    missing_files = sorted(expected_names - actual_names)
    untracked_files = sorted(actual_names - expected_names)
    mismatches = sorted(
        name for name in expected_names & actual_names if expected[name] != actual[name]
    )
    if missing_files or untracked_files or mismatches:
        print("DATA INTEGRITY MISMATCH:", file=sys.stderr)
        for name in missing_files:
            print(f"  {name}: listed in manifest but missing from disk", file=sys.stderr)
        for name in untracked_files:
            print(f"  {name}: present on disk but missing from manifest", file=sys.stderr)
        for name in mismatches:
            print(f"  {name}: expected {expected.get(name)}, got {actual[name]}", file=sys.stderr)
        return 1
    print(f"data integrity OK ({len(actual)} inputs match the manifest)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the manifest.")
    arguments = parser.parse_args()
    if arguments.write:
        write_manifest()
        return 0
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
