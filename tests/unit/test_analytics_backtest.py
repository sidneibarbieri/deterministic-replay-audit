"""Unit tests for the backtest engine (hand-computed expectations)."""

import pytest

from arenawealth.analytics.backtest import compare_backtests, normalize_weights, run_backtest


def test_buy_and_hold_single_asset():
    result = run_backtest({"A": (0.1, 0.1)}, {"A": 1.0}, periods_per_year=1)
    assert result.total_return == pytest.approx(0.21)
    assert result.cagr == pytest.approx(0.10)
    assert result.rebalances == 0
    assert result.total_cost == 0.0


def test_two_asset_buy_and_hold():
    returns = {"A": (0.2, 0.2), "B": (0.0, 0.0)}
    result = run_backtest(returns, {"A": 0.5, "B": 0.5}, periods_per_year=1)
    assert result.total_return == pytest.approx(0.22)


def test_weights_are_normalized():
    returns = {"A": (0.1, 0.1), "B": (0.1, 0.1)}
    result = run_backtest(returns, {"A": 2.0, "B": 2.0}, periods_per_year=1)
    assert result.total_return == pytest.approx(0.21)
    assert normalize_weights({"A": 0.0, "B": 2.0}) == {"B": 1.0}


def test_rebalance_incurs_cost():
    result = run_backtest(
        {"A": (0.2, 0.0), "B": (0.0, 0.0)},
        {"A": 0.5, "B": 0.5},
        periods_per_year=1,
        rebalance_every=1,
        cost_rate=0.01,
    )
    assert result.rebalances == 1
    assert result.total_cost > 0.0


def test_empty_weights_raise():
    with pytest.raises(ValueError, match="positive"):
        run_backtest({"A": (0.1,)}, {}, periods_per_year=1)


def test_negative_weights_raise():
    with pytest.raises(ValueError, match="non-negative"):
        run_backtest({"A": (0.1,)}, {"A": -1.0}, periods_per_year=1)


def test_missing_or_misaligned_returns_raise():
    with pytest.raises(ValueError, match="missing return series"):
        run_backtest({"A": (0.1,)}, {"A": 0.5, "B": 0.5}, periods_per_year=1)

    with pytest.raises(ValueError, match="equal length"):
        run_backtest(
            {"A": (0.1, 0.1), "B": (0.1,)},
            {"A": 0.5, "B": 0.5},
            periods_per_year=1,
        )


def test_invalid_backtest_parameters_raise():
    with pytest.raises(ValueError, match="periods_per_year"):
        run_backtest({"A": (0.1,)}, {"A": 1.0}, periods_per_year=0)

    with pytest.raises(ValueError, match="rebalance_every"):
        run_backtest({"A": (0.1,)}, {"A": 1.0}, periods_per_year=1, rebalance_every=-1)

    with pytest.raises(ValueError, match="cost_rate"):
        run_backtest({"A": (0.1,)}, {"A": 1.0}, periods_per_year=1, cost_rate=-0.01)


def test_compare_backtests_reports_excess_metrics():
    strategy = run_backtest({"A": (0.1, 0.1)}, {"A": 1.0}, periods_per_year=1)
    benchmark = run_backtest({"B": (0.05, 0.05)}, {"B": 1.0}, periods_per_year=1)

    comparison = compare_backtests(strategy, benchmark)

    assert comparison.excess_total_return == pytest.approx(0.1075)
    assert comparison.excess_cagr == pytest.approx(0.05)
    assert comparison.strategy is strategy
    assert comparison.benchmark is benchmark


def test_compare_backtests_requires_same_period_count():
    strategy = run_backtest({"A": (0.1, 0.1)}, {"A": 1.0}, periods_per_year=1)
    benchmark = run_backtest({"B": (0.05,)}, {"B": 1.0}, periods_per_year=1)

    with pytest.raises(ValueError, match="same number of periods"):
        compare_backtests(strategy, benchmark)
