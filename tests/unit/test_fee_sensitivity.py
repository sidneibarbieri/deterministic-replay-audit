"""Unit tests for the fee-parameter sensitivity sweep (pure, offline)."""

import math

import pytest

from arenawealth.experiments.fee_sensitivity import (
    floor_is_tranche_invariant,
    guardrail_floor,
    guardrail_grid,
    reference_schedules,
    schedule_floors,
)


def test_guardrail_floor_recovers_operating_point():
    assert guardrail_floor(2.50, 0.01) == 250.0


def test_guardrail_floor_is_linear_in_cost():
    base = guardrail_floor(2.50, 0.01)
    assert guardrail_floor(5.00, 0.01) == pytest.approx(2 * base)


def test_guardrail_floor_is_inverse_in_tolerance():
    assert guardrail_floor(2.50, 0.02) == pytest.approx(guardrail_floor(2.50, 0.01) / 2)


def test_guardrail_floor_rejects_nonpositive_tolerance():
    with pytest.raises(ValueError):
        guardrail_floor(2.50, 0.0)


def test_guardrail_grid_covers_every_pair():
    costs = [1.0, 2.5, 5.0]
    tolerances = [0.005, 0.01, 0.02]
    cells = guardrail_grid(costs, tolerances)
    assert len(cells) == len(costs) * len(tolerances)
    operating = next(cell for cell in cells if cell.cost == 2.5 and cell.tolerance == 0.01)
    assert operating.floor == 250.0


def test_reference_schedule_floors_at_one_percent():
    floors = {row.name: row.floor_at_1pct for row in schedule_floors(reference_schedules())}
    assert floors["Tranche $2.50 / $1k"] == 250.0
    assert floors["Flat $1.00"] == 100.0
    assert floors["Flat $5.00"] == 500.0
    assert math.isclose(floors["Flat $9.99"], 999.0)


def test_floor_is_invariant_to_tranche_size():
    # The floor must be identical for tranche sizes from $500 to a flat fee.
    assert floor_is_tranche_invariant(2.50, 0.01, [500.0, 1000.0, 2000.0, float("inf")])
