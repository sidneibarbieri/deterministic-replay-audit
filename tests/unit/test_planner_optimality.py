"""Unit tests for the planner-vs-MIP optimality check (pure, offline)."""

from arenawealth.experiments.planner_optimality import (
    planner_optimality,
    reference_report,
    reference_scenario,
)


def test_planner_matches_mip_and_fee_floor_in_design_regime():
    report = reference_report()

    assert report.points
    # The planner is exactly deployment-optimal and fee-optimal in its design regime.
    assert report.max_deployment_gap == 0.0
    assert report.max_fee_premium == 0.0
    for point in report.points:
        assert point.deployed_planner == point.cash
        assert point.fee_planner == point.fee_lower_bound


def test_mip_upper_bound_matches_planner_with_one_candidate():
    tight = (
        reference_scenario()[0],
    )
    report = planner_optimality(tight, (250.0, 500.0))
    for point in report.points:
        assert point.deployment_gap == 0.0
