"""Fee structure as an object of study.

The broker fee is a step function of order size:

    f(a) = ceil(a / T) * c        with tranche T = 1000, cost c = 2.50

This function is *subadditive*: f(a + b) <= f(a) + f(b). The proof is direct,
because ceil is subadditive and scaling by a positive constant preserves it.
The practical consequence is the central object here: splitting a fixed budget
into several orders can only keep fees equal or make them worse, never better.
So any policy that splits cash for diversification pays a measurable
*diversification fee premium*:

    premium(plan) = sum_i f(a_i) - f(sum_i a_i)

We sweep cash over a grid and compare three sizing policies against the
single-order lower bound, so the premium can be observed rather than assumed.
The 'engine' policy delegates to the production planner, which makes this module
double as a regression guard: after the fee-aware fix, 'engine' must hug the
fee-optimal frontier.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arenawealth.analytics.deployment import (
    FEE_PER_TRANCHE,
    MIN_ORDER_AMOUNT,
    TRANCHE_SIZE,
    order_fee,
    size_orders,
)
from arenawealth.analytics.models import Holding, PositionAnalysis


def _position(ticker: str, composite: float, theme: str, price: float = 100.0) -> PositionAnalysis:
    """Minimal analysis row; only composite_score and price drive sizing."""
    holding = Holding(ticker, ticker, 1.0, 1.0, price, theme, False)
    return PositionAnalysis(
        holding=holding,
        live_price=price,
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
        moat_points=0.0,
        compounding_points=0.0,
        valuation_points=0.0,
        composite_score=composite,
    )


def proportional_fee(cash: float, first_share: float) -> float:
    """Naive policy: split strictly by score share, account fees honestly.

    This is the policy a developer writes before noticing subadditivity. It is
    the one that overpays; we keep it to quantify how much.
    """
    if cash < MIN_ORDER_AMOUNT:
        return 0.0
    if cash < MIN_ORDER_AMOUNT * 2:
        return order_fee(cash)
    first = cash * first_share
    second = cash - first
    if first < MIN_ORDER_AMOUNT or second < MIN_ORDER_AMOUNT:
        return order_fee(cash)
    return order_fee(first) + order_fee(second)


def engine_fee(cash: float, scores: tuple[float, float] = (60.0, 40.0)) -> tuple[float, int]:
    """Fee and order count produced by the production planner."""
    picks = (
        _position("AAA", scores[0], "ThemeA"),
        _position("BBB", scores[1], "ThemeB"),
    )
    orders = size_orders(picks, cash)
    return sum(order.fee for order in orders), len(orders)


@dataclass(frozen=True)
class FeePoint:
    cash: float
    single_fee: float
    proportional_fee: float
    engine_fee: float
    engine_orders: int
    proportional_premium: float
    engine_premium: float
    engine_fee_pct: float


def fee_landscape(cash_grid: Sequence[float], first_share: float = 0.6) -> tuple[FeePoint, ...]:
    """Compare single-order, naive-proportional, and engine fees across cash."""
    points: list[FeePoint] = []
    for cash in cash_grid:
        single = order_fee(cash)
        prop = proportional_fee(cash, first_share)
        eng, eng_orders = engine_fee(cash, (first_share * 100, (1 - first_share) * 100))
        points.append(
            FeePoint(
                cash=cash,
                single_fee=single,
                proportional_fee=prop,
                engine_fee=eng,
                engine_orders=eng_orders,
                proportional_premium=prop - single,
                engine_premium=eng - single,
                engine_fee_pct=(eng / cash * 100) if cash > 0 else 0.0,
            )
        )
    return tuple(points)


@dataclass(frozen=True)
class GuardrailReport:
    min_order_amount: float
    one_percent_fixed_point: float
    first_order_cash: float
    second_order_cash: float


def guardrail_report() -> GuardrailReport:
    """Derive the guardrail thresholds in closed form from the fee model.

    MIN_ORDER_AMOUNT is the cash level where a single tranche fee equals exactly
    MAX_FEE_PCT of the order. It is a fixed point of the cost model, not a tuned
    constant. The first order can be placed at MIN_ORDER_AMOUNT; a second
    economic order needs twice that.
    """
    fixed_point = FEE_PER_TRANCHE / 0.01  # fee == 1% of order
    return GuardrailReport(
        min_order_amount=MIN_ORDER_AMOUNT,
        one_percent_fixed_point=fixed_point,
        first_order_cash=MIN_ORDER_AMOUNT,
        second_order_cash=MIN_ORDER_AMOUNT * 2,
    )


def worst_case_premium(cash_grid: Sequence[float], first_share: float = 0.6) -> FeePoint:
    """The grid point where the naive split overpays the most (absolute)."""
    landscape = fee_landscape(cash_grid, first_share)
    return max(landscape, key=lambda point: point.proportional_premium)


def tranche_boundary(cash: float) -> float:
    """Smallest single-tranche-preserving split: align one leg to a boundary."""
    return min(TRANCHE_SIZE, cash)
