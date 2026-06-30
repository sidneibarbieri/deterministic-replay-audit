"""Long-only portfolio allocators over a return matrix.

Each function takes an aligned return matrix (`dict[ticker, sequence[float]]`)
and returns a weight dict that sums to 1 with all weights non-negative. The
functions are pure and depend only on numpy. They are intended as honest SOTA
baselines for backtests, not investment advice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

ReturnMatrix = Mapping[str, Sequence[float]]

MAX_ITERATIONS = 1000
CONVERGENCE_TOLERANCE = 1e-9


def _aligned_returns(returns: ReturnMatrix) -> tuple[tuple[str, ...], np.ndarray]:
    """Return tickers sorted for determinism and a (n_assets, n_periods) matrix."""
    tickers = tuple(sorted(returns))
    matrix = np.array([returns[ticker] for ticker in tickers], dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] < 2:
        raise ValueError("each ticker must have at least two return observations")
    return tickers, matrix


def covariance_matrix(
    returns: ReturnMatrix, shrinkage: float = 0.0
) -> tuple[tuple[str, ...], np.ndarray]:
    """Sample covariance with optional constant-variance shrinkage."""
    if not 0.0 <= shrinkage <= 1.0:
        raise ValueError("shrinkage must be between 0 and 1")
    tickers, matrix = _aligned_returns(returns)
    sample = np.cov(matrix)
    if shrinkage == 0.0:
        return tickers, sample
    average_variance = float(np.mean(np.diag(sample)))
    target = np.eye(len(tickers)) * average_variance
    return tickers, (1.0 - shrinkage) * sample + shrinkage * target


def equal_weights(returns: ReturnMatrix) -> dict[str, float]:
    """1/N over the assets present in the return matrix."""
    tickers = tuple(sorted(returns))
    if not tickers:
        raise ValueError("returns must contain at least one ticker")
    weight = 1.0 / len(tickers)
    return {ticker: weight for ticker in tickers}


def min_variance_weights(
    returns: ReturnMatrix, shrinkage: float = 0.0
) -> dict[str, float]:
    """Long-only minimum-variance weights via active-set on the closed form.

    The unconstrained minimum is w* = sigma_inv @ 1 / (1' sigma_inv @ 1). When
    any weight is negative we drop the most negative asset and re-solve over the
    remaining ones, repeating until all weights are non-negative. For
    well-conditioned equity covariance matrices this converges in a handful of
    iterations.
    """
    tickers, sigma = covariance_matrix(returns, shrinkage=shrinkage)
    if np.any(np.diag(sigma) <= 0):
        raise ValueError("every asset must have positive variance")
    active = list(range(len(tickers)))
    while True:
        if not active:
            raise ValueError("no assets left after active-set reduction")
        sub_sigma = sigma[np.ix_(active, active)]
        ones = np.ones(len(active))
        try:
            inverse_times_ones = np.linalg.solve(sub_sigma, ones)
        except np.linalg.LinAlgError as error:
            raise ValueError("covariance matrix is singular for active set") from error
        sub_weights = inverse_times_ones / inverse_times_ones.sum()
        worst_index = int(np.argmin(sub_weights))
        if sub_weights[worst_index] >= 0:
            full_weights = np.zeros(len(tickers))
            for position, asset_index in enumerate(active):
                full_weights[asset_index] = sub_weights[position]
            return _to_weight_dict(tickers, full_weights)
        active.pop(worst_index)


def risk_parity_weights(
    returns: ReturnMatrix, shrinkage: float = 0.0
) -> dict[str, float]:
    """Equal risk contribution weights via the Maillard iterative algorithm.

    Each asset's marginal risk contribution `w_i * (sigma @ w)_i` is driven to
    the mean of the contributions. Initialized from inverse-volatility weights.
    """
    tickers, sigma = covariance_matrix(returns, shrinkage=shrinkage)
    asset_variances = np.diag(sigma)
    if np.any(asset_variances <= 0):
        raise ValueError("every asset must have positive variance")
    weights = 1.0 / np.sqrt(asset_variances)
    weights /= weights.sum()
    for _ in range(MAX_ITERATIONS):
        sigma_times_weights = sigma @ weights
        risk_contributions = weights * sigma_times_weights
        target = risk_contributions.mean()
        if target <= 0:
            raise ValueError("portfolio variance collapsed to zero")
        scale = np.sqrt(target / risk_contributions)
        next_weights = weights * scale
        next_weights /= next_weights.sum()
        if np.max(np.abs(next_weights - weights)) < CONVERGENCE_TOLERANCE:
            return _to_weight_dict(tickers, next_weights)
        weights = next_weights
    return _to_weight_dict(tickers, weights)


def _to_weight_dict(tickers: tuple[str, ...], weights: np.ndarray) -> dict[str, float]:
    return {ticker: float(weight) for ticker, weight in zip(tickers, weights, strict=True)}
