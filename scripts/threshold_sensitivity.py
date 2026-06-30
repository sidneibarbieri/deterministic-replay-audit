#!/usr/bin/env python3
"""Sensitivity of the portfolio-fit decision to the contract thresholds.

Reviewers (and the SOCpilot rejection) flag hand-chosen thresholds as arbitrary.
This experiment sweeps the theme concentration cap, the concentration-penalty
multiplier, and the new-theme diversification incentive, and reports whether the
headline portfolio-fit decision (select Industrial over the higher-quality
Platforms candidate) is knife-edge on the exact 20% / 1.3x values or robust.

Deterministic, offline, no LLM calls. The projected-weight arithmetic reuses the
production function so the swept formula matches the shipped verifier exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from arenawealth.analytics.portfolio_review import projected_theme_weight_pct

# The controlled scenario from the paper (Table: Platforms vs Industrial).
# Held themes: Platforms 23% (two positions), Healthcare 5%. Starter slot 10%.
STARTER_WEIGHT_PCT = 10.0
HELD_THEME_WEIGHTS = {"Platforms": 23.0, "Healthcare": 5.0}
CANDIDATES = (
    ("Platforms", 90.0, "Platforms"),  # name, composite, theme
    ("Industrial", 84.0, "Industrial"),
    ("Healthcare", 82.0, "Healthcare"),
)

# Production defaults (portfolio_review.py): base 80, penalty x3, bonus 12, cap 20.
BASE = 80.0


@dataclass(frozen=True)
class FitInputs:
    name: str
    composite: float
    projected_theme_pct: float
    is_new_theme: bool


def candidate_inputs() -> tuple[FitInputs, ...]:
    rows = []
    for name, composite, theme in CANDIDATES:
        current = HELD_THEME_WEIGHTS.get(theme, 0.0)
        rows.append(
            FitInputs(
                name=name,
                composite=composite,
                projected_theme_pct=projected_theme_weight_pct(current, STARTER_WEIGHT_PCT),
                is_new_theme=current == 0.0,
            )
        )
    return tuple(rows)


def fit_score(row: FitInputs, cap: float, penalty_mult: float, bonus: float) -> float:
    """Same closed form as portfolio_review.portfolio_fit_score, with swept knobs."""
    penalty = max(0.0, row.projected_theme_pct - cap) * penalty_mult
    diversification = bonus if row.is_new_theme else 0.0
    return max(0.0, min(100.0, BASE + diversification - penalty))


def decision(rows: tuple[FitInputs, ...], cap: float, penalty_mult: float, bonus: float) -> str:
    """Winner under portfolio-fit (tie broken by composite), as the verifier ranks."""
    return max(rows, key=lambda r: (fit_score(r, cap, penalty_mult, bonus), r.composite)).name


def main() -> None:
    rows = candidate_inputs()
    isolated_top = max(rows, key=lambda r: r.composite).name

    # 1. Reproduce the shipped numbers as a faithfulness check.
    print("Faithfulness check (production defaults cap=20, penalty x3, bonus 12):")
    for row in rows:
        print(
            f"  {row.name:10s} projected_theme={row.projected_theme_pct:5.1f}%  "
            f"fit={fit_score(row, 20.0, 3.0, 12.0):5.1f}  composite={row.composite:.0f}"
        )
    print(f"  isolated-rank top = {isolated_top};  "
          f"portfolio-fit top = {decision(rows, 20.0, 3.0, 12.0)}\n")

    # 2. Sweep the grid; record where the decision flips away from Industrial.
    caps = (10.0, 15.0, 20.0, 25.0, 30.0, 35.0)
    penalties = (1.0, 2.0, 3.0, 5.0)
    bonuses = (0.0, 6.0, 12.0, 18.0)
    total = flips = 0
    flip_cases = []
    for cap in caps:
        for pm in penalties:
            for bonus in bonuses:
                total += 1
                win = decision(rows, cap, pm, bonus)
                if win != "Industrial":
                    flips += 1
                    flip_cases.append((cap, pm, bonus, win))
    print(f"Swept {total} threshold combinations "
          f"(cap in {caps}, penalty in {penalties}, bonus in {bonuses}).")
    print(f"Headline decision (Industrial over Platforms) holds in "
          f"{total - flips}/{total} = {100*(total-flips)/total:.0f}% of the grid.")
    if flip_cases:
        print("Flips only at:")
        for cap, pm, bonus, win in flip_cases:
            print(f"  cap={cap:.0f}%, penalty x{pm:.0f}, bonus={bonus:.0f} -> {win}")
    else:
        print("No flip anywhere in the grid.")


if __name__ == "__main__":
    main()
