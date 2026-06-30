"""Unit tests for the pure scoring functions (no network)."""

import pytest

from arenawealth.analytics.models import Fundamentals, Holding
from arenawealth.analytics.scoring import (
    analyze,
    clamp,
    coefficient_of_variation,
    compound_annual_growth_rate,
    compounding_classification,
    fcf_yield,
    moat_classification,
    score_fundamentals,
)


def make_fundamentals(**overrides) -> Fundamentals:
    base = dict(
        live_price=50.0,
        market_cap=200.0,
        return_on_equity=0.30,
        gross_margin=0.60,
        operating_margin=0.22,
        forward_pe=20.0,
        fifty_two_week_high=60.0,
        analyst_target=55.0,
        free_cash_flow=15.0,
        financial_currency="USD",
        trading_currency="USD",
        revenue_series=(100.0, 110.0, 121.0),
        ebit_series=(20.0, 22.0, 25.0),
        tax_rate_series=(0.20, 0.20, 0.20),
        operating_income_series=(20.0, 22.0, 25.0),
        eps_series=(1.0, 1.2, 1.44),
        fcf_series=(10.0, 12.0, 15.0),
        diluted_shares_series=(100.0, 98.0, 96.0),
        invested_capital_series=(100.0, 105.0, 110.0),
    )
    base.update(overrides)
    return Fundamentals(**base)


def make_holding(is_financial: bool = False) -> Holding:
    return Holding("X", "Example Co", 10.0, 40.0, 49.0, "Tech", is_financial)


def test_cagr_basic():
    assert compound_annual_growth_rate((100.0, 110.0, 121.0)) == pytest.approx(0.10)


def test_cagr_needs_two_positive_points():
    assert compound_annual_growth_rate((100.0,)) is None
    assert compound_annual_growth_rate((0.0, 100.0)) is None
    assert compound_annual_growth_rate((100.0, -5.0)) is None


def test_coefficient_of_variation():
    assert coefficient_of_variation((10.0, 10.0, 10.0)) == 0.0
    assert coefficient_of_variation((10.0,)) is None
    assert coefficient_of_variation((8.0, 12.0)) == pytest.approx(0.2)


def test_clamp_bounds():
    assert clamp(-5.0) == 0.0
    assert clamp(150.0) == 100.0
    assert clamp(42.0) == 42.0


def test_fcf_yield_same_currency_ignores_rate():
    fund = make_fundamentals(free_cash_flow=100.0, market_cap=1000.0)
    assert fcf_yield(fund, lambda base, quote: 999.0) == pytest.approx(0.10)


def test_fcf_yield_currency_adjusted():
    fund = make_fundamentals(
        free_cash_flow=100.0, market_cap=1000.0,
        financial_currency="TWD", trading_currency="USD",
    )
    calls = []

    def rate(base: str, quote: str) -> float:
        calls.append((base, quote))
        return 0.03

    assert fcf_yield(fund, rate) == pytest.approx(0.003)
    assert calls == [("TWD", "USD")]


def test_moat_classification_strong_and_weak():
    assert moat_classification(False, 0.20, 0.30, 0.05, 0.80) == "STRONG"
    assert moat_classification(False, 0.05, 0.10, 0.05, 0.80) == "WEAK"


def test_moat_classification_financial_uses_roe():
    assert moat_classification(True, None, 0.20, None, 0.0) == "STRONG"
    assert moat_classification(True, None, None, None, 0.0) == "MODERATE"


def test_compounding_classification_tiers():
    assert compounding_classification(0.20, 0.20, -0.06) == "EXCELLENT"
    assert compounding_classification(0.20, 0.20, 0.0) == "STRONG"
    assert compounding_classification(0.12, 0.05, 0.0) == "GOOD"
    assert compounding_classification(-0.10, 0.20, 0.0) == "POOR"


def test_analyze_integration():
    result = analyze(make_holding(), make_fundamentals(), 500.0, lambda base, quote: 1.0)

    assert result.weight_pct == pytest.approx(100.0)
    assert result.pnl_pct == pytest.approx(25.0)
    assert result.roic == pytest.approx(0.1698, abs=1e-3)
    assert result.eps_cagr == pytest.approx(0.20)
    assert result.moat_class == "STRONG"
    assert result.compounding_class == "STRONG"
    assert 0.0 <= result.composite_score <= 100.0


def test_score_fundamentals_matches_analyze():
    fund = make_fundamentals()
    score = score_fundamentals(fund, is_financial=False, exchange_rate=lambda base, quote: 1.0)
    analysis = analyze(make_holding(), fund, 500.0, lambda base, quote: 1.0)

    assert score.moat_class == analysis.moat_class
    assert score.composite_score == analysis.composite_score
    assert score.roic == analysis.roic
