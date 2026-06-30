"""Sensitivity of the guardrail and premium to the fee parameters.

The economic order floor is the fixed point of the fee-impact constraint,

    MIN(c, tau) = c / tau,

where c is the fixed cost charged per started tranche and tau is the tolerated
fee impact. The floor is linear in c and inverse in tau, and---importantly---it
does not depend on the tranche size T. T only rescales the diversification
premium bands, not the floor. This module sweeps (c, tau) so the $250 operating
point can be seen as one cell of a closed-form surface that generalizes to any
schedule with a fixed per-order component.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isinf

DEFAULT_COST = 2.50
DEFAULT_TOLERANCE = 0.01


def guardrail_floor(cost: float, tolerance: float) -> float:
    """Minimum economic order size c / tau (the fee-impact fixed point)."""
    if cost < 0:
        raise ValueError("cost must be non-negative")
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    return cost / tolerance


@dataclass(frozen=True)
class BrokerSchedule:
    """A named fixed-fee schedule. tranche is inf for a flat per-order fee."""

    name: str
    cost: float
    tranche: float

    def floor_at(self, tolerance: float = DEFAULT_TOLERANCE) -> float:
        return guardrail_floor(self.cost, tolerance)


def reference_schedules() -> tuple[BrokerSchedule, ...]:
    """Plausible fixed-fee schedules across brokers and markets.

    The first matches the studied broker (a fixed cost per started $1,000
    tranche); the others are flat per-order fees still seen for international or
    non-US-equity access. Zero-commission US equity is the degenerate c=0 case.
    """
    return (
        BrokerSchedule("Tranche $2.50 / $1k", cost=2.50, tranche=1000.0),
        BrokerSchedule("Flat $1.00", cost=1.00, tranche=float("inf")),
        BrokerSchedule("Flat $5.00", cost=5.00, tranche=float("inf")),
        BrokerSchedule("Flat $9.99", cost=9.99, tranche=float("inf")),
    )


@dataclass(frozen=True)
class GuardrailCell:
    cost: float
    tolerance: float
    floor: float


def guardrail_grid(
    costs: Sequence[float], tolerances: Sequence[float]
) -> tuple[GuardrailCell, ...]:
    """The floor c / tau for every (cost, tolerance) pair in the sweep."""
    cells: list[GuardrailCell] = []
    for cost in costs:
        for tolerance in tolerances:
            cells.append(
                GuardrailCell(
                    cost=cost,
                    tolerance=tolerance,
                    floor=guardrail_floor(cost, tolerance),
                )
            )
    return tuple(cells)


@dataclass(frozen=True)
class ScheduleFloor:
    name: str
    cost: float
    tranche: float
    floor_at_1pct: float


def schedule_floors(
    schedules: Sequence[BrokerSchedule], tolerance: float = DEFAULT_TOLERANCE
) -> tuple[ScheduleFloor, ...]:
    """Implied economic floor for each named schedule at a fixed tolerance."""
    return tuple(
        ScheduleFloor(
            name=schedule.name,
            cost=schedule.cost,
            tranche=schedule.tranche,
            floor_at_1pct=schedule.floor_at(tolerance),
        )
        for schedule in schedules
    )


def floor_is_tranche_invariant(cost: float, tolerance: float, tranches: Sequence[float]) -> bool:
    """The floor depends only on (cost, tolerance), never on the tranche size.

    A single tranche is started by any positive order, so the binding fee at the
    floor is exactly one unit of cost regardless of T. We check that the closed
    form is constant across a set of tranche sizes (including a flat per-order
    fee, tranche = inf).
    """
    reference = guardrail_floor(cost, tolerance)
    for tranche in tranches:
        if tranche <= 0 and not isinf(tranche):
            raise ValueError("tranche must be positive")
        if guardrail_floor(cost, tolerance) != reference:
            return False
    return True
