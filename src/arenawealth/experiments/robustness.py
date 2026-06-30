"""Robustness of the equal-weight-beats-fundamentals result.

The full-sample backtest found that equal weighting beats the market-value
("current") weighting on risk-adjusted return. A single sample cannot tell us
whether that is structural or luck. Two pure checks over the aligned daily-return
matrix address it:

1. Rolling windows: split the history into overlapping windows and record how
   often equal weighting wins on the Sharpe ratio.
2. Block bootstrap: resample contiguous blocks of days (to preserve serial
   structure) and build a confidence interval for the full-period Sharpe
   difference. A fixed seed makes the interval reproducible.

Portfolios here are fixed-weight (rebalanced each period to target), the standard
convention for a clean Sharpe comparison; this differs from the buy-and-hold
drift of the headline backtest and is stated as such.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from arenawealth.analytics.performance import sharpe_ratio

TRADING_DAYS_PER_YEAR = 252.0


def fixed_weight_returns(
    asset_returns: Mapping[str, Sequence[float]], weights: Mapping[str, float]
) -> tuple[float, ...]:
    """Daily return series of a fixed-weight portfolio (weights renormalized)."""
    active = {ticker: weight for ticker, weight in weights.items() if weight != 0}
    total = sum(active.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    tickers = sorted(active)
    matrix = np.array([asset_returns[ticker] for ticker in tickers], dtype=np.float64)
    weight_vector = np.array([active[ticker] / total for ticker in tickers])
    return tuple(weight_vector @ matrix)


def equal_weights(tickers: Sequence[str]) -> dict[str, float]:
    weight = 1.0 / len(tickers)
    return {ticker: weight for ticker in tickers}


@dataclass(frozen=True)
class RollingComparison:
    window: int
    step: int
    windows: int
    wins_a: int
    win_rate_a: float
    mean_sharpe_a: float
    mean_sharpe_b: float


def rolling_comparison(
    asset_returns: Mapping[str, Sequence[float]],
    weights_a: Mapping[str, float],
    weights_b: Mapping[str, float],
    window: int = 252,
    step: int = 21,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> RollingComparison:
    """How often portfolio A beats B on Sharpe across rolling windows."""
    returns_a = fixed_weight_returns(asset_returns, weights_a)
    returns_b = fixed_weight_returns(asset_returns, weights_b)
    length = len(returns_a)
    if window > length:
        raise ValueError("window must not exceed the series length")
    sharpes_a: list[float] = []
    sharpes_b: list[float] = []
    wins = 0
    for start in range(0, length - window + 1, step):
        slice_a = returns_a[start : start + window]
        slice_b = returns_b[start : start + window]
        sharpe_a = sharpe_ratio(slice_a, periods_per_year)
        sharpe_b = sharpe_ratio(slice_b, periods_per_year)
        sharpes_a.append(sharpe_a)
        sharpes_b.append(sharpe_b)
        if sharpe_a > sharpe_b:
            wins += 1
    windows = len(sharpes_a)
    return RollingComparison(
        window=window,
        step=step,
        windows=windows,
        wins_a=wins,
        win_rate_a=wins / windows if windows else 0.0,
        mean_sharpe_a=float(np.mean(sharpes_a)) if sharpes_a else 0.0,
        mean_sharpe_b=float(np.mean(sharpes_b)) if sharpes_b else 0.0,
    )


@dataclass(frozen=True)
class BootstrapResult:
    samples: int
    block: int
    point_estimate: float
    ci_low: float
    ci_high: float
    prob_a_better: float


def block_bootstrap_sharpe_diff(
    asset_returns: Mapping[str, Sequence[float]],
    weights_a: Mapping[str, float],
    weights_b: Mapping[str, float],
    block: int = 21,
    samples: int = 2000,
    confidence: float = 0.95,
    seed: int = 12345,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> BootstrapResult:
    """Confidence interval for Sharpe(A) - Sharpe(B) via circular block bootstrap."""
    returns_a = np.array(fixed_weight_returns(asset_returns, weights_a))
    returns_b = np.array(fixed_weight_returns(asset_returns, weights_b))
    length = len(returns_a)
    if block > length:
        raise ValueError("block must not exceed the series length")
    generator = np.random.default_rng(seed)
    block_count = int(np.ceil(length / block))
    differences = np.empty(samples)
    for index in range(samples):
        starts = generator.integers(0, length, size=block_count)
        offsets = (starts[:, None] + np.arange(block)) % length
        picks = offsets.reshape(-1)[:length]
        diff = sharpe_ratio(tuple(returns_a[picks]), periods_per_year) - sharpe_ratio(
            tuple(returns_b[picks]), periods_per_year
        )
        differences[index] = diff
    tail = (1.0 - confidence) / 2.0
    point = sharpe_ratio(tuple(returns_a), periods_per_year) - sharpe_ratio(
        tuple(returns_b), periods_per_year
    )
    return BootstrapResult(
        samples=samples,
        block=block,
        point_estimate=float(point),
        ci_low=float(np.quantile(differences, tail)),
        ci_high=float(np.quantile(differences, 1.0 - tail)),
        prob_a_better=float(np.mean(differences > 0)),
    )
