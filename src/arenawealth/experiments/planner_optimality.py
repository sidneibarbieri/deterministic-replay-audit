"""Optimality of the deterministic planner against a mixed-integer optimum.

The deterministic planner is a fast heuristic, so a reviewer reasonably asks how
far it can fall short of the exact optimum. This module answers that on a small
cash grid by comparing the planner against two references under the same fee
schedule:

* Fee: by subadditivity the minimum fee to deploy an amount is the consolidated
  single-order fee ``compute_order_fee(cash)``. We report the planner's fee
  premium over that closed-form lower bound.
* Deployment: a mixed-integer program maximizes cash deployment subject only to
  the budget and economic floor. Its result is therefore an upper bound on any
  policy with additional portfolio constraints. We report how much less cash
  the planner deploys than that bound in a regime where concentration does not
  bind.

Both references use only the public planner inputs, so the check is reproducible
and adds no modeling assumptions of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arenawealth.analytics.deployment import (
    FeeParameters,
    compute_order_fee,
    plan_deployment,
)
from arenawealth.analytics.deployment_mip import plan_deployment_mip
from arenawealth.analytics.models import Holding, PositionAnalysis


def candidate(
    ticker: str,
    score: float,
    theme: str,
    market_value: float,
    weight_pct: float,
    price: float = 100.0,
) -> PositionAnalysis:
    """Minimal candidate row; only score, theme, value, and weight drive planning."""
    holding = Holding(ticker, ticker, market_value / price, 1.0, price, theme, False)
    return PositionAnalysis(
        holding=holding,
        live_price=price,
        market_value=market_value,
        weight_pct=weight_pct,
        pnl_pct=0.0,
        price_gap_pct=0.0,
        roic=None,
        roe=None,
        margin_cv=None,
        revenue_cagr=None,
        eps_cagr=None,
        fcf_cagr=None,
        shares_change=None,
        fcf_yield=None,
        forward_pe=None,
        peg=None,
        moat_class="MODERATE",
        compounding_class="GOOD",
        moat_points=0.0,
        compounding_points=0.0,
        valuation_points=0.0,
        composite_score=score,
    )


@dataclass(frozen=True)
class OptimalityPoint:
    cash: float
    deployed_planner: float
    deployed_mip: float
    deployment_gap: float
    fee_planner: float
    fee_lower_bound: float
    fee_premium: float


@dataclass(frozen=True)
class OptimalityReport:
    points: tuple[OptimalityPoint, ...]
    max_deployment_gap: float
    max_fee_premium: float


def planner_optimality(
    candidates: Sequence[PositionAnalysis],
    cash_grid: Sequence[float],
    fee_params: FeeParameters | None = None,
) -> OptimalityReport:
    """Compare the planner against the fee lower bound and the MIP deployment optimum."""
    fee_params = fee_params or FeeParameters()
    points: list[OptimalityPoint] = []
    for cash in cash_grid:
        plan = plan_deployment(candidates, cash, fee_params)
        deployed_planner = sum(order.amount for order in plan.orders)
        fee_lower_bound = compute_order_fee(deployed_planner, fee_params)
        mip_orders, mip_metadata = plan_deployment_mip(list(candidates), cash, fee_params)
        deployed_mip = mip_metadata.deployed_amount_usd if mip_orders else 0.0
        points.append(
            OptimalityPoint(
                cash=cash,
                deployed_planner=deployed_planner,
                deployed_mip=deployed_mip,
                deployment_gap=max(0.0, deployed_mip - deployed_planner),
                fee_planner=plan.total_fee,
                fee_lower_bound=fee_lower_bound,
                fee_premium=plan.total_fee - fee_lower_bound,
            )
        )
    return OptimalityReport(
        points=tuple(points),
        max_deployment_gap=max((point.deployment_gap for point in points), default=0.0),
        max_fee_premium=max((point.fee_premium for point in points), default=0.0),
    )


def reference_scenario() -> tuple[PositionAnalysis, ...]:
    """Four under-weight candidates across distinct themes with ample headroom.

    This is the planner's design regime: recurring small-cash deployment where no
    concentration limit binds, so any shortfall is the heuristic's own.
    """
    return (
        candidate("AAA", 90.0, "ThemeA", market_value=40_000.0, weight_pct=5.0),
        candidate("BBB", 80.0, "ThemeB", market_value=40_000.0, weight_pct=5.0),
        candidate("CCC", 70.0, "ThemeC", market_value=40_000.0, weight_pct=5.0),
        candidate("DDD", 60.0, "ThemeD", market_value=40_000.0, weight_pct=5.0),
    )


def reference_report() -> OptimalityReport:
    """The optimality check reported in the paper, on a fixed small-cash grid."""
    grid = (250.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0, 3000.0, 5000.0)
    return planner_optimality(reference_scenario(), grid)
