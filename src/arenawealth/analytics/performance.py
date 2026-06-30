"""Performance and risk metrics for backtests.

Pure functions over return series. No I/O, so every metric is unit-testable
against hand-computed values. These are the measurement core a backtest needs
to compare a strategy against baselines net of costs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def to_returns(prices: Sequence[float]) -> tuple[float, ...]:
    """Convert a price series into simple period returns."""
    returns = []
    for index in range(1, len(prices)):
        previous = prices[index - 1]
        if previous:
            returns.append(prices[index] / previous - 1)
    return tuple(returns)


def cumulative_return(returns: Sequence[float]) -> float:
    growth = 1.0
    for period_return in returns:
        growth *= 1 + period_return
    return growth - 1


def cagr(returns: Sequence[float], periods_per_year: float) -> float | None:
    if not returns or periods_per_year <= 0:
        return None
    growth = cumulative_return(returns) + 1
    if growth <= 0:
        return None
    years = len(returns) / periods_per_year
    return growth ** (1 / years) - 1


def annualized_volatility(returns: Sequence[float], periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def sharpe_ratio(
    returns: Sequence[float], periods_per_year: float, risk_free_rate: float = 0.0
) -> float:
    if len(returns) < 2:
        return 0.0
    per_period_risk_free = risk_free_rate / periods_per_year
    excess = [value - per_period_risk_free for value in returns]
    mean = sum(excess) / len(excess)
    variance = sum((value - mean) ** 2 for value in excess) / len(excess)
    deviation = math.sqrt(variance)
    if deviation < 1e-12:  # a flat return series carries no risk-adjusted signal
        return 0.0
    return mean / deviation * math.sqrt(periods_per_year)


def max_drawdown(returns: Sequence[float]) -> float:
    """Largest peak-to-trough decline of the equity curve (<= 0)."""
    peak = 1.0
    equity = 1.0
    worst = 0.0
    for period_return in returns:
        equity *= 1 + period_return
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    return worst


def turnover(previous_weights: dict[str, float], current_weights: dict[str, float]) -> float:
    """One-way turnover between two weight vectors (0 = no change)."""
    tickers = set(previous_weights) | set(current_weights)
    traded = sum(
        abs(current_weights.get(ticker, 0.0) - previous_weights.get(ticker, 0.0))
        for ticker in tickers
    )
    return traded / 2
