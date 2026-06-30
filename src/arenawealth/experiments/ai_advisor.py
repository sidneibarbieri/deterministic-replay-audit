"""Offline metrics for AI-advisor recommendation benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from statistics import mean

from arenawealth.fee_contract import MIN_ORDER_AMOUNT, order_fee


@dataclass(frozen=True)
class AdvisorScenario:
    """Frozen constraints for one AI-advisor benchmark prompt."""

    name: str
    cash: float
    allowed_tickers: tuple[str, ...]
    owned_tickers: tuple[str, ...]
    policy_tickers: tuple[str, ...] = ()
    # A compliance restricted list. Empty by default, so adding this governance
    # rule leaves every existing scenario and its verdict unchanged: the contract
    # grows by one predicate without touching the audit protocol or the metrics.
    restricted_tickers: tuple[str, ...] = ()
    # Tickers whose projected post-trade position or theme weight breaches a
    # concentration limit computed from the frozen scenario.
    concentration_blocked_tickers: tuple[str, ...] = ()
    available_fact_ids: tuple[str, ...] = ()
    max_recommendations: int = 3
    add_only: bool = True
    amounts_required: bool = False
    min_order_amount: float = MIN_ORDER_AMOUNT
    min_cash_deployment_fraction: float | None = None


@dataclass(frozen=True)
class AdvisorRecommendation:
    """One model or advisor output reduced to auditable tickers."""

    run_id: str
    tickers: tuple[str, ...]
    amounts: tuple[float, ...] = ()
    cited_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstraintReport:
    run_id: str
    violations: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class PolicyComparison:
    run_id: str
    overlap_at_k: int
    agreement_at_k: float
    jaccard: float
    missing_policy_tickers: tuple[str, ...]
    extra_tickers: tuple[str, ...]


@dataclass(frozen=True)
class StabilityReport:
    runs: int
    mean_pairwise_jaccard: float
    unique_tickers: tuple[str, ...]
    amount_stability: float | None = None


@dataclass(frozen=True)
class AdvisorRunSetReport:
    scenario_name: str
    advisor_label: str
    runs: int
    valid_runs: int
    violation_counts: tuple[tuple[str, int], ...]
    stability: StabilityReport
    mean_overlap_at_k: float
    mean_agreement_at_k: float
    mean_policy_jaccard: float
    agreement_only_false_positive_runs: int
    mean_cash_used: float | None
    mean_fee: float | None

    @property
    def valid_rate(self) -> float:
        if self.runs == 0:
            return 0.0
        return self.valid_runs / self.runs


def normalize_tickers(tickers: tuple[str, ...]) -> tuple[str, ...]:
    """Uppercase tickers and remove duplicates while preserving first occurrence."""
    seen: set[str] = set()
    normalized: list[str] = []
    for ticker in tickers:
        clean_ticker = ticker.strip().upper()
        if not clean_ticker or clean_ticker in seen:
            continue
        seen.add(clean_ticker)
        normalized.append(clean_ticker)
    return tuple(normalized)


def jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 1.0
    return len(left_set & right_set) / len(union)


def allocation_weights(recommendation: AdvisorRecommendation) -> dict[str, float]:
    """Fraction of deployed cash per ticker.

    Set-based agreement and stability ignore sizing: two runs can pick the same
    tickers yet allocate the cash very differently. This reduces a recommendation
    to a weight distribution over tickers so sizing can be compared directly.
    Returns an empty mapping when amounts are absent or do not align with tickers.
    """
    tickers = tuple(ticker.strip().upper() for ticker in recommendation.tickers)
    amounts = recommendation.amounts
    if not amounts or len(amounts) != len(tickers):
        return {}
    total = sum(amounts)
    if total <= 0:
        return {}
    weights: dict[str, float] = {}
    for ticker, amount in zip(tickers, amounts, strict=True):
        weights[ticker] = weights.get(ticker, 0.0) + amount / total
    return weights


def _total_variation(left: dict[str, float], right: dict[str, float]) -> float:
    """Total-variation distance between two weight distributions, in [0, 1]."""
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def amount_stability(
    recommendations: tuple[AdvisorRecommendation, ...],
) -> float | None:
    """Sizing consistency across runs, in [0, 1] (1 = identical allocation).

    Defined as 1 minus the mean pairwise total-variation distance over allocation
    weight vectors. Returns None when fewer than two runs carry usable amounts,
    so it is reported only where sizing is actually observed.
    """
    vectors = [allocation_weights(recommendation) for recommendation in recommendations]
    vectors = [vector for vector in vectors if vector]
    if len(vectors) < 2:
        return None
    distances = [_total_variation(left, right) for left, right in combinations(vectors, 2)]
    return 1.0 - mean(distances)


def check_constraints(
    scenario: AdvisorScenario, recommendation: AdvisorRecommendation
) -> ConstraintReport:
    tickers = normalize_tickers(recommendation.tickers)
    allowed = set(normalize_tickers(scenario.allowed_tickers))
    owned = set(normalize_tickers(scenario.owned_tickers))
    restricted = set(normalize_tickers(scenario.restricted_tickers))
    concentration_blocked = set(
        normalize_tickers(scenario.concentration_blocked_tickers)
    )
    violations: list[str] = []
    if len(tickers) > scenario.max_recommendations:
        violations.append("too_many_recommendations")
    for ticker in tickers:
        if ticker not in allowed:
            violations.append(f"ticker_not_allowed:{ticker}")
        if scenario.add_only and ticker in owned:
            violations.append(f"already_owned:{ticker}")
        if ticker in restricted:
            violations.append(f"restricted_ticker:{ticker}")
        if ticker in concentration_blocked:
            violations.append(f"concentration_breach:{ticker}")
    violations.extend(_amount_violations(scenario, tickers, recommendation.amounts))
    violations.extend(_fact_violations(scenario, recommendation.cited_fact_ids))
    return ConstraintReport(run_id=recommendation.run_id, violations=tuple(violations))


def _amount_violations(
    scenario: AdvisorScenario,
    tickers: tuple[str, ...],
    amounts: tuple[float, ...],
) -> list[str]:
    if not amounts:
        if (
            scenario.amounts_required
            and not tickers
            and scenario.cash < scenario.min_order_amount
        ):
            return []
        return ["amounts_required"] if scenario.amounts_required else []
    violations: list[str] = []
    if len(amounts) != len(tickers):
        violations.append("amount_count_mismatch")
        return violations
    if any(not isfinite(amount) for amount in amounts):
        violations.append("non_finite_amount")
        return violations
    cash_used = sum(amounts)
    if cash_used > scenario.cash + 0.01:
        violations.append("cash_exceeded")
    if (
        scenario.min_cash_deployment_fraction is not None
        and scenario.cash >= scenario.min_order_amount
        and cash_used + 0.01 < scenario.cash * scenario.min_cash_deployment_fraction
    ):
        violations.append("cash_underdeployed")
    for ticker, amount in zip(tickers, amounts, strict=True):
        if amount <= 0:
            violations.append(f"non_positive_order:{ticker}")
        elif amount < scenario.min_order_amount:
            violations.append(f"below_min_order:{ticker}")
    if sum(order_fee(amount) for amount in amounts) > order_fee(cash_used):
        violations.append("unnecessary_split_fee")
    return violations


def _fact_violations(scenario: AdvisorScenario, cited_fact_ids: tuple[str, ...]) -> list[str]:
    if not cited_fact_ids:
        return []
    available = set(scenario.available_fact_ids)
    return [
        f"unsupported_fact:{fact_id}" for fact_id in cited_fact_ids if fact_id not in available
    ]


def compare_to_policy(
    recommendation: AdvisorRecommendation, policy_tickers: tuple[str, ...], k: int
) -> PolicyComparison:
    normalized_advisor = normalize_tickers(recommendation.tickers)
    advisor_top = normalized_advisor[:k]
    policy_top = normalize_tickers(policy_tickers)[:k]
    advisor_set = set(advisor_top)
    policy_set = set(policy_top)
    if k == 0:
        agreement_at_k = 1.0 if not normalized_advisor else 0.0
    else:
        agreement_at_k = len(advisor_set & policy_set) / k
    return PolicyComparison(
        run_id=recommendation.run_id,
        overlap_at_k=len(advisor_set & policy_set),
        agreement_at_k=agreement_at_k,
        jaccard=jaccard(advisor_top, policy_top),
        missing_policy_tickers=tuple(ticker for ticker in policy_top if ticker not in advisor_set),
        extra_tickers=tuple(ticker for ticker in advisor_top if ticker not in policy_set),
    )


def stability(recommendations: tuple[AdvisorRecommendation, ...]) -> StabilityReport:
    normalized = [normalize_tickers(recommendation.tickers) for recommendation in recommendations]
    unique = tuple(sorted({ticker for tickers in normalized for ticker in tickers}))
    sizing = amount_stability(recommendations)
    if len(normalized) < 2:
        return StabilityReport(
            runs=len(normalized),
            mean_pairwise_jaccard=1.0,
            unique_tickers=unique,
            amount_stability=sizing,
        )
    scores = [jaccard(left, right) for left, right in combinations(normalized, 2)]
    return StabilityReport(
        runs=len(normalized),
        mean_pairwise_jaccard=mean(scores),
        unique_tickers=unique,
        amount_stability=sizing,
    )


def evaluate_run_set(
    scenario: AdvisorScenario,
    advisor_label: str,
    recommendations: tuple[AdvisorRecommendation, ...],
) -> AdvisorRunSetReport:
    """Evaluate repeated advisor outputs for one frozen scenario."""
    constraint_reports = [
        check_constraints(scenario, recommendation) for recommendation in recommendations
    ]
    comparisons = [
        compare_to_policy(
            recommendation,
            scenario.policy_tickers,
            min(scenario.max_recommendations, len(scenario.policy_tickers)),
        )
        for recommendation in recommendations
    ]
    agreement_false_positives = sum(
        comparison.agreement_at_k == 1.0 and not constraint_report.is_valid
        for comparison, constraint_report in zip(
            comparisons, constraint_reports, strict=True
        )
    )
    cash_values = [
        sum(recommendation.amounts) for recommendation in recommendations if recommendation.amounts
    ]
    fee_values = [
        sum(order_fee(amount) for amount in recommendation.amounts)
        for recommendation in recommendations
        if recommendation.amounts
    ]
    return AdvisorRunSetReport(
        scenario_name=scenario.name,
        advisor_label=advisor_label,
        runs=len(recommendations),
        valid_runs=sum(report.is_valid for report in constraint_reports),
        violation_counts=_count_violations(constraint_reports),
        stability=stability(recommendations),
        mean_overlap_at_k=_mean([comparison.overlap_at_k for comparison in comparisons]),
        mean_agreement_at_k=_mean(
            [comparison.agreement_at_k for comparison in comparisons]
        ),
        mean_policy_jaccard=_mean([comparison.jaccard for comparison in comparisons]),
        agreement_only_false_positive_runs=agreement_false_positives,
        mean_cash_used=_mean(cash_values) if cash_values else None,
        mean_fee=_mean(fee_values) if fee_values else None,
    )


def _count_violations(
    reports: list[ConstraintReport],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for report in reports:
        for violation in report.violations:
            counts[violation] = counts.get(violation, 0) + 1
    return tuple(sorted(counts.items()))


def _mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return float(mean(values))
