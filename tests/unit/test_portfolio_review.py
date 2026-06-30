"""Unit tests for deterministic portfolio upgrade review."""

from arenawealth.analytics.models import FundamentalScore, Holding, PositionAnalysis
from arenawealth.analytics.portfolio_review import review_portfolio
from arenawealth.analytics.screening import CandidateAnalysis


def score(composite_score: float, valuation_points: float = 60.0) -> FundamentalScore:
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
        valuation_points=valuation_points,
        composite_score=composite_score,
    )


def position_analysis(
    ticker: str,
    composite_score: float,
    valuation_points: float = 60.0,
    weight_pct: float = 5.0,
    theme: str = "Theme",
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
        valuation_points=valuation_points,
        composite_score=composite_score,
    )


def candidate_analysis(
    ticker: str,
    composite_score: float,
    valuation_points: float = 60.0,
    theme: str = "Candidate Theme",
) -> CandidateAnalysis:
    return CandidateAnalysis(
        ticker=ticker,
        name=f"{ticker} Inc",
        theme=theme,
        live_price=100.0,
        score=score(composite_score, valuation_points),
    )


def test_review_surfaces_additions_when_portfolio_is_below_target_range():
    held = [position_analysis("AAA", 65.0), position_analysis("BBB", 62.0)]
    candidates = [candidate_analysis("CCC", 80.0), candidate_analysis("DDD", 78.0)]

    review = review_portfolio(held, candidates, target_min_positions=3, target_max_positions=5)

    assert review.additions_needed == 1
    assert [candidate.ticker for candidate in review.add_candidates] == ["CCC", "DDD"]
    assert review.add_candidates[0].structural_role == "Diversifier"
    assert review.add_candidates[0].reason.startswith("Portfolio is below the target range.")


def test_review_flags_replacement_only_when_score_gap_and_valuation_clear():
    held = [position_analysis("WEAK", 50.0, 55.0), position_analysis("KEEP", 74.0, 58.0)]
    candidates = [
        candidate_analysis("UPGD", 63.0, 52.0),
        candidate_analysis("RICH", 80.0, 40.0),
    ]

    review = review_portfolio(held, candidates, target_min_positions=2, target_max_positions=5)

    assert len(review.replacement_watch) == 1
    replacement = review.replacement_watch[0]
    assert replacement.current_ticker == "WEAK"
    assert replacement.candidate_ticker == "UPGD"
    assert replacement.score_gap == 13.0


def test_review_flags_overweight_lower_quality_positions_for_trim_watch():
    held = [
        position_analysis("HEAVY", 62.0, weight_pct=40.0),
        position_analysis("OKAY", 74.0, weight_pct=25.0),
        position_analysis("SMOL", 72.0, weight_pct=20.0),
        position_analysis("ALSO", 73.0, weight_pct=15.0),
    ]

    review = review_portfolio(held, [], target_min_positions=4, target_max_positions=6)

    assert [position.ticker for position in review.trim_watch] == ["HEAVY"]


def test_review_scores_candidate_fit_against_theme_concentration():
    held = [
        position_analysis("AAA", 72.0, weight_pct=12.0, theme="Platforms"),
        position_analysis("BBB", 70.0, weight_pct=11.0, theme="Platforms"),
        position_analysis("CCC", 68.0, weight_pct=5.0, theme="Healthcare"),
    ]
    candidates = [
        candidate_analysis("NEW", 82.0, theme="Industrial"),
        candidate_analysis("MORE", 81.0, theme="Platforms"),
    ]

    review = review_portfolio(held, candidates, target_min_positions=3, target_max_positions=8)

    diversifier = review.add_candidates[0]
    concentrated = review.add_candidates[1]
    assert diversifier.structural_role == "Diversifier"
    assert diversifier.portfolio_fit_score > concentrated.portfolio_fit_score
    assert concentrated.structural_role == "Concentration watch"
    assert concentrated.projected_theme_weight_pct > 20.0
