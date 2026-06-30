"""Price-history backtest helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from arenawealth.analytics.allocators import (
    min_variance_weights,
    risk_parity_weights,
)
from arenawealth.analytics.backtest import (
    BacktestComparison,
    BacktestResult,
    compare_backtests,
    run_backtest,
)
from arenawealth.analytics.performance import (
    annualized_volatility,
    cagr,
    max_drawdown,
    sharpe_ratio,
    to_returns,
    turnover,
)

Allocator = Callable[[Mapping[str, Sequence[float]], float], dict[str, float]]


@dataclass(frozen=True)
class AlignedReturnSeries:
    dates: tuple[str, ...]
    returns: dict[str, tuple[float, ...]]


@dataclass(frozen=True)
class PriceBacktestReport:
    start_date: str
    end_date: str
    tickers: tuple[str, ...]
    benchmark_ticker: str
    strategy: BacktestResult
    benchmark: BacktestResult
    comparison: BacktestComparison


@dataclass(frozen=True)
class PriceBacktestStudy:
    start_date: str
    end_date: str
    tickers: tuple[str, ...]
    benchmark_ticker: str
    current_weight: BacktestResult
    equal_weight: BacktestResult
    benchmark: BacktestResult
    current_vs_equal_weight: BacktestComparison
    current_vs_benchmark: BacktestComparison
    rebalanced_current: BacktestResult | None = None
    current_vs_rebalanced: BacktestComparison | None = None
    min_variance: BacktestResult | None = None
    risk_parity: BacktestResult | None = None
    current_vs_min_variance: BacktestComparison | None = None
    current_vs_risk_parity: BacktestComparison | None = None
    sota_weights: dict[str, dict[str, float]] | None = None
    sota_method: dict[str, float | int | str] | None = None


@dataclass(frozen=True)
class WalkForwardAllocatorConfig:
    lookback: int = 252
    min_observations: int = 63
    rebalance_every: int = 63
    shrinkage: float = 0.20


def align_price_history(price_history: Mapping[str, Mapping[str, float]]) -> AlignedReturnSeries:
    if not price_history:
        raise ValueError("price_history must not be empty")

    common_dates: set[str] | None = None
    for ticker, series in price_history.items():
        if len(series) < 2:
            raise ValueError(f"price history for {ticker} must contain at least two dates")
        ticker_dates = {date for date, price in series.items() if price > 0}
        common_dates = ticker_dates if common_dates is None else common_dates & ticker_dates

    dates = tuple(sorted(common_dates or ()))
    if len(dates) < 2:
        raise ValueError("price histories must share at least two valid dates")

    returns = {
        ticker: to_returns([series[date] for date in dates])
        for ticker, series in price_history.items()
    }
    return AlignedReturnSeries(dates=dates[1:], returns=returns)


def run_price_backtest(
    price_history: Mapping[str, Mapping[str, float]],
    target_weights: Mapping[str, float],
    benchmark_ticker: str,
    periods_per_year: float = 252.0,
    rebalance_every: int = 0,
    cost_rate: float = 0.0,
) -> PriceBacktestReport:
    aligned = align_price_history(price_history)
    tickers = tuple(target_weights)
    strategy = run_backtest(
        aligned.returns,
        target_weights,
        periods_per_year=periods_per_year,
        rebalance_every=rebalance_every,
        cost_rate=cost_rate,
    )
    benchmark = run_backtest(
        aligned.returns,
        {benchmark_ticker: 1.0},
        periods_per_year=periods_per_year,
        rebalance_every=0,
        cost_rate=0.0,
    )
    return PriceBacktestReport(
        start_date=aligned.dates[0],
        end_date=aligned.dates[-1],
        tickers=tickers,
        benchmark_ticker=benchmark_ticker,
        strategy=strategy,
        benchmark=benchmark,
        comparison=compare_backtests(strategy, benchmark),
    )


def equal_weights(tickers: tuple[str, ...]) -> dict[str, float]:
    if not tickers:
        raise ValueError("tickers must not be empty")
    weight = 1.0 / len(tickers)
    return {ticker: weight for ticker in tickers}


def _return_slice(
    asset_returns: Mapping[str, Sequence[float]],
    tickers: Sequence[str],
    start: int,
    end: int,
) -> dict[str, tuple[float, ...]]:
    return {ticker: tuple(asset_returns[ticker][start:end]) for ticker in tickers}


def walk_forward_weight_schedule(
    asset_returns: Mapping[str, Sequence[float]],
    tickers: Sequence[str],
    allocator: Allocator,
    config: WalkForwardAllocatorConfig,
) -> dict[int, dict[str, float]]:
    """Rebalance weights from past returns only."""
    if config.lookback < 2:
        raise ValueError("lookback must be at least 2")
    if config.min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if config.rebalance_every <= 0:
        raise ValueError("rebalance_every must be positive")
    periods = {len(asset_returns[ticker]) for ticker in tickers}
    if len(periods) != 1:
        raise ValueError("asset returns must be date-aligned")
    length = periods.pop()
    if length <= 0:
        raise ValueError("asset returns must not be empty")

    schedule: dict[int, dict[str, float]] = {}
    uniform = equal_weights(tuple(tickers))
    for period in range(0, length, config.rebalance_every):
        if period < config.min_observations:
            schedule[period] = uniform
            continue
        window_start = max(0, period - config.lookback)
        training = _return_slice(asset_returns, tickers, window_start, period)
        schedule[period] = allocator(training, config.shrinkage)
    return schedule


def run_walk_forward_backtest(
    asset_returns: Mapping[str, Sequence[float]],
    tickers: Sequence[str],
    allocator: Allocator,
    periods_per_year: float,
    config: WalkForwardAllocatorConfig,
    cost_rate: float = 0.0,
) -> BacktestResult:
    """Backtest a rolling allocator without using future returns."""
    if cost_rate < 0:
        raise ValueError("cost_rate must be non-negative")
    schedule = walk_forward_weight_schedule(asset_returns, tickers, allocator, config)
    periods = len(next(iter(asset_returns.values())))
    target_weights = schedule[0]
    holdings = dict(target_weights)
    equity_curve: list[float] = []
    total_cost = 0.0
    rebalances = 0

    for period in range(periods):
        if period in schedule and period != 0:
            equity = sum(holdings.values())
            current_weights = {ticker: value / equity for ticker, value in holdings.items()}
            target_weights = schedule[period]
            traded = turnover(current_weights, target_weights)
            cost = cost_rate * traded * equity
            equity -= cost
            total_cost += cost
            holdings = {ticker: target_weights[ticker] * equity for ticker in target_weights}
            rebalances += 1

        for ticker in target_weights:
            holdings[ticker] *= 1 + asset_returns[ticker][period]
        equity_curve.append(sum(holdings.values()))

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


def run_price_backtest_study(
    price_history: Mapping[str, Mapping[str, float]],
    target_weights: Mapping[str, float],
    benchmark_ticker: str,
    periods_per_year: float = 252.0,
    rebalance_every: int = 0,
    cost_rate: float = 0.0,
    include_sota_baselines: bool = True,
    walk_forward_config: WalkForwardAllocatorConfig | None = None,
) -> PriceBacktestStudy:
    aligned = align_price_history(price_history)
    return run_price_backtest_study_from_aligned_returns(
        aligned,
        target_weights,
        benchmark_ticker=benchmark_ticker,
        periods_per_year=periods_per_year,
        rebalance_every=rebalance_every,
        cost_rate=cost_rate,
        include_sota_baselines=include_sota_baselines,
        walk_forward_config=walk_forward_config,
    )


def run_price_backtest_study_from_aligned_returns(
    aligned: AlignedReturnSeries,
    target_weights: Mapping[str, float],
    benchmark_ticker: str,
    periods_per_year: float = 252.0,
    rebalance_every: int = 0,
    cost_rate: float = 0.0,
    include_sota_baselines: bool = True,
    walk_forward_config: WalkForwardAllocatorConfig | None = None,
) -> PriceBacktestStudy:
    walk_forward_config = walk_forward_config or WalkForwardAllocatorConfig()
    tickers = tuple(target_weights)
    asset_returns = {ticker: aligned.returns[ticker] for ticker in tickers}
    current_weight = run_backtest(
        aligned.returns,
        target_weights,
        periods_per_year=periods_per_year,
        rebalance_every=0,
        cost_rate=0.0,
    )
    equal_weight = run_backtest(
        aligned.returns,
        equal_weights(tickers),
        periods_per_year=periods_per_year,
        rebalance_every=0,
        cost_rate=0.0,
    )
    benchmark = run_backtest(
        aligned.returns,
        {benchmark_ticker: 1.0},
        periods_per_year=periods_per_year,
        rebalance_every=0,
        cost_rate=0.0,
    )
    rebalanced_current = None
    current_vs_rebalanced = None
    if rebalance_every:
        rebalanced_current = run_backtest(
            aligned.returns,
            target_weights,
            periods_per_year=periods_per_year,
            rebalance_every=rebalance_every,
            cost_rate=cost_rate,
        )
        current_vs_rebalanced = compare_backtests(current_weight, rebalanced_current)

    min_variance = None
    risk_parity = None
    current_vs_min_variance = None
    current_vs_risk_parity = None
    sota_weights: dict[str, dict[str, float]] | None = None
    sota_method: dict[str, float | int | str] | None = None
    if include_sota_baselines:
        min_variance = run_walk_forward_backtest(
            asset_returns,
            tickers,
            min_variance_weights,
            periods_per_year=periods_per_year,
            config=walk_forward_config,
            cost_rate=cost_rate,
        )
        risk_parity = run_walk_forward_backtest(
            asset_returns,
            tickers,
            risk_parity_weights,
            periods_per_year=periods_per_year,
            config=walk_forward_config,
            cost_rate=cost_rate,
        )
        current_vs_min_variance = compare_backtests(current_weight, min_variance)
        current_vs_risk_parity = compare_backtests(current_weight, risk_parity)
        min_variance_schedule = walk_forward_weight_schedule(
            asset_returns, tickers, min_variance_weights, walk_forward_config
        )
        risk_parity_schedule = walk_forward_weight_schedule(
            asset_returns, tickers, risk_parity_weights, walk_forward_config
        )
        sota_weights = {
            "min_variance_last": min_variance_schedule[max(min_variance_schedule)],
            "risk_parity_last": risk_parity_schedule[max(risk_parity_schedule)],
        }
        sota_method = {
            "method": "walk_forward_rolling_covariance",
            "lookback": walk_forward_config.lookback,
            "min_observations": walk_forward_config.min_observations,
            "rebalance_every": walk_forward_config.rebalance_every,
            "shrinkage": walk_forward_config.shrinkage,
            "cost_rate": cost_rate,
        }

    return PriceBacktestStudy(
        start_date=aligned.dates[0],
        end_date=aligned.dates[-1],
        tickers=tickers,
        benchmark_ticker=benchmark_ticker,
        current_weight=current_weight,
        equal_weight=equal_weight,
        benchmark=benchmark,
        current_vs_equal_weight=compare_backtests(current_weight, equal_weight),
        current_vs_benchmark=compare_backtests(current_weight, benchmark),
        rebalanced_current=rebalanced_current,
        current_vs_rebalanced=current_vs_rebalanced,
        min_variance=min_variance,
        risk_parity=risk_parity,
        current_vs_min_variance=current_vs_min_variance,
        current_vs_risk_parity=current_vs_risk_parity,
        sota_weights=sota_weights,
        sota_method=sota_method,
    )
