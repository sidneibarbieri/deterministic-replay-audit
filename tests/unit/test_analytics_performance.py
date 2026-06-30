"""Unit tests for performance metrics (hand-computed expectations)."""

import pytest

from arenawealth.analytics.performance import (
    annualized_volatility,
    cagr,
    cumulative_return,
    max_drawdown,
    sharpe_ratio,
    to_returns,
    turnover,
)


def test_to_returns():
    assert to_returns([100.0, 110.0, 121.0]) == pytest.approx((0.1, 0.1))
    assert to_returns([100.0]) == ()


def test_cumulative_return():
    assert cumulative_return((0.1, 0.1)) == pytest.approx(0.21)
    assert cumulative_return(()) == 0.0


def test_cagr():
    assert cagr((0.1, 0.1), periods_per_year=1) == pytest.approx(0.10)
    assert cagr((), periods_per_year=12) is None


def test_annualized_volatility():
    flat = annualized_volatility((0.05, 0.05, 0.05), periods_per_year=1)
    assert flat == pytest.approx(0.0, abs=1e-9)
    assert annualized_volatility((0.1, -0.1), periods_per_year=1) == pytest.approx(0.1)


def test_sharpe_ratio():
    assert sharpe_ratio((0.01, 0.01, 0.01), periods_per_year=12) == 0.0  # zero variance
    assert sharpe_ratio((0.02, 0.01, 0.03), periods_per_year=12) > 0.0


def test_max_drawdown():
    # equity: 1 -> 1.2 -> 0.6 -> 0.9; deepest from peak 1.2 to 0.6 = -50%
    assert max_drawdown((0.2, -0.5, 0.5)) == pytest.approx(-0.5)
    assert max_drawdown((0.1, 0.1)) == 0.0  # monotonic up


def test_turnover():
    previous = {"A": 0.5, "B": 0.5}
    current = {"A": 0.3, "B": 0.3, "C": 0.4}
    assert turnover(previous, current) == pytest.approx(0.4)
    assert turnover(previous, previous) == 0.0
