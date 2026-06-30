"""Deterministic portfolio backtest engine.

Pure functions over per-asset return series. Given target weights and a
rebalancing policy, it produces an equity curve and risk/return metrics from
arenawealth.analytics.performance. No I/O, so a run is reproducible and
unit-testable without market data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arenawealth.analytics.performance import (
    annualized_volatility,
    cagr,
    max_drawdown,
    sharpe_ratio,
    to_returns,
    turnover,
)


@dataclass(frozen=True)
class BacktestResult:
    periods: int
    rebalances: int
    total_return: float
    cagr: float | None
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    total_cost: float
    equity_curve: tuple[float, ...]


@dataclass(frozen=True)
class BacktestComparison:
    strategy: BacktestResult
    benchmark: BacktestResult
    excess_total_return: float
    excess_cagr: float | None
    sharpe_delta: float
    max_drawdown_delta: float


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if any(weight < 0 for weight in weights.values()):
        raise ValueError("target weights must be non-negative")
    active_weights = {ticker: weight for ticker, weight in weights.items() if weight > 0}
    total = sum(active_weights.values())
    if total <= 0:
        raise ValueError("target weights must sum to a positive number")
    return {ticker: weight / total for ticker, weight in active_weights.items()}


def validate_return_series(
    asset_returns: Mapping[str, Sequence[float]], weights: Mapping[str, float]
) -> int:
    lengths = set()
    for ticker in weights:
        if ticker not in asset_returns:
            raise ValueError(f"missing return series for {ticker}")
        lengths.add(len(asset_returns[ticker]))
    if not lengths or 0 in lengths:
        raise ValueError("return series must not be empty")
    if len(lengths) != 1:
        raise ValueError("return series must be date-aligned with equal length")
    return lengths.pop()


def run_backtest(
    asset_returns: Mapping[str, Sequence[float]],
    target_weights: Mapping[str, float],
    periods_per_year: float,
    rebalance_every: int = 0,
    cost_rate: float = 0.0,
) -> BacktestResult:
    """Simulate a portfolio over time.

    rebalance_every=0 lets weights drift (buy and hold); a positive value resets
    to target weights on that cadence and charges cost_rate on the traded value.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    if rebalance_every < 0:
        raise ValueError("rebalance_every must be non-negative")
    if cost_rate < 0:
        raise ValueError("cost_rate must be non-negative")
    weights = normalize_weights(target_weights)
    periods = validate_return_series(asset_returns, weights)

    holdings = dict(weights)
    equity_curve: list[float] = []
    total_cost = 0.0
    rebalances = 0

    for period in range(periods):
        for ticker in weights:
            holdings[ticker] *= 1 + asset_returns[ticker][period]
        equity = sum(holdings.values())

        is_last_period = period == periods - 1
        if rebalance_every and (period + 1) % rebalance_every == 0 and not is_last_period:
            current = {ticker: value / equity for ticker, value in holdings.items()}
            traded = turnover(current, weights)
            cost = cost_rate * traded * equity
            equity -= cost
            total_cost += cost
            holdings = {ticker: weights[ticker] * equity for ticker in weights}
            rebalances += 1

        equity_curve.append(equity)

    returns = to_returns([1.0, *equity_curve])
    return BacktestResult(
        periods=periods,
        rebalances=rebalances,
        total_return=equity_curve[-1] - 1 if equity_curve else 0.0,
        cagr=cagr(returns, periods_per_year),
        annualized_volatility=annualized_volatility(returns, periods_per_year),
        sharpe_ratio=sharpe_ratio(returns, periods_per_year),
        max_drawdown=max_drawdown(returns),
        total_cost=total_cost,
        equity_curve=tuple(equity_curve),
    )


def compare_backtests(strategy: BacktestResult, benchmark: BacktestResult) -> BacktestComparison:
    if strategy.periods != benchmark.periods:
        raise ValueError("strategy and benchmark must cover the same number of periods")
    if strategy.cagr is None or benchmark.cagr is None:
        excess_cagr = None
    else:
        excess_cagr = strategy.cagr - benchmark.cagr
    return BacktestComparison(
        strategy=strategy,
        benchmark=benchmark,
        excess_total_return=strategy.total_return - benchmark.total_return,
        excess_cagr=excess_cagr,
        sharpe_delta=strategy.sharpe_ratio - benchmark.sharpe_ratio,
        max_drawdown_delta=strategy.max_drawdown - benchmark.max_drawdown,
    )
