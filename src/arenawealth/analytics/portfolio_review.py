"""Deterministic portfolio upgrade review."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arenawealth.analytics.models import PositionAnalysis
from arenawealth.analytics.screening import CandidateAnalysis

TARGET_MIN_POSITIONS = 18
TARGET_MAX_POSITIONS = 25
THEME_CAP_PCT = 20.0
UPGRADE_SCORE_GAP = 8.0
VALUATION_TOLERANCE = 5.0
TRIM_SCORE_LIMIT = 70.0


@dataclass(frozen=True)
class AdditionReview:
    ticker: str
    name: str
    theme: str
    composite_score: float
    portfolio_fit_score: float
    current_theme_weight_pct: float
    projected_theme_weight_pct: float
    structural_role: str
    reason: str


@dataclass(frozen=True)
class ReplacementReview:
    current_ticker: str
    candidate_ticker: str
    candidate_name: str
    score_gap: float
    reason: str


@dataclass(frozen=True)
class TrimReview:
    ticker: str
    weight_pct: float
    composite_score: float
    reason: str


@dataclass(frozen=True)
class PortfolioReview:
    current_positions: int
    target_min_positions: int
    target_max_positions: int
    additions_needed: int
    add_candidates: tuple[AdditionReview, ...]
    replacement_watch: tuple[ReplacementReview, ...]
    trim_watch: tuple[TrimReview, ...]


def review_additions(
    held: Sequence[PositionAnalysis],
    candidates: Sequence[CandidateAnalysis],
    target_min_positions: int,
    target_max_positions: int,
) -> tuple[int, tuple[AdditionReview, ...]]:
    current_positions = len(held)
    additions_needed = max(0, target_min_positions - current_positions)
    if current_positions > target_max_positions:
        return additions_needed, ()
    limit = max(3, additions_needed)
    theme_weights = current_theme_weights(held)
    starter_weight = starter_position_weight_pct(current_positions, target_min_positions)
    additions = tuple(
        review_candidate_addition(
            candidate,
            theme_weights,
            starter_weight,
            additions_needed > 0,
        )
        for candidate in candidates[:limit]
    )
    return additions_needed, additions


def current_theme_weights(held: Sequence[PositionAnalysis]) -> dict[str, float]:
    theme_weights: dict[str, float] = {}
    for analysis in held:
        theme = analysis.holding.theme
        theme_weights[theme] = theme_weights.get(theme, 0.0) + analysis.weight_pct
    return theme_weights


def starter_position_weight_pct(
    current_positions: int,
    target_min_positions: int,
) -> float:
    if current_positions <= 0:
        return 100.0
    target_slot = 100 / max(target_min_positions, current_positions + 1)
    return min(10.0, target_slot)


def projected_theme_weight_pct(
    current_theme_weight_pct: float,
    starter_weight_pct: float,
) -> float:
    remaining_current_weight = 100.0 - starter_weight_pct
    return current_theme_weight_pct * remaining_current_weight / 100.0 + starter_weight_pct


def portfolio_fit_score(projected_theme_weight: float, is_new_theme: bool) -> float:
    concentration_penalty = max(0.0, projected_theme_weight - THEME_CAP_PCT) * 3.0
    diversification_bonus = 12.0 if is_new_theme else 0.0
    return max(0.0, min(100.0, 80.0 + diversification_bonus - concentration_penalty))


def review_candidate_addition(
    candidate: CandidateAnalysis,
    theme_weights: dict[str, float],
    starter_weight_pct: float,
    portfolio_below_range: bool,
) -> AdditionReview:
    current_theme_weight = theme_weights.get(candidate.theme, 0.0)
    is_new_theme = current_theme_weight == 0.0
    projected_weight = projected_theme_weight_pct(
        current_theme_weight,
        starter_weight_pct,
    )
    if is_new_theme:
        role = "Diversifier"
        reason = "Adds a new theme while staying inside the concentration cap."
    elif projected_weight <= THEME_CAP_PCT:
        role = "Theme reinforcement"
        reason = "Improves the candidate set without breaching the theme cap."
    else:
        role = "Concentration watch"
        reason = "Candidate quality is high, but the theme would exceed the cap."
    if portfolio_below_range:
        reason = f"Portfolio is below the target range. {reason}"
    return AdditionReview(
        ticker=candidate.ticker,
        name=candidate.name,
        theme=candidate.theme,
        composite_score=candidate.score.composite_score,
        portfolio_fit_score=portfolio_fit_score(projected_weight, is_new_theme),
        current_theme_weight_pct=current_theme_weight,
        projected_theme_weight_pct=projected_weight,
        structural_role=role,
        reason=reason,
    )


def review_replacements(
    held: Sequence[PositionAnalysis],
    candidates: Sequence[CandidateAnalysis],
) -> tuple[ReplacementReview, ...]:
    replacements: list[ReplacementReview] = []
    used_candidates: set[str] = set()
    weakest_holdings = sorted(held, key=lambda analysis: analysis.composite_score)
    ranked_candidates = sorted(
        candidates, key=lambda candidate: candidate.score.composite_score, reverse=True
    )
    for current in weakest_holdings:
        for candidate in ranked_candidates:
            if candidate.ticker in used_candidates:
                continue
            score_gap = candidate.score.composite_score - current.composite_score
            valuation_gap = candidate.score.valuation_points - current.valuation_points
            if score_gap >= UPGRADE_SCORE_GAP and valuation_gap >= -VALUATION_TOLERANCE:
                replacements.append(
                    ReplacementReview(
                        current_ticker=current.holding.ticker,
                        candidate_ticker=candidate.ticker,
                        candidate_name=candidate.name,
                        score_gap=score_gap,
                        reason="Candidate clears score gap without a material valuation penalty.",
                    )
                )
                used_candidates.add(candidate.ticker)
                break
        if len(replacements) == 3:
            break
    return tuple(replacements)


def review_trims(held: Sequence[PositionAnalysis]) -> tuple[TrimReview, ...]:
    if not held:
        return ()
    equal_weight = 100 / len(held)
    overweight_limit = equal_weight * 1.3
    trims = [
        TrimReview(
            ticker=analysis.holding.ticker,
            weight_pct=analysis.weight_pct,
            composite_score=analysis.composite_score,
            reason="Position is above the concentration limit with sub-threshold quality score.",
        )
        for analysis in held
        if analysis.weight_pct > overweight_limit and analysis.composite_score < TRIM_SCORE_LIMIT
    ]
    return tuple(sorted(trims, key=lambda item: item.weight_pct, reverse=True))


def review_portfolio(
    held: Sequence[PositionAnalysis],
    candidates: Sequence[CandidateAnalysis],
    target_min_positions: int = TARGET_MIN_POSITIONS,
    target_max_positions: int = TARGET_MAX_POSITIONS,
) -> PortfolioReview:
    additions_needed, additions = review_additions(
        held, candidates, target_min_positions, target_max_positions
    )
    return PortfolioReview(
        current_positions=len(held),
        target_min_positions=target_min_positions,
        target_max_positions=target_max_positions,
        additions_needed=additions_needed,
        add_candidates=additions,
        replacement_watch=review_replacements(held, candidates),
        trim_watch=review_trims(held),
    )
