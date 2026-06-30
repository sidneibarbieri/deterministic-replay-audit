"""Screen a candidate universe for moat and compounding quality.

Reuses the pure scoring from arenawealth.analytics.scoring, so candidates that
are not held are evaluated by the exact same moat/compounding/valuation logic as
the portfolio holdings.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from arenawealth.analytics.fundamentals import FundamentalsProvider
from arenawealth.analytics.models import FundamentalScore
from arenawealth.analytics.scoring import score_fundamentals
from arenawealth.analytics.universe import CANDIDATE_UNIVERSE, FINANCIAL_TICKERS


@dataclass(frozen=True)
class CandidateAnalysis:
    ticker: str
    name: str
    theme: str
    live_price: float
    score: FundamentalScore


def screen_candidates(
    provider: FundamentalsProvider,
    tickers: Sequence[str] | None = None,
    owned: Iterable[str] = (),
    max_workers: int = 8,
) -> list[CandidateAnalysis]:
    """Score a candidate universe and return it ranked by composite score.

    Tickers already owned are skipped so the result only surfaces new ideas.
    """
    owned_tickers = {ticker.upper() for ticker in owned}
    universe = [
        ticker
        for ticker in (tickers if tickers is not None else CANDIDATE_UNIVERSE)
        if ticker.upper() not in owned_tickers
    ]
    if not universe:
        return []

    def evaluate(ticker: str) -> CandidateAnalysis:
        fundamentals = provider.get_fundamentals(ticker)
        score = score_fundamentals(
            fundamentals, ticker in FINANCIAL_TICKERS, provider.exchange_rate
        )
        name, theme = CANDIDATE_UNIVERSE.get(ticker, (ticker, "Other"))
        return CandidateAnalysis(
            ticker=ticker,
            name=name,
            theme=theme,
            live_price=fundamentals.live_price,
            score=score,
        )

    with ThreadPoolExecutor(max_workers=min(max_workers, len(universe))) as executor:
        candidates = list(executor.map(evaluate, universe))
    return sorted(candidates, key=lambda candidate: candidate.score.composite_score, reverse=True)
