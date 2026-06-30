"""Deterministic, fee-aware cash deployment.

This module implements a fee-optimal cash allocation strategy that respects:
1. Concentration limits: positions above 1.3x equal weight are ineligible.
2. Fee efficiency: splits are only diversified when fee-neutral.
3. Theme diversification: picks are drawn from distinct themes.
4. Determinism: ties broken by ticker for reproducible ordering.

The key fee invariant is sub-tranche fee-worsening: naive proportional splits in
the range [$625, $1000] incur an extra tranche fee. The fix diversifies only
when the split is fee-neutral.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from arenawealth.analytics.models import DeploymentPlan, Order, PositionAnalysis
from arenawealth.fee_contract import (
    FeeParameters,
    compute_order_fee,
)

MAX_LARGE_CASH_ORDERS = 6


@dataclass(frozen=True)
class ConcentrationLimits:
    """Portfolio concentration rules."""

    overweight_multiple: float = 1.3
    theme_concentration_cap_pct: float = 20.0

def compute_theme_weights(
    analyses: Sequence[PositionAnalysis],
) -> dict[str, float]:
    """Aggregate portfolio weight by theme.

    Args:
        analyses: Current position analyses.

    Returns:
        Mapping from theme to cumulative weight percentage.
    """
    theme_weight_map: dict[str, float] = {}
    for analysis in analyses:
        theme = analysis.holding.theme
        theme_weight_map[theme] = theme_weight_map.get(theme, 0.0) + analysis.weight_pct
    return theme_weight_map


def select_eligible_for_purchase(
    ranked_analyses: Sequence[PositionAnalysis],
    theme_weights: dict[str, float],
    concentration_limits: ConcentrationLimits,
    max_picks: int = 2,
) -> tuple[list[PositionAnalysis], list[str]]:
    """Select top candidates respecting theme and concentration rules.

    Args:
        ranked_analyses: Candidates sorted by composite score (descending).
        theme_weights: Current weight by theme.
        concentration_limits: Portfolio rules.
        max_picks: Maximum candidates to select (typically 2 for fee efficiency).

    Returns:
        Tuple of (selected analyses, blocked ticker symbols).
    """
    selected_picks: list[PositionAnalysis] = []
    blocked_tickers: list[str] = []
    used_themes: set[str] = set()

    for analysis in ranked_analyses:
        if len(selected_picks) >= max_picks:
            break

        theme = analysis.holding.theme
        is_theme_saturated = (
            theme_weights.get(theme, 0.0) >= concentration_limits.theme_concentration_cap_pct
        )
        is_theme_used = theme in used_themes

        if is_theme_saturated or is_theme_used:
            blocked_tickers.append(analysis.holding.ticker)
            continue

        selected_picks.append(analysis)
        used_themes.add(theme)

    return selected_picks, blocked_tickers


def max_orders_for_cash(cash_usd: float, fee_params: FeeParameters) -> int:
    """Return the maximum order count supported by the cash regime."""
    if cash_usd < fee_params.tranche_size_usd * 3:
        return 2
    tranche_count = max(1, int(cash_usd // fee_params.tranche_size_usd))
    return min(MAX_LARGE_CASH_ORDERS, tranche_count)


def build_single_order(
    analysis: PositionAnalysis,
    amount_usd: float,
    fee_params: FeeParameters,
) -> Order:
    """Create a buy order for a single security.

    Args:
        analysis: Position analysis with current price.
        amount_usd: Dollar amount to allocate.
        fee_params: Fee model.

    Returns:
        Order with computed shares and fee.
    """
    fee_usd = compute_order_fee(amount_usd, fee_params)
    shares = amount_usd / analysis.live_price
    return Order(
        ticker=analysis.holding.ticker,
        amount=amount_usd,
        shares=shares,
        fee=fee_usd,
    )


def compute_score_based_split(
    first_analysis: PositionAnalysis,
    second_analysis: PositionAnalysis,
    total_cash_usd: float,
) -> tuple[float, float]:
    """Allocate cash between two securities by score share.

    Args:
        first_analysis: Primary candidate.
        second_analysis: Secondary candidate.
        total_cash_usd: Total budget to split.

    Returns:
        Tuple of (first_amount_usd, second_amount_usd) summing to total_cash_usd.
    """
    total_score = first_analysis.composite_score + second_analysis.composite_score
    first_fraction = first_analysis.composite_score / total_score
    first_amount = total_cash_usd * first_fraction
    second_amount = total_cash_usd - first_amount
    return first_amount, second_amount


def allocate_tranche_units(
    candidates: Sequence[PositionAnalysis],
    cash_usd: float,
    fee_params: FeeParameters,
) -> tuple[float, ...]:
    """Allocate large cash as fee-neutral tranche-sized orders."""
    tranche_count = math.ceil(cash_usd / fee_params.tranche_size_usd)
    candidate_count = min(len(candidates), tranche_count, MAX_LARGE_CASH_ORDERS)
    selected = candidates[:candidate_count]
    if not selected:
        return ()

    total_score = sum(candidate.composite_score for candidate in selected)
    if total_score <= 0:
        unit_targets = [tranche_count / candidate_count for _ in selected]
    else:
        unit_targets = [
            candidate.composite_score / total_score * tranche_count for candidate in selected
        ]

    units = [max(1, math.floor(target)) for target in unit_targets]
    while sum(units) > tranche_count:
        reducible_indexes = [
            index for index, unit_count in enumerate(units) if unit_count > 1
        ]
        if not reducible_indexes:
            return ()
        index_to_reduce = min(
            reducible_indexes,
            key=lambda index: unit_targets[index] - math.floor(unit_targets[index]),
        )
        units[index_to_reduce] -= 1

    while sum(units) < tranche_count:
        index_to_increase = max(
            range(candidate_count),
            key=lambda index: unit_targets[index] - math.floor(unit_targets[index]),
        )
        units[index_to_increase] += 1

    amounts = [unit_count * fee_params.tranche_size_usd for unit_count in units]
    overage = sum(amounts) - cash_usd
    if overage > 0:
        reducible_indexes = [
            index
            for index, amount in enumerate(amounts)
            if amount - overage >= fee_params.min_order_amount_usd
        ]
        if not reducible_indexes:
            return ()
        index_to_reduce = max(reducible_indexes, key=lambda index: amounts[index])
        amounts[index_to_reduce] -= overage

    if any(amount < fee_params.min_order_amount_usd for amount in amounts):
        return ()
    return tuple(amounts)


def is_split_fee_neutral(
    split_orders: Sequence[Order],
    single_order: Order,
) -> bool:
    """Check if a multi-order split incurs the same total fee as consolidation.

    A split is fee-neutral iff the sum of tranche fees equals the single-order
    fee. Splits are only viable when fee-neutral; otherwise, consolidation is
    cost-efficient.

    Args:
        split_orders: Multi-order split.
        single_order: Consolidated single-order alternative.

    Returns:
        True if split fee equals single-order fee.
    """
    split_fee_total = sum(order.fee for order in split_orders)
    return split_fee_total <= single_order.fee


def build_fee_neutral_large_cash_orders(
    candidates: Sequence[PositionAnalysis],
    cash_usd: float,
    fee_params: FeeParameters,
) -> tuple[Order, ...]:
    """Build a deterministic multi-order plan for large cash deployments."""
    amounts = allocate_tranche_units(candidates, cash_usd, fee_params)
    return tuple(
        build_single_order(candidate, amount, fee_params)
        for candidate, amount in zip(candidates, amounts, strict=False)
    )


def size_orders_for_cash(
    candidates: Sequence[PositionAnalysis],
    cash_usd: float,
    fee_params: FeeParameters,
) -> tuple[Order, ...]:
    """Size orders to deploy cash while maintaining fee efficiency.

    Implements the latent-defect fix: diversifies only when fee-neutral.
    For sub-tranche cash ($250-$1000), naive proportional splits incur an
    extra fee. This function aligns splits to fee-optimal boundaries.

    Args:
        candidates: Eligible positions ranked by score.
        cash_usd: Available cash to deploy.
        fee_params: Fee model with floor and tranche sizes.

    Returns:
        Tuple of orders. Typically 0 (insufficient), 1 (single), or 2 (split).
    """
    min_order = fee_params.min_order_amount_usd

    if not candidates or cash_usd < min_order:
        return ()

    single_order = build_single_order(candidates[0], cash_usd, fee_params)

    if len(candidates) >= 3 and cash_usd >= fee_params.tranche_size_usd * 3:
        large_cash_orders = build_fee_neutral_large_cash_orders(
            candidates, cash_usd, fee_params
        )
        if large_cash_orders and is_split_fee_neutral(large_cash_orders, single_order):
            return large_cash_orders

    if len(candidates) < 2 or cash_usd < min_order * 2:
        return (single_order,)

    first_amount, second_amount = compute_score_based_split(
        candidates[0], candidates[1], cash_usd
    )

    if first_amount < min_order or second_amount < min_order:
        return (single_order,)

    first_order = build_single_order(candidates[0], first_amount, fee_params)
    second_order = build_single_order(candidates[1], second_amount, fee_params)
    split_orders = (first_order, second_order)

    if not is_split_fee_neutral(split_orders, single_order):
        return (single_order,)

    return split_orders


def plan_deployment(
    analyses: Sequence[PositionAnalysis],
    cash_usd: float,
    fee_params: FeeParameters | None = None,
    concentration_limits: ConcentrationLimits | None = None,
) -> DeploymentPlan:
    """Generate a deterministic, fee-efficient cash deployment plan.

    Args:
        analyses: Current portfolio position analyses.
        cash_usd: Available cash to deploy.
        fee_params: Fee model (uses defaults if None).
        concentration_limits: Portfolio rules (uses defaults if None).

    Returns:
        Deployment plan with orders, fees, and exclusion reasons.

    Raises:
        ValueError: If analyses is empty.
    """
    if not analyses:
        raise ValueError("analyses cannot be empty")

    fee_params = fee_params or FeeParameters()
    concentration_limits = concentration_limits or ConcentrationLimits()

    equal_weight_pct = 100.0 / len(analyses)
    overweight_threshold = equal_weight_pct * concentration_limits.overweight_multiple

    eligible_analyses = [
        analysis
        for analysis in analyses
        if analysis.weight_pct <= overweight_threshold
    ]
    overweight_tickers = tuple(
        analysis.holding.ticker
        for analysis in analyses
        if analysis.weight_pct > overweight_threshold
    )

    ranked_by_score = sorted(
        eligible_analyses,
        key=lambda analysis: (-analysis.composite_score, analysis.holding.ticker),
    )

    theme_weights_map = compute_theme_weights(analyses)
    max_picks = max_orders_for_cash(cash_usd, fee_params)
    candidates, theme_blocked_tickers = select_eligible_for_purchase(
        ranked_by_score, theme_weights_map, concentration_limits, max_picks=max_picks
    )

    orders = size_orders_for_cash(candidates, cash_usd, fee_params)

    top_six_candidates = tuple(
        (analysis.holding.ticker, analysis.composite_score)
        for analysis in ranked_by_score[:6]
    )

    return DeploymentPlan(
        orders=orders,
        total_fee=sum(order.fee for order in orders),
        excluded_overweight=overweight_tickers,
        excluded_theme=tuple(theme_blocked_tickers),
        top_candidates=top_six_candidates,
    )


# Scalar helpers bound to the default fee model. The experiment scripts reason
# about a single cash amount under one fee schedule, so they call these rather
# than threading a FeeParameters instance through every call site.
_default_fee_params = FeeParameters()
MIN_ORDER_AMOUNT: float = _default_fee_params.min_order_amount_usd
TRANCHE_SIZE: float = _default_fee_params.tranche_size_usd
FEE_PER_TRANCHE: float = _default_fee_params.fee_per_tranche_usd


def order_fee(amount: float) -> float:
    """Broker fee for one order under the default fee schedule."""
    return compute_order_fee(amount, _default_fee_params)


def size_orders(picks: Sequence[PositionAnalysis], cash: float) -> tuple[Order, ...]:
    """Size orders for the given cash under the default fee schedule."""
    return size_orders_for_cash(picks, cash, _default_fee_params)
