"""Pure moat, compounding, and valuation scoring.

No I/O. Classification thresholds match arenawealth.services.FundamentalService
so results stay consistent across the platform.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from arenawealth.analytics.models import (
    Fundamentals,
    FundamentalScore,
    Holding,
    PositionAnalysis,
)

MOAT_WEIGHT = 0.40
COMPOUNDING_WEIGHT = 0.35
VALUATION_WEIGHT = 0.25
DEFAULT_TAX_RATE = 0.21


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def compound_annual_growth_rate(series: Sequence[float]) -> float | None:
    if len(series) < 2 or series[0] <= 0 or series[-1] <= 0:
        return None
    periods = len(series) - 1
    return (series[-1] / series[0]) ** (1 / periods) - 1


def coefficient_of_variation(series: Sequence[float]) -> float | None:
    if len(series) < 2:
        return None
    average = mean(series)
    if average == 0:
        return None
    variance = mean([(value - average) ** 2 for value in series])
    return math.sqrt(variance) / abs(average)


def roic_values(fund: Fundamentals) -> tuple[float, ...]:
    ebit = list(reversed(fund.ebit_series))
    invested = list(reversed(fund.invested_capital_series))
    taxes = list(reversed(fund.tax_rate_series))
    periods = min(len(ebit), len(invested))
    values = []
    for index in range(periods):
        capital = invested[index]
        if capital <= 0:
            continue
        tax_rate = taxes[index] if index < len(taxes) else DEFAULT_TAX_RATE
        values.append(ebit[index] * (1 - tax_rate) / capital)
    return tuple(values)


def operating_margin_series(fund: Fundamentals) -> tuple[float, ...]:
    if not fund.revenue_series or not fund.operating_income_series:
        return ()
    revenue = list(reversed(fund.revenue_series))
    income = list(reversed(fund.operating_income_series))
    periods = min(len(revenue), len(income))
    return tuple(income[index] / revenue[index] for index in range(periods) if revenue[index])


def fraction_at_least(values: Sequence[float], threshold: float) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value >= threshold) / len(values)


def shares_change(series: Sequence[float]) -> float | None:
    if len(series) < 2 or series[0] == 0:
        return None
    return (series[-1] - series[0]) / series[0]


def peg_ratio(forward_pe: float | None, eps_cagr: float | None) -> float | None:
    if forward_pe and eps_cagr and eps_cagr > 0:
        return forward_pe / (eps_cagr * 100)
    return None


def fcf_yield(fund: Fundamentals, exchange_rate: Callable[[str, str], float]) -> float | None:
    if not fund.free_cash_flow or not fund.market_cap or fund.market_cap <= 0:
        return None
    rate = 1.0
    foreign = (
        fund.financial_currency
        and fund.trading_currency
        and fund.financial_currency != fund.trading_currency
    )
    if foreign:
        rate = exchange_rate(fund.financial_currency, fund.trading_currency)
    return fund.free_cash_flow * rate / fund.market_cap


def moat_classification(
    is_financial: bool,
    roic: float | None,
    roe: float | None,
    margin_cv: float | None,
    pricing_power: float,
) -> str:
    if is_financial:
        return "STRONG" if roe is not None and roe >= 0.15 else "MODERATE"
    if roic is None:
        return "INSUFFICIENT_DATA"
    if roic >= 0.15 and margin_cv is not None and margin_cv <= 0.10:
        return "STRONG" if pricing_power >= 0.70 else "MODERATE"
    if roic < 0.10 or (margin_cv is not None and margin_cv > 0.25):
        return "WEAK"
    return "MODERATE"


def compounding_classification(
    fcf_cagr: float | None, eps_cagr: float | None, share_count_change: float | None
) -> str:
    if fcf_cagr is None or eps_cagr is None:
        return "INSUFFICIENT_DATA"
    if fcf_cagr >= 0.15 and eps_cagr >= 0.15:
        buys_back_stock = share_count_change is not None and share_count_change <= -0.05
        return "EXCELLENT" if buys_back_stock else "STRONG"
    if fcf_cagr >= 0.10 and eps_cagr > 0:
        return "GOOD"
    if fcf_cagr <= 0 or eps_cagr <= 0:
        return "POOR"
    return "MODERATE"


def moat_points(
    roic: float | None,
    roe: float | None,
    gross_margin: float | None,
    operating_margin: float | None,
    margin_cv: float | None,
) -> float:
    return_metric = roic if roic is not None else roe
    return_component = clamp((return_metric or 0) / 0.30 * 100)
    margin_level = gross_margin or operating_margin or 0
    margin_component = clamp(margin_level / 0.70 * 100)
    stability_component = clamp(100 - margin_cv * 400) if margin_cv is not None else 50.0
    return 0.50 * return_component + 0.25 * margin_component + 0.25 * stability_component


def growth_points(value: float | None) -> float:
    return clamp((value or 0) / 0.20 * 100)


def compounding_points(
    eps_cagr: float | None,
    fcf_cagr: float | None,
    revenue_cagr: float | None,
    share_count_change: float | None,
) -> float:
    if share_count_change is None:
        buyback_component = 50.0
    else:
        buyback_component = clamp(50 - share_count_change * 1000)
    return (
        0.35 * growth_points(eps_cagr)
        + 0.35 * growth_points(fcf_cagr)
        + 0.20 * growth_points(revenue_cagr)
        + 0.10 * buyback_component
    )


def valuation_points(
    yield_on_fcf: float | None, forward_pe: float | None, peg: float | None
) -> float:
    yield_component = clamp(yield_on_fcf / 0.06 * 100) if yield_on_fcf is not None else 50.0
    pe_component = clamp(100 - (forward_pe - 15) * 2) if forward_pe else 50.0
    peg_component = clamp(100 - (peg - 1) * 50) if peg else 50.0
    return 0.40 * yield_component + 0.35 * pe_component + 0.25 * peg_component


def score_fundamentals(
    fund: Fundamentals,
    is_financial: bool,
    exchange_rate: Callable[[str, str], float],
) -> FundamentalScore:
    roic_history = roic_values(fund)
    roic = mean(roic_history) if roic_history else None
    margin_cv = coefficient_of_variation(operating_margin_series(fund))
    eps_cagr = compound_annual_growth_rate(fund.eps_series)
    fcf_cagr = compound_annual_growth_rate(fund.fcf_series)
    revenue_cagr = compound_annual_growth_rate(fund.revenue_series)
    share_count_change = shares_change(fund.diluted_shares_series)
    yield_on_fcf = fcf_yield(fund, exchange_rate)
    peg = peg_ratio(fund.forward_pe, eps_cagr)

    moat = moat_points(
        roic, fund.return_on_equity, fund.gross_margin, fund.operating_margin, margin_cv
    )
    compounding = compounding_points(eps_cagr, fcf_cagr, revenue_cagr, share_count_change)
    valuation = valuation_points(yield_on_fcf, fund.forward_pe, peg)
    composite = (
        MOAT_WEIGHT * moat
        + COMPOUNDING_WEIGHT * compounding
        + VALUATION_WEIGHT * valuation
    )

    return FundamentalScore(
        roic=roic,
        roe=fund.return_on_equity,
        margin_cv=margin_cv,
        revenue_cagr=revenue_cagr,
        eps_cagr=eps_cagr,
        fcf_cagr=fcf_cagr,
        shares_change=share_count_change,
        fcf_yield=yield_on_fcf,
        forward_pe=fund.forward_pe,
        peg=peg,
        moat_class=moat_classification(
            is_financial,
            roic,
            fund.return_on_equity,
            margin_cv,
            fraction_at_least(roic_history, 0.15),
        ),
        compounding_class=compounding_classification(fcf_cagr, eps_cagr, share_count_change),
        moat_points=moat,
        compounding_points=compounding,
        valuation_points=valuation,
        composite_score=composite,
    )


def analyze(
    holding: Holding,
    fund: Fundamentals,
    total_market_value: float,
    exchange_rate: Callable[[str, str], float],
) -> PositionAnalysis:
    market_value = holding.shares * fund.live_price
    cost_basis = holding.shares * holding.average_cost
    score = score_fundamentals(fund, holding.is_financial, exchange_rate)
    return PositionAnalysis(
        holding=holding,
        live_price=fund.live_price,
        market_value=market_value,
        weight_pct=market_value / total_market_value * 100 if total_market_value else 0.0,
        pnl_pct=(market_value - cost_basis) / cost_basis * 100 if cost_basis else 0.0,
        price_gap_pct=(fund.live_price - holding.broker_price) / holding.broker_price * 100,
        roic=score.roic,
        roe=score.roe,
        margin_cv=score.margin_cv,
        revenue_cagr=score.revenue_cagr,
        eps_cagr=score.eps_cagr,
        fcf_cagr=score.fcf_cagr,
        shares_change=score.shares_change,
        fcf_yield=score.fcf_yield,
        forward_pe=score.forward_pe,
        peg=score.peg,
        moat_class=score.moat_class,
        compounding_class=score.compounding_class,
        moat_points=score.moat_points,
        compounding_points=score.compounding_points,
        valuation_points=score.valuation_points,
        composite_score=score.composite_score,
    )
