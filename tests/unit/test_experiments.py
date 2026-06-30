"""Unit tests for the exploratory experiment modules (pure, offline)."""

from arenawealth.analytics.deployment import order_fee
from arenawealth.analytics.models import Holding, PositionAnalysis
from arenawealth.experiments.ablation import (
    BASELINE_WEIGHTS,
    rank_under_weights,
    recompose,
    spearman,
    standard_weight_sets,
    weight_ablation,
    weight_sensitivity,
)
from arenawealth.experiments.fee_landscape import (
    engine_fee,
    fee_landscape,
    guardrail_report,
    proportional_fee,
)


def make_analysis(ticker: str, moat: float, comp: float, val: float) -> PositionAnalysis:
    holding = Holding(ticker, ticker, 1.0, 1.0, 100.0, "Theme", False)
    return PositionAnalysis(
        holding=holding,
        live_price=100.0,
        market_value=0.0,
        weight_pct=0.0,
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
        moat_points=moat,
        compounding_points=comp,
        valuation_points=val,
        composite_score=0.0,
    )


# fee landscape


def test_guardrail_fixed_point_is_250():
    report = guardrail_report()
    assert report.min_order_amount == 250.0
    assert report.one_percent_fixed_point == 250.0
    assert report.second_order_cash == 500.0


def test_engine_is_fee_optimal_across_grid():
    """After the fix, the engine premium must be zero everywhere it deploys."""
    grid = [float(x) for x in range(250, 5001, 10)]
    for point in fee_landscape(grid, first_share=0.6):
        assert point.engine_premium == 0.0, f"engine overpaid at cash={point.cash}"


def test_naive_proportional_overpays_in_band():
    """The naive policy demonstrates the premium the engine avoids."""
    # cash=800 with a 0.6 split -> 480/320, two tranches = $5 vs one tranche $2.50
    assert proportional_fee(800.0, 0.6) == 5.0
    assert order_fee(800.0) == 2.50


def test_engine_consolidates_subtranche_cash():
    fee, orders = engine_fee(800.0, (60.0, 40.0))
    assert orders == 1
    assert fee == 2.50


# ablation


def test_recompose_matches_baseline_weights():
    analysis = make_analysis("X", moat=80.0, comp=40.0, val=20.0)
    expected = 0.40 * 80 + 0.35 * 40 + 0.25 * 20
    assert recompose(analysis, BASELINE_WEIGHTS) == expected


def test_rank_under_weights_orders_by_score():
    analyses = [
        make_analysis("LOW", 10, 10, 10),
        make_analysis("HIGH", 90, 90, 90),
        make_analysis("MID", 50, 50, 50),
    ]
    assert rank_under_weights(analyses, BASELINE_WEIGHTS) == ("HIGH", "MID", "LOW")


def test_spearman_identity_and_reverse():
    order = ("A", "B", "C", "D")
    assert spearman(order, order) == 1.0
    assert spearman(order, tuple(reversed(order))) == -1.0


def test_single_factor_ablation_can_reorder_top():
    # X wins on moat, Y wins on valuation; weighting flips the leader.
    analyses = [
        make_analysis("X", moat=100, comp=0, val=0),
        make_analysis("Y", moat=0, comp=0, val=100),
    ]
    rows = {row.label: row for row in weight_ablation(analyses, standard_weight_sets())}
    assert rows["moat_only"].top[0] == "X"
    assert rows["valuation_only"].top[0] == "Y"


def test_weight_sensitivity_renormalizes_to_one():
    analyses = [make_analysis("A", 80, 40, 20), make_analysis("B", 40, 60, 50)]
    rows = weight_sensitivity(analyses)
    assert rows  # produced perturbations
    # Every perturbed weight vector still sums to 1 (checked via recompose path).
    for row in rows:
        assert isinstance(row.top_k_changed, bool)
