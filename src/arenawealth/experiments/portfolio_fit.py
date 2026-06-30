"""Controlled portfolio-fit experiment."""

from __future__ import annotations

from dataclasses import dataclass

from arenawealth.analytics.models import FundamentalScore, Holding, PositionAnalysis
from arenawealth.analytics.portfolio_review import review_candidate_addition
from arenawealth.analytics.screening import CandidateAnalysis


@dataclass(frozen=True)
class CandidateFitRow:
    ticker: str
    theme: str
    composite_score: float
    portfolio_fit_score: float
    current_theme_weight_pct: float
    projected_theme_weight_pct: float
    structural_role: str


@dataclass(frozen=True)
class PortfolioFitExperiment:
    isolated_top: str
    portfolio_fit_top: str
    ranking_changed: bool
    rows: tuple[CandidateFitRow, ...]


def controlled_portfolio_fit_experiment() -> PortfolioFitExperiment:
    """Show when isolated quality rank disagrees with portfolio fit."""
    held = (
        _position_analysis("AAA", 72.0, 12.0, "Platforms"),
        _position_analysis("BBB", 70.0, 11.0, "Platforms"),
        _position_analysis("CCC", 68.0, 5.0, "Healthcare"),
    )
    candidates = (
        _candidate_analysis("PLAT", 90.0, "Platforms"),
        _candidate_analysis("INDU", 84.0, "Industrial"),
        _candidate_analysis("HLTH", 82.0, "Healthcare"),
    )
    theme_weights: dict[str, float] = {}
    for analysis in held:
        theme = analysis.holding.theme
        theme_weights[theme] = theme_weights.get(theme, 0.0) + analysis.weight_pct

    starter_weight_pct = 10.0
    reviewed = tuple(
        review_candidate_addition(
            candidate,
            theme_weights,
            starter_weight_pct,
            portfolio_below_range=False,
        )
        for candidate in candidates
    )
    rows = tuple(
        CandidateFitRow(
            ticker=review.ticker,
            theme=review.theme,
            composite_score=review.composite_score,
            portfolio_fit_score=review.portfolio_fit_score,
            current_theme_weight_pct=review.current_theme_weight_pct,
            projected_theme_weight_pct=review.projected_theme_weight_pct,
            structural_role=review.structural_role,
        )
        for review in reviewed
    )
    isolated_top = max(rows, key=lambda row: row.composite_score).ticker
    portfolio_fit_top = max(
        rows,
        key=lambda row: (row.portfolio_fit_score, row.composite_score),
    ).ticker
    return PortfolioFitExperiment(
        isolated_top=isolated_top,
        portfolio_fit_top=portfolio_fit_top,
        ranking_changed=isolated_top != portfolio_fit_top,
        rows=rows,
    )


def _score(composite_score: float) -> FundamentalScore:
    return FundamentalScore(
        roic=0.18,
        roe=0.22,
        margin_cv=0.08,
        revenue_cagr=0.10,
        eps_cagr=0.12,
        fcf_cagr=0.11,
        shares_change=-0.03,
        fcf_yield=0.04,
        forward_pe=24.0,
        peg=1.5,
        moat_class="STRONG",
        compounding_class="GOOD",
        moat_points=composite_score,
        compounding_points=composite_score,
        valuation_points=60.0,
        composite_score=composite_score,
    )


def _position_analysis(
    ticker: str,
    composite_score: float,
    weight_pct: float,
    theme: str,
) -> PositionAnalysis:
    holding = Holding(ticker, ticker, 1.0, 100.0, 100.0, theme, False)
    return PositionAnalysis(
        holding=holding,
        live_price=100.0,
        market_value=100.0,
        weight_pct=weight_pct,
        pnl_pct=0.0,
        price_gap_pct=0.0,
        roic=0.18,
        roe=0.22,
        margin_cv=0.08,
        revenue_cagr=0.10,
        eps_cagr=0.12,
        fcf_cagr=0.11,
        shares_change=-0.03,
        fcf_yield=0.04,
        forward_pe=24.0,
        peg=1.5,
        moat_class="STRONG",
        compounding_class="GOOD",
        moat_points=composite_score,
        compounding_points=composite_score,
        valuation_points=60.0,
        composite_score=composite_score,
    )


def _candidate_analysis(
    ticker: str,
    composite_score: float,
    theme: str,
) -> CandidateAnalysis:
    return CandidateAnalysis(
        ticker=ticker,
        name=f"{ticker} Inc",
        theme=theme,
        live_price=100.0,
        score=_score(composite_score),
    )
