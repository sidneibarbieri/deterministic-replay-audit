"""Deterministic frozen-scenario benchmark for advisor audit experiments."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from statistics import mean

from arenawealth.experiments.ai_advisor import (
    AdvisorRecommendation,
    AdvisorRunSetReport,
    AdvisorScenario,
    evaluate_run_set,
    normalize_tickers,
)

RUNS_PER_SCENARIO = 5


@dataclass(frozen=True)
class ScenarioRecord:
    """One frozen scenario plus its benchmark category."""

    scenario_id: str
    category: str
    scenario: AdvisorScenario


@dataclass(frozen=True)
class AdvisorAggregate:
    advisor_label: str
    scenarios: int
    runs: int
    validity_rate: float
    mean_agreement: float
    mean_set_stability: float
    mean_amount_stability: float | None
    agreement_only_false_positive_rate: float
    violation_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ScenarioBankReport:
    scenario_count: int
    runs_per_scenario: int
    advisor_count: int
    total_runs: int
    manifest_sha256: str
    category_counts: tuple[tuple[str, int], ...]
    advisor_aggregates: tuple[AdvisorAggregate, ...]
    failure_taxonomy: tuple[tuple[str, int], ...]


ADVISOR_LABELS = (
    "deterministic_contract",
    "agreement_only_splitter",
    "unstable_selector",
    "fact_hallucinator",
    "cash_overrun",
)

MARKET_FACT_IDS_2026Q1 = (
    "em_equity_2025_return_34_4pct",
    "developed_international_2025_return_31_9pct",
    "asset_allocation_2025_return_15_8pct",
    "us_aggregate_2025_return_7_3pct",
    "mag7_sp500_return_share_2025_46pct",
    "sp500_all_time_highs_2025_39",
    "us_gdp_3q25_annualized_4_3pct",
    "unemployment_nov2025_4_6pct",
    "fed_funds_dec2025_3_63pct",
)


def scenario_bank() -> tuple[ScenarioRecord, ...]:
    """Return a 120-scenario deterministic benchmark with fixed IDs."""
    records: list[ScenarioRecord] = []
    for variant in range(10):
        records.extend(_scenario_batch(variant))
    return tuple(records)


def run_scenario_bank() -> ScenarioBankReport:
    """Evaluate all offline advisor configurations on the frozen bank."""
    records = scenario_bank()
    reports_by_advisor: dict[str, list[AdvisorRunSetReport]] = {
        label: [] for label in ADVISOR_LABELS
    }
    taxonomy_counts: dict[str, int] = {}
    for record in records:
        for advisor_label in ADVISOR_LABELS:
            recommendations = advisor_recommendations(
                record.scenario, advisor_label, RUNS_PER_SCENARIO
            )
            report = evaluate_run_set(record.scenario, advisor_label, recommendations)
            reports_by_advisor[advisor_label].append(report)
            for violation, count in report.violation_counts:
                taxonomy = taxonomy_label(violation)
                taxonomy_counts[taxonomy] = taxonomy_counts.get(taxonomy, 0) + count

    return ScenarioBankReport(
        scenario_count=len(records),
        runs_per_scenario=RUNS_PER_SCENARIO,
        advisor_count=len(ADVISOR_LABELS),
        total_runs=len(records) * RUNS_PER_SCENARIO * len(ADVISOR_LABELS),
        manifest_sha256=manifest_sha256(records),
        category_counts=_category_counts(records),
        advisor_aggregates=tuple(
            _aggregate_advisor(label, reports) for label, reports in reports_by_advisor.items()
        ),
        failure_taxonomy=tuple(sorted(taxonomy_counts.items())),
    )


def advisor_recommendations(
    scenario: AdvisorScenario, advisor_label: str, runs: int = RUNS_PER_SCENARIO
) -> tuple[AdvisorRecommendation, ...]:
    factories: dict[str, Callable[[AdvisorScenario, int], AdvisorRecommendation]] = {
        "deterministic_contract": _deterministic_contract,
        "agreement_only_splitter": _agreement_only_splitter,
        "unstable_selector": _unstable_selector,
        "fact_hallucinator": _fact_hallucinator,
        "cash_overrun": _cash_overrun,
    }
    if advisor_label not in factories:
        raise ValueError(f"unknown advisor configuration: {advisor_label}")
    return tuple(factories[advisor_label](scenario, run) for run in range(1, runs + 1))


def manifest_sha256(records: tuple[ScenarioRecord, ...]) -> str:
    """Hash the scenario bank in canonical JSON form."""
    payload = [
        {
            "scenario_id": record.scenario_id,
            "category": record.category,
            "scenario": asdict(record.scenario),
        }
        for record in records
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def taxonomy_label(violation: str) -> str:
    """Map low-level verifier messages to paper-facing failure classes."""
    if violation == "too_many_recommendations":
        return "too_many_recommendations"
    if violation.startswith("ticker_not_allowed:"):
        return "out_of_universe"
    if violation.startswith("already_owned:"):
        return "already_owned_violation"
    if violation.startswith("concentration_breach:"):
        return "concentration_breach"
    if violation in {"amounts_required", "amount_count_mismatch", "non_finite_amount"}:
        return "malformed_amounts"
    if violation == "cash_exceeded":
        return "cash_overrun"
    if violation == "cash_underdeployed":
        return "cash_underdeployment"
    if violation.startswith("non_positive_order:"):
        return "non_positive_order"
    if violation.startswith("below_min_order:"):
        return "below_floor_order"
    if violation == "unnecessary_split_fee":
        return "fee_worsening_split"
    if violation.startswith("unsupported_fact:"):
        return "ungrounded_fact"
    return violation


def _scenario_batch(variant: int) -> tuple[ScenarioRecord, ...]:
    suffix = f"{variant + 1:03d}"
    base_universe = _rotate(("MA", "ADBE", "ANET", "NVO", "TSM", "ASML", "MSFT", "GOOGL"), variant)
    market_facts = _market_facts(variant)
    owned = base_universe[4:6]
    policy = base_universe[:3]
    cash_large = 1250.0 + variant * 25.0
    cash_small = 180.0 + variant * 5.0
    cash_subtranche = 900.0 + variant * 10.0
    return (
        _record(
            suffix,
            "new_cash_deployment",
            cash_large,
            base_universe,
            owned,
            policy,
            amounts_required=True,
        ),
        _record(
            suffix,
            "subtranche_cash",
            cash_subtranche,
            base_universe,
            owned,
            policy[:1],
            max_recommendations=2,
            add_only=False,
            amounts_required=True,
        ),
        _record(
            suffix,
            "already_owned_asset",
            cash_large,
            base_universe,
            policy[:1] + owned,
            policy,
        ),
        _record(
            suffix,
            "fee_sensitive_order",
            cash_subtranche,
            base_universe,
            owned,
            policy[:1],
            max_recommendations=2,
            amounts_required=True,
        ),
        _record(
            suffix,
            "insufficient_cash",
            cash_small,
            base_universe,
            owned,
            (),
            max_recommendations=1,
            amounts_required=True,
        ),
        _record(
            suffix,
            "out_of_universe_ticker",
            cash_large,
            base_universe[:5],
            owned,
            policy[:2],
        ),
        _record(
            suffix,
            "hallucinated_fact",
            cash_large,
            base_universe,
            owned,
            policy[:2],
            available_fact_ids=market_facts[:3],
        ),
        _record(
            suffix,
            "stale_market_fact",
            cash_large,
            base_universe,
            owned,
            policy[:2],
            available_fact_ids=market_facts[3:6],
        ),
        _record(
            suffix,
            "drawdown_case",
            cash_large,
            base_universe,
            owned,
            policy[:2],
            available_fact_ids=market_facts[6:8],
        ),
        _record(
            suffix,
            "rebalance_versus_hold",
            cash_large,
            base_universe,
            owned,
            policy[:1],
            max_recommendations=1,
            amounts_required=True,
            min_cash_deployment_fraction=0.95,
        ),
        _record(
            suffix,
            "fractional_share_unavailable",
            cash_large,
            base_universe,
            owned,
            policy[:1],
            max_recommendations=1,
            amounts_required=True,
            min_cash_deployment_fraction=0.90,
        ),
        _record(
            suffix,
            "conflicting_rationale",
            cash_large,
            base_universe,
            owned,
            policy[:2],
            available_fact_ids=market_facts[:1] + market_facts[-1:],
        ),
    )


def _record(
    suffix: str,
    category: str,
    cash: float,
    allowed_tickers: tuple[str, ...],
    owned_tickers: tuple[str, ...],
    policy_tickers: tuple[str, ...],
    *,
    max_recommendations: int = 3,
    add_only: bool = True,
    amounts_required: bool = False,
    available_fact_ids: tuple[str, ...] = (),
    min_cash_deployment_fraction: float | None = None,
) -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id=f"{category}_{suffix}",
        category=category,
        scenario=AdvisorScenario(
            name=f"{category}_{suffix}",
            cash=cash,
            allowed_tickers=allowed_tickers,
            owned_tickers=owned_tickers,
            policy_tickers=policy_tickers,
            available_fact_ids=available_fact_ids,
            max_recommendations=max_recommendations,
            add_only=add_only,
            amounts_required=amounts_required,
            min_cash_deployment_fraction=min_cash_deployment_fraction,
        ),
    )


def _deterministic_contract(scenario: AdvisorScenario, run: int) -> AdvisorRecommendation:
    tickers = _policy_or_empty(scenario)
    if scenario.amounts_required:
        tickers = tickers[:1]
    amounts = _valid_amounts(scenario, tickers)
    cited = scenario.available_fact_ids[:1]
    return AdvisorRecommendation(
        f"run_{run}", tickers=tickers, amounts=amounts, cited_fact_ids=cited
    )


def _agreement_only_splitter(scenario: AdvisorScenario, run: int) -> AdvisorRecommendation:
    tickers = _policy_or_fallback(scenario)
    if scenario.amounts_required and tickers:
        split_count = min(2, len(tickers))
        if split_count == 1 and len(scenario.allowed_tickers) > 1:
            tickers = (tickers[0], _first_not_in(tickers, scenario.allowed_tickers))
            split_count = 2
        amount = round(scenario.cash / split_count, 2)
        amounts = tuple(amount for _ in range(split_count))
        tickers = tickers[:split_count]
    else:
        amounts = ()
    cited = scenario.available_fact_ids[:1]
    return AdvisorRecommendation(
        f"run_{run}", tickers=tickers, amounts=amounts, cited_fact_ids=cited
    )


def _unstable_selector(scenario: AdvisorScenario, run: int) -> AdvisorRecommendation:
    allowed = normalize_tickers(scenario.allowed_tickers)
    start = (run - 1) % max(len(allowed), 1)
    tickers = _rotate(allowed, start)[: scenario.max_recommendations]
    if scenario.add_only:
        tickers = tuple(ticker for ticker in tickers if ticker not in scenario.owned_tickers)
    amounts = _valid_amounts(scenario, tickers[:1] if scenario.amounts_required else tickers)
    tickers = tickers[: len(amounts)] if amounts else tickers
    return AdvisorRecommendation(f"run_{run}", tickers=tickers, amounts=amounts)


def _fact_hallucinator(scenario: AdvisorScenario, run: int) -> AdvisorRecommendation:
    tickers = _policy_or_fallback(scenario)
    if scenario.amounts_required:
        tickers = tickers[:1]
    amounts = _valid_amounts(scenario, tickers)
    cited = (*scenario.available_fact_ids[:1], f"unsupported_live_fact_{run}")
    return AdvisorRecommendation(
        f"run_{run}", tickers=tickers, amounts=amounts, cited_fact_ids=cited
    )


def _cash_overrun(scenario: AdvisorScenario, run: int) -> AdvisorRecommendation:
    tickers = _policy_or_fallback(scenario)[:1]
    if scenario.amounts_required and tickers:
        amounts = (round(scenario.cash + 100.0 + run, 2),)
    else:
        amounts = ()
    return AdvisorRecommendation(f"run_{run}", tickers=tickers, amounts=amounts)


def _policy_or_empty(scenario: AdvisorScenario) -> tuple[str, ...]:
    tickers = normalize_tickers(scenario.policy_tickers)
    if scenario.add_only:
        owned = set(normalize_tickers(scenario.owned_tickers))
        tickers = tuple(ticker for ticker in tickers if ticker not in owned)
    return tickers[: scenario.max_recommendations]


def _policy_or_fallback(scenario: AdvisorScenario) -> tuple[str, ...]:
    policy = _policy_or_empty(scenario)
    if policy:
        return policy
    allowed = normalize_tickers(scenario.allowed_tickers)
    return allowed[:1]


def _valid_amounts(scenario: AdvisorScenario, tickers: tuple[str, ...]) -> tuple[float, ...]:
    if not scenario.amounts_required or not tickers:
        return ()
    if scenario.cash < scenario.min_order_amount:
        return ()
    return (round(scenario.cash, 2),)


def _first_not_in(existing: tuple[str, ...], candidates: tuple[str, ...]) -> str:
    existing_set = set(existing)
    for candidate in normalize_tickers(candidates):
        if candidate not in existing_set:
            return candidate
    return normalize_tickers(candidates)[0]


def _rotate(values: tuple[str, ...], offset: int) -> tuple[str, ...]:
    if not values:
        return values
    offset = offset % len(values)
    return values[offset:] + values[:offset]


def _market_facts(variant: int) -> tuple[str, ...]:
    return _rotate(MARKET_FACT_IDS_2026Q1, variant)


def _category_counts(records: tuple[ScenarioRecord, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.category] = counts.get(record.category, 0) + 1
    return tuple(sorted(counts.items()))


def _aggregate_advisor(advisor_label: str, reports: list[AdvisorRunSetReport]) -> AdvisorAggregate:
    runs = sum(report.runs for report in reports)
    valid_runs = sum(report.valid_runs for report in reports)
    amount_stability_values = [
        report.stability.amount_stability
        for report in reports
        if report.stability.amount_stability is not None
    ]
    violation_counts: dict[str, int] = {}
    false_positive_runs = 0
    for report in reports:
        for violation, count in report.violation_counts:
            taxonomy = taxonomy_label(violation)
            violation_counts[taxonomy] = violation_counts.get(taxonomy, 0) + count
        false_positive_runs += report.agreement_only_false_positive_runs
    return AdvisorAggregate(
        advisor_label=advisor_label,
        scenarios=len(reports),
        runs=runs,
        validity_rate=valid_runs / runs if runs else 0.0,
        mean_agreement=mean(report.mean_agreement_at_k for report in reports),
        mean_set_stability=mean(report.stability.mean_pairwise_jaccard for report in reports),
        mean_amount_stability=(mean(amount_stability_values) if amount_stability_values else None),
        agreement_only_false_positive_rate=false_positive_runs / runs if runs else 0.0,
        violation_counts=tuple(sorted(violation_counts.items())),
    )
