"""Unit tests for the deterministic deployment planner (no network)."""

import math

from arenawealth.analytics.deployment import (
    FeeParameters,
    compute_order_fee,
    plan_deployment,
)
from arenawealth.analytics.models import Holding, PositionAnalysis


def test_kway_fee_neutrality_characterization():
    """A split is fee-neutral iff leg tranche counts match the whole budget."""
    fee_params = FeeParameters()
    budget = 2500.0
    whole_tranches = math.ceil(budget / fee_params.tranche_size_usd)  # 3
    # Whole-tranche legs are fee-neutral and reach the ceil(a/T) bound.
    tranche = fee_params.tranche_size_usd
    legs = [tranche, tranche, budget - 2 * tranche]
    assert len(legs) == whole_tranches
    whole_budget_fee = compute_order_fee(budget, fee_params)
    assert sum(compute_order_fee(leg, fee_params) for leg in legs) == whole_budget_fee
    # Splitting into more legs than ceil(a/T) must overpay.
    too_many = [budget / 4] * 4
    assert sum(compute_order_fee(leg, fee_params) for leg in too_many) > whole_budget_fee


def make_position(
    ticker: str, composite: float, weight: float, theme: str, price: float = 100.0
) -> PositionAnalysis:
    holding = Holding(ticker, ticker, 1.0, 1.0, price, theme, False)
    return PositionAnalysis(
        holding=holding,
        live_price=price,
        market_value=weight,
        weight_pct=weight,
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
        composite_score=composite,
    )


def test_order_fee_tiers():
    fee_params = FeeParameters()
    assert compute_order_fee(0.0, fee_params) == 0.0
    assert compute_order_fee(500.0, fee_params) == 2.50
    assert compute_order_fee(1000.0, fee_params) == 2.50
    assert compute_order_fee(1000.01, fee_params) == 5.00
    assert compute_order_fee(1500.0, fee_params) == 5.00
    assert compute_order_fee(2000.0, fee_params) == 5.00
    assert compute_order_fee(2001.0, fee_params) == 7.50


def test_excludes_overweight_and_picks_top_two_distinct_themes():
    positions = [
        make_position("A", 90.0, 30.0, "TA"),
        make_position("B", 80.0, 10.0, "TB"),
        make_position("C", 78.0, 10.0, "TC"),
        make_position("D", 70.0, 10.0, "TD"),
        make_position("E", 60.0, 10.0, "TE"),
    ]

    plan = plan_deployment(positions, 1500.00)

    assert "A" in plan.excluded_overweight
    assert tuple(order.ticker for order in plan.orders) == ("B", "C")
    assert plan.total_fee == 5.00
    assert sum(order.amount for order in plan.orders) == 1500.00
    assert all(order.amount <= 1000.0 for order in plan.orders)
    assert plan.orders[0].amount > plan.orders[1].amount  # higher score gets more


def test_theme_cap_blocks_saturated_theme():
    positions = [
        make_position("A", 90.0, 15.0, "Semis"),
        make_position("B", 85.0, 15.0, "Semis"),  # Semis = 30% >= cap
        make_position("C", 70.0, 10.0, "Pharma"),
        make_position("D", 60.0, 8.0, "Data"),
    ]

    plan = plan_deployment(positions, 1500.00)

    assert tuple(order.ticker for order in plan.orders) == ("C", "D")
    assert "A" in plan.excluded_theme
    assert "B" in plan.excluded_theme


def test_distinct_theme_dedup_under_cap():
    positions = [
        make_position("A", 90.0, 8.0, "Semis"),
        make_position("B", 85.0, 8.0, "Semis"),  # Semis = 16% < cap, still deduped
        make_position("C", 70.0, 8.0, "Pharma"),
    ]

    plan = plan_deployment(positions, 1500.00)

    assert tuple(order.ticker for order in plan.orders) == ("A", "C")
    assert "B" in plan.excluded_theme


