"""Unit tests for long-only allocators (no network, no SciPy)."""

import math

import numpy as np
import pytest

from arenawealth.analytics.allocators import (
    covariance_matrix,
    equal_weights,
    min_variance_weights,
    risk_parity_weights,
)


def _approx_weights(weights: dict[str, float], expected: dict[str, float]) -> None:
    assert weights.keys() == expected.keys()
    for ticker, weight in expected.items():
        assert math.isclose(weights[ticker], weight, abs_tol=1e-6), (
            f"{ticker}: {weights[ticker]} != {weight}"
        )


def test_equal_weights_uniform():
    returns = {"A": (0.01, -0.02, 0.03), "B": (0.0, 0.01, -0.01), "C": (0.02, 0.0, 0.01)}
    _approx_weights(equal_weights(returns), {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})


def test_min_variance_picks_lower_variance_asset():
    """Between two uncorrelated assets, weight goes to the lower-variance one."""
    rng = np.random.default_rng(42)
    low_variance = rng.normal(scale=0.01, size=200).tolist()
    high_variance = rng.normal(scale=0.05, size=200).tolist()
    weights = min_variance_weights({"LOW": low_variance, "HIGH": high_variance})
    assert weights["LOW"] > weights["HIGH"]
    assert math.isclose(weights["LOW"] + weights["HIGH"], 1.0)


def test_covariance_shrinkage_moves_toward_diagonal_target():
    returns = {
        "A": (0.01, 0.02, -0.01, 0.03),
        "B": (0.02, 0.04, -0.02, 0.06),
    }

    tickers, shrunk = covariance_matrix(returns, shrinkage=1.0)

    assert tickers == ("A", "B")
    assert shrunk[0, 1] == pytest.approx(0.0)
    assert shrunk[0, 0] == pytest.approx(shrunk[1, 1])


def test_covariance_rejects_invalid_shrinkage():
    with pytest.raises(ValueError, match="shrinkage"):
        covariance_matrix({"A": (0.01, 0.02), "B": (0.0, 0.01)}, shrinkage=1.1)


def test_min_variance_long_only_drops_negative():
    """High correlation with mismatched variances can produce negative closed-form
    weights, which the active-set must clip."""
    rng = np.random.default_rng(0)
    base = rng.normal(scale=0.01, size=300)
    noise = rng.normal(scale=0.001, size=300)
    returns = {
        "LOW": base.tolist(),
        "HIGH_CORR": (base * 2 + noise).tolist(),  # correlated, much higher variance
        "INDEP": rng.normal(scale=0.02, size=300).tolist(),
    }
    weights = min_variance_weights(returns)
    assert all(weight >= 0 for weight in weights.values())
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)


def test_risk_parity_equalizes_contributions():
    """With assets of different variances, ERC weights inversely scale by volatility."""
    rng = np.random.default_rng(7)
    low = rng.normal(scale=0.01, size=300).tolist()
    high = rng.normal(scale=0.04, size=300).tolist()
    weights = risk_parity_weights({"LOW": low, "HIGH": high})
    # Verify equal risk contributions: w_i * (Sigma w)_i should be equal.
    tickers, sigma = covariance_matrix({"LOW": low, "HIGH": high})
    weight_vector = np.array([weights[ticker] for ticker in tickers])
    contributions = weight_vector * (sigma @ weight_vector)
    assert math.isclose(contributions[0], contributions[1], rel_tol=1e-4)
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)


def test_risk_parity_uniform_when_iid_assets():
    """Three i.i.d. assets should produce roughly equal risk-parity weights."""
    rng = np.random.default_rng(99)
    returns = {ticker: rng.normal(scale=0.01, size=500).tolist() for ticker in ("A", "B", "C")}
    weights = risk_parity_weights(returns)
    for weight in weights.values():
        assert math.isclose(weight, 1 / 3, abs_tol=0.05)


def test_all_allocators_long_only_and_summing_to_one():
    rng = np.random.default_rng(123)
    returns = {ticker: rng.normal(scale=0.02, size=300).tolist() for ticker in "ABCDE"}
    for allocator in (equal_weights, min_variance_weights, risk_parity_weights):
        weights = allocator(returns)
        assert all(weight >= 0 for weight in weights.values()), allocator.__name__
        assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9), allocator.__name__


def test_min_variance_requires_two_observations():
    with pytest.raises(ValueError):
        min_variance_weights({"A": (0.01,)})


def test_equal_weights_rejects_empty():
    with pytest.raises(ValueError):
        equal_weights({})
