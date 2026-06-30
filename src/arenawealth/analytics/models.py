"""Data transfer objects for moat and compounding analysis.

These are plain immutable values. Analysis uses float rather than the domain
layer's Decimal because the calculations are statistical, not monetary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    ticker: str
    name: str
    shares: float
    average_cost: float
    broker_price: float
    theme: str
    is_financial: bool


@dataclass(frozen=True)
class Fundamentals:
    live_price: float
    market_cap: float | None
    return_on_equity: float | None
    gross_margin: float | None
    operating_margin: float | None
    forward_pe: float | None
    fifty_two_week_high: float | None
    analyst_target: float | None
    free_cash_flow: float | None
    financial_currency: str | None
    trading_currency: str | None
    revenue_series: tuple[float, ...]
    ebit_series: tuple[float, ...]
    tax_rate_series: tuple[float, ...]
    operating_income_series: tuple[float, ...]
    eps_series: tuple[float, ...]
    fcf_series: tuple[float, ...]
    diluted_shares_series: tuple[float, ...]
    invested_capital_series: tuple[float, ...]


@dataclass(frozen=True)
class FundamentalScore:
    roic: float | None
    roe: float | None
    margin_cv: float | None
    revenue_cagr: float | None
    eps_cagr: float | None
    fcf_cagr: float | None
    shares_change: float | None
    fcf_yield: float | None
    forward_pe: float | None
    peg: float | None
    moat_class: str
    compounding_class: str
    moat_points: float
    compounding_points: float
    valuation_points: float
    composite_score: float


@dataclass(frozen=True)
class PositionAnalysis:
    holding: Holding
    live_price: float
    market_value: float
    weight_pct: float
    pnl_pct: float
    price_gap_pct: float
    roic: float | None
    roe: float | None
    margin_cv: float | None
    revenue_cagr: float | None
    eps_cagr: float | None
    fcf_cagr: float | None
    shares_change: float | None
    fcf_yield: float | None
    forward_pe: float | None
    peg: float | None
    moat_class: str
    compounding_class: str
    moat_points: float
    compounding_points: float
    valuation_points: float
    composite_score: float


@dataclass(frozen=True)
class Order:
    ticker: str
    amount: float
    shares: float
    fee: float


@dataclass(frozen=True)
class DeploymentPlan:
    orders: tuple[Order, ...]
    total_fee: float
    excluded_overweight: tuple[str, ...]
    excluded_theme: tuple[str, ...]
    top_candidates: tuple[tuple[str, float], ...]