def test_two_orders_cost_same_as_one():
    positions = [
        make_position("A", 80.0, 10.0, "TA"),
        make_position("B", 70.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()

    plan = plan_deployment(positions, 1500.00, fee_params)

    assert plan.total_fee == compute_order_fee(1500.00, fee_params)


def test_large_cash_uses_fee_neutral_multi_order_plan():
    positions = [
        make_position("A", 90.0, 6.0, "TA"),
        make_position("B", 85.0, 6.0, "TB"),
        make_position("C", 80.0, 6.0, "TC"),
        make_position("D", 75.0, 6.0, "TD"),
        make_position("E", 70.0, 6.0, "TE"),
        make_position("F", 65.0, 6.0, "TF"),
    ]
    fee_params = FeeParameters()

    plan = plan_deployment(positions, 100_000.0, fee_params)

    assert len(plan.orders) == 6
    assert sum(order.amount for order in plan.orders) == 100_000.0
    assert plan.total_fee == compute_order_fee(100_000.0, fee_params)
    assert all(order.amount >= fee_params.min_order_amount_usd for order in plan.orders)
    assert tuple(order.ticker for order in plan.orders) == ("A", "B", "C", "D", "E", "F")


def test_does_not_deploy_cash_below_economic_minimum():
    positions = [
        make_position("A", 80.0, 10.0, "TA"),
        make_position("B", 70.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()

    plan = plan_deployment(positions, fee_params.min_order_amount_usd - 0.01, fee_params)

    assert plan.orders == ()
    assert plan.total_fee == 0.0


def test_uses_one_order_when_cash_cannot_fund_two_economic_orders():
    positions = [
        make_position("A", 80.0, 10.0, "TA"),
        make_position("B", 70.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()

    plan = plan_deployment(positions, fee_params.min_order_amount_usd * 1.5, fee_params)

    assert tuple(order.ticker for order in plan.orders) == ("A",)
    assert plan.orders[0].amount == fee_params.min_order_amount_usd * 1.5


def test_consolidates_in_subtranche_overpay_band():
    """Cash in (625, 1000] must not split into two sub-tranche orders.

    Two sub-tranche orders cost two tranches ($5.00) while one order covering the
    same cash costs a single tranche ($2.50). The planner must consolidate.
    """
    positions = [
        make_position("A", 60.0, 10.0, "TA"),
        make_position("B", 40.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()

    plan = plan_deployment(positions, 800.0, fee_params)

    assert len(plan.orders) == 1
    assert plan.total_fee == compute_order_fee(800.0, fee_params) == 2.50


def test_planner_never_overpays_single_order_fee_across_grid():
    """Property: the split fee never exceeds the single-order fee (subadditivity)."""
    positions = [
        make_position("A", 60.0, 10.0, "TA"),
        make_position("B", 40.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()

    for cash_cents in range(25_000, 500_000, 1_111):  # $250.00 .. $5000 in odd steps
        cash = cash_cents / 100
        plan = plan_deployment(positions, cash, fee_params)
        fee_ceiling = compute_order_fee(cash, fee_params) + 1e-9
        assert plan.total_fee <= fee_ceiling, f"overpaid at cash={cash}"


def test_fee_worsening_band_matches_closed_form():
    """With score share rho, the planner consolidates the overpay band."""
    # Scores 60/40 -> rho = 0.6; band lower edge = 250 / (1 - 0.6) = 625.
    positions = [
        make_position("A", 60.0, 10.0, "TA"),
        make_position("B", 40.0, 10.0, "TB"),
    ]
    fee_params = FeeParameters()
    rho = 60.0 / (60.0 + 40.0)
    lower_edge = fee_params.min_order_amount_usd / (1 - rho)
    assert lower_edge == 625.0
    tranche = fee_params.tranche_size_usd

    for cash in (lower_edge, 800.0, tranche):
        plan = plan_deployment(positions, cash, fee_params)
        assert len(plan.orders) == 1, f"expected consolidation at cash={cash}"
        assert plan.total_fee == compute_order_fee(cash, fee_params)

    # Above the tranche the split becomes fee-neutral and two orders are allowed.
    plan_two = plan_deployment(positions, 1100.0, fee_params)
    assert len(plan_two.orders) == 2
    assert plan_two.total_fee == compute_order_fee(1100.0, fee_params)
