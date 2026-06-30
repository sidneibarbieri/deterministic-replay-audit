"""Portfolio analysis workflow."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from arenawealth.analytics.fundamentals import FundamentalsProvider
from arenawealth.analytics.models import Fundamentals, Holding, PositionAnalysis
from arenawealth.analytics.scoring import analyze


def fetch_fundamentals(
    holdings: tuple[Holding, ...],
    provider: FundamentalsProvider,
    max_workers: int = 8,
) -> dict[str, Fundamentals]:
    def fetch_one(holding: Holding) -> tuple[str, Fundamentals]:
        return holding.ticker, provider.get_fundamentals(holding.ticker)

    workers = min(max_workers, max(1, len(holdings)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pairs = executor.map(fetch_one, holdings)
    return dict(pairs)


def analyze_holdings(
    holdings: tuple[Holding, ...],
    provider: FundamentalsProvider,
) -> list[PositionAnalysis]:
    fundamentals = fetch_fundamentals(holdings, provider)
    total_market_value = sum(
        holding.shares * fundamentals[holding.ticker].live_price for holding in holdings
    )
    return [
        analyze(holding, fundamentals[holding.ticker], total_market_value, provider.exchange_rate)
        for holding in holdings
    ]
