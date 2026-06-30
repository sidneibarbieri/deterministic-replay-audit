#!/usr/bin/env python3
"""Write the frozen adversarial advisor scenarios to JSON for the collector."""

from __future__ import annotations

import json
from pathlib import Path

from arenawealth.experiments.adversarial_scenarios import adversarial_scenarios

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "paper" / "data" / "adversarial_scenarios.json"


def main() -> None:
    scenarios = adversarial_scenarios()
    document = {
        "version": 1,
        "description": (
            "Adversarial advisor scenarios with awkward cash amounts and no "
            "fee-revealing facts, used to elicit real model violations across "
            "the bare, policy, and scaffold prompt arms."
        ),
        "scenarios": [scenario.to_payload() for scenario in scenarios],
    }
    OUTPUT_PATH.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(scenarios)} scenarios")


if __name__ == "__main__":
    main()
