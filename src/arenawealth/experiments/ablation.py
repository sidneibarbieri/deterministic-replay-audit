"""Ablation and sensitivity over the composite ranking.

The composite score is a linear functional of three bounded sub-scores:

    composite = w_moat * moat + w_comp * compounding + w_val * valuation

Because it is linear with explicit weights, the ranking it induces is directly
ablatable (zero a weight) and its sensitivity to the weights is analyzable. We
recompose the score from the per-position sub-points already attached to each
PositionAnalysis, so no re-scoring or data fetch is needed: the ablation is a
pure transform of an existing analysis set.

Findings to observe: which factor dominates the ordering on a given basket, and
how stable the funded picks are when the weights are perturbed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arenawealth.analytics.models import PositionAnalysis

Weights = Mapping[str, float]

BASELINE_WEIGHTS: dict[str, float] = {"moat": 0.40, "compounding": 0.35, "valuation": 0.25}


def recompose(analysis: PositionAnalysis, weights: Weights) -> float:
    return (
        weights.get("moat", 0.0) * analysis.moat_points
        + weights.get("compounding", 0.0) * analysis.compounding_points
        + weights.get("valuation", 0.0) * analysis.valuation_points
    )


def rank_under_weights(analyses: Sequence[PositionAnalysis], weights: Weights) -> tuple[str, ...]:
    """Tickers ordered by recomposed score, highest first (ties broken by ticker)."""
    scored = [(recompose(a, weights), a.holding.ticker) for a in analyses]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return tuple(ticker for _, ticker in scored)


def _ranks(order: Sequence[str]) -> dict[str, int]:
    return {ticker: index for index, ticker in enumerate(order)}


def spearman(order_a: Sequence[str], order_b: Sequence[str]) -> float:
    """Rank correlation in [-1, 1]. No SciPy dependency."""
    ranks_b = _ranks(order_b)
    length = len(order_a)
    if length < 2:
        return 1.0
    ranks_a = list(range(length))
    paired_ranks_b = [ranks_b[ticker] for ticker in order_a]
    mean_a = sum(ranks_a) / length
    mean_b = sum(paired_ranks_b) / length
    covariance = sum(
        (rank_a - mean_a) * (rank_b - mean_b)
        for rank_a, rank_b in zip(ranks_a, paired_ranks_b, strict=True)
    )
    variance_a = sum((rank_a - mean_a) ** 2 for rank_a in ranks_a)
    variance_b = sum((rank_b - mean_b) ** 2 for rank_b in paired_ranks_b)
    if variance_a == 0 or variance_b == 0:
        return 0.0
    return covariance / (variance_a * variance_b) ** 0.5


@dataclass(frozen=True)
class AblationRow:
    label: str
    weights: dict[str, float]
    top: tuple[str, ...]
    spearman_vs_baseline: float
    top_k_churn: int


def weight_ablation(
    analyses: Sequence[PositionAnalysis],
    weight_sets: Mapping[str, Weights],
    baseline: Weights = BASELINE_WEIGHTS,
    top_k: int = 2,
) -> tuple[AblationRow, ...]:
    """Compare each weight set's ranking to the baseline's."""
    base_order = rank_under_weights(analyses, baseline)
    base_top = set(base_order[:top_k])
    rows: list[AblationRow] = []
    for label, weights in weight_sets.items():
        order = rank_under_weights(analyses, weights)
        top = order[:top_k]
        churn = len(base_top - set(top))
        rows.append(
            AblationRow(
                label=label,
                weights=dict(weights),
                top=top,
                spearman_vs_baseline=spearman(base_order, order),
                top_k_churn=churn,
            )
        )
    return tuple(rows)


def standard_weight_sets() -> dict[str, Weights]:
    """A baseline plus single-factor and equal-weight ablations."""
    return {
        "baseline_40_35_25": BASELINE_WEIGHTS,
        "moat_only": {"moat": 1.0, "compounding": 0.0, "valuation": 0.0},
        "compounding_only": {"moat": 0.0, "compounding": 1.0, "valuation": 0.0},
        "valuation_only": {"moat": 0.0, "compounding": 0.0, "valuation": 1.0},
        "equal_thirds": {"moat": 1 / 3, "compounding": 1 / 3, "valuation": 1 / 3},
    }


@dataclass(frozen=True)
class SensitivityRow:
    factor: str
    delta: float
    top: tuple[str, ...]
    top_k_changed: bool


def weight_sensitivity(
    analyses: Sequence[PositionAnalysis],
    base_weights: Weights = BASELINE_WEIGHTS,
    deltas: Sequence[float] = (-0.10, -0.05, 0.05, 0.10),
    top_k: int = 2,
) -> tuple[SensitivityRow, ...]:
    """Perturb one factor's weight at a time; record whether the top-k changes.

    Each perturbation shifts the named factor by delta and renormalizes the
    remaining factors proportionally, so the weights still sum to one.
    """
    base_order = rank_under_weights(analyses, base_weights)
    base_top = base_order[:top_k]
    rows: list[SensitivityRow] = []
    for factor in base_weights:
        for delta in deltas:
            perturbed = _perturb(base_weights, factor, delta)
            if perturbed is None:
                continue
            order = rank_under_weights(analyses, perturbed)
            rows.append(
                SensitivityRow(
                    factor=factor,
                    delta=delta,
                    top=order[:top_k],
                    top_k_changed=order[:top_k] != base_top,
                )
            )
    return tuple(rows)


def _perturb(weights: Weights, factor: str, delta: float) -> dict[str, float] | None:
    new_value = weights[factor] + delta
    if new_value < 0:
        return None
    others = {k: v for k, v in weights.items() if k != factor}
    others_total = sum(others.values())
    if others_total <= 0:
        return None
    remaining = 1.0 - new_value
    if remaining < 0:
        return None
    scaled = {k: v / others_total * remaining for k, v in others.items()}
    scaled[factor] = new_value
    return scaled
