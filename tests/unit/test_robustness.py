"""Unit tests for the robustness experiments (pure, fixed-seed, offline)."""

import numpy as np
import pytest

from arenawealth.experiments.robustness import (
    block_bootstrap_sharpe_diff,
    equal_weights,
    fixed_weight_returns,
    rolling_comparison,
)


def test_fixed_weight_returns_is_weighted_average():
    asset_returns = {"A": (0.02, -0.01, 0.03), "B": (0.0, 0.01, -0.01)}
    series = fixed_weight_returns(asset_returns, {"A": 0.5, "B": 0.5})
    assert series == pytest.approx((0.01, 0.0, 0.01))


def test_fixed_weight_returns_renormalizes_weights():
    asset_returns = {"A": (0.02, 0.04), "B": (0.0, 0.0)}
    # Weights 3:1 -> 0.75/0.25 after renormalization.
    series = fixed_weight_returns(asset_returns, {"A": 3.0, "B": 1.0})
    assert series == pytest.approx((0.015, 0.03))


def _two_assets(better_mean: float, worse_mean: float, periods: int = 600):
    rng = np.random.default_rng(0)
    better = rng.normal(loc=better_mean, scale=0.01, size=periods)
    worse = rng.normal(loc=worse_mean, scale=0.01, size=periods)
    return {"GOOD": better.tolist(), "BAD": worse.tolist()}


def test_rolling_comparison_favors_the_stronger_portfolio():
    asset_returns = _two_assets(better_mean=0.0015, worse_mean=0.0)
    result = rolling_comparison(
        asset_returns,
        weights_a={"GOOD": 1.0, "BAD": 0.0},
        weights_b={"GOOD": 0.0, "BAD": 1.0},
        window=120,
        step=20,
    )
    assert result.windows > 0
    assert result.win_rate_a > 0.8
    assert result.mean_sharpe_a > result.mean_sharpe_b


def test_block_bootstrap_ci_excludes_zero_for_clear_winner():
    asset_returns = _two_assets(better_mean=0.0015, worse_mean=0.0)
    result = block_bootstrap_sharpe_diff(
        asset_returns,
        weights_a={"GOOD": 1.0, "BAD": 0.0},
        weights_b={"GOOD": 0.0, "BAD": 1.0},
        samples=500,
        seed=42,
    )
    assert result.point_estimate > 0
    assert result.ci_low > 0
    assert result.prob_a_better > 0.95


def test_block_bootstrap_is_reproducible_under_fixed_seed():
    asset_returns = _two_assets(better_mean=0.001, worse_mean=0.0005)
    kwargs = {
        "weights_a": {"GOOD": 1.0, "BAD": 0.0},
        "weights_b": {"GOOD": 0.0, "BAD": 1.0},
        "samples": 300,
        "seed": 7,
    }
    first = block_bootstrap_sharpe_diff(asset_returns, **kwargs)
    second = block_bootstrap_sharpe_diff(asset_returns, **kwargs)
    assert first == second


def test_equal_weights_sum_to_one():
    weights = equal_weights(["A", "B", "C", "D"])
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(value == pytest.approx(0.25) for value in weights.values())
