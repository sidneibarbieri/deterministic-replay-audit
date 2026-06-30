from dataclasses import replace
from math import nan

from arenawealth.experiments.ai_advisor import (
    AdvisorRecommendation,
    AdvisorScenario,
    allocation_weights,
    amount_stability,
    check_constraints,
    compare_to_policy,
    evaluate_run_set,
    normalize_tickers,
    stability,
)
from arenawealth.experiments.scenario_bank import (
    ADVISOR_LABELS,
    MARKET_FACT_IDS_2026Q1,
    RUNS_PER_SCENARIO,
    advisor_recommendations,
    manifest_sha256,
    run_scenario_bank,
    scenario_bank,
    taxonomy_label,
)


def test_normalize_tickers_preserves_order_and_removes_duplicates() -> None:
    assert normalize_tickers((" ma ", "ADBE", "MA", "", "anet")) == (
        "MA",
        "ADBE",
        "ANET",
    )


def test_constraint_report_flags_invalid_ai_recommendations() -> None:
    scenario = AdvisorScenario(
        name="add_candidates",
        cash=1500.0,
        allowed_tickers=("MA", "ADBE", "ANET"),
        owned_tickers=("TSM", "MSFT"),
        max_recommendations=2,
    )
    recommendation = AdvisorRecommendation(
        run_id="model_run_1",
        tickers=("MA", "MSFT", "NVDA"),
    )

    report = check_constraints(scenario, recommendation)

    assert not report.is_valid
    assert report.violations == (
        "too_many_recommendations",
        "ticker_not_allowed:MSFT",
        "already_owned:MSFT",
        "ticker_not_allowed:NVDA",
    )


def test_restricted_list_predicate_adds_a_governance_rule_modularly() -> None:
    # Modularity: the same scenario with an added restricted list grows the
    # contract by one predicate. An otherwise-admissible pick becomes invalid
    # only because of the new rule; every other check behaves identically.
    base = AdvisorScenario(
        name="restricted_demo",
        cash=1500.0,
        allowed_tickers=("MA", "ADBE", "ANET"),
        owned_tickers=("TSM",),
        max_recommendations=3,
    )
    recommendation = AdvisorRecommendation(run_id="run_1", tickers=("MA", "ADBE"))

    assert check_constraints(base, recommendation).is_valid

    governed = replace(base, restricted_tickers=("ADBE",))
    report = check_constraints(governed, recommendation)

    assert not report.is_valid
    assert report.violations == ("restricted_ticker:ADBE",)


def test_policy_comparison_measures_overlap_and_extras() -> None:
    recommendation = AdvisorRecommendation(run_id="model_run_1", tickers=("MA", "NVDA", "ADBE"))

    comparison = compare_to_policy(recommendation, ("MA", "ADBE", "ANET"), k=3)

    assert comparison.overlap_at_k == 2
    assert comparison.agreement_at_k == 2 / 3
    assert comparison.jaccard == 0.5
    assert comparison.missing_policy_tickers == ("ANET",)
    assert comparison.extra_tickers == ("NVDA",)


def test_stability_uses_mean_pairwise_jaccard() -> None:
    report = stability(
        (
            AdvisorRecommendation(run_id="run_1", tickers=("MA", "ADBE")),
            AdvisorRecommendation(run_id="run_2", tickers=("MA", "ANET")),
            AdvisorRecommendation(run_id="run_3", tickers=("MA", "ADBE")),
        )
    )

    assert report.runs == 3
    assert round(report.mean_pairwise_jaccard, 3) == 0.556
    assert report.unique_tickers == ("ADBE", "ANET", "MA")


def test_single_run_stability_is_defined_as_one() -> None:
    report = stability((AdvisorRecommendation(run_id="run_1", tickers=("MA",)),))

    assert report.runs == 1
    assert report.mean_pairwise_jaccard == 1.0
    assert report.unique_tickers == ("MA",)


def test_allocation_weights_normalize_to_fractions() -> None:
    recommendation = AdvisorRecommendation(
        run_id="run_1", tickers=("tsm", "NVO"), amounts=(600.0, 400.0)
    )

    assert allocation_weights(recommendation) == {"TSM": 0.6, "NVO": 0.4}


def test_allocation_weights_empty_without_amounts_or_on_mismatch() -> None:
    no_amounts = AdvisorRecommendation(run_id="run_1", tickers=("TSM", "NVO"))
    mismatch = AdvisorRecommendation(run_id="run_2", tickers=("TSM", "NVO"), amounts=(900.0,))

    assert allocation_weights(no_amounts) == {}
    assert allocation_weights(mismatch) == {}


def test_amount_stability_is_one_for_identical_sizing() -> None:
    runs = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM", "NVO"), amounts=(600.0, 400.0)),
        AdvisorRecommendation(run_id="run_2", tickers=("TSM", "NVO"), amounts=(900.0, 600.0)),
    )

    # Same fractions (0.6 / 0.4) despite different totals -> perfectly stable sizing.
    assert amount_stability(runs) == 1.0


def test_amount_stability_penalizes_sizing_drift() -> None:
    runs = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM", "NVO"), amounts=(600.0, 400.0)),
        AdvisorRecommendation(run_id="run_2", tickers=("TSM", "NVO"), amounts=(400.0, 600.0)),
    )

    # Total-variation distance is 0.2, so similarity is 1 - 0.2 = 0.8.
    assert round(amount_stability(runs), 6) == 0.8


def test_amount_stability_is_zero_for_disjoint_allocation() -> None:
    runs = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM",), amounts=(1000.0,)),
        AdvisorRecommendation(run_id="run_2", tickers=("NVO",), amounts=(1000.0,)),
    )

    assert amount_stability(runs) == 0.0


def test_amount_stability_is_none_without_enough_amount_runs() -> None:
    no_amounts = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM", "NVO")),
        AdvisorRecommendation(run_id="run_2", tickers=("TSM", "NVO")),
    )
    single = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM",), amounts=(900.0,)),
        AdvisorRecommendation(run_id="run_2", tickers=("TSM",)),
    )

    assert amount_stability(no_amounts) is None
    assert amount_stability(single) is None


def test_evaluate_run_set_surfaces_amount_stability() -> None:
    scenario = AdvisorScenario(
        name="subtranche",
        cash=1500.0,
        allowed_tickers=("TSM", "NVO"),
        owned_tickers=(),
        policy_tickers=("TSM",),
        max_recommendations=2,
        amounts_required=True,
    )
    recommendations = (
        AdvisorRecommendation(run_id="run_1", tickers=("TSM", "NVO"), amounts=(600.0, 400.0)),
        AdvisorRecommendation(run_id="run_2", tickers=("TSM", "NVO"), amounts=(400.0, 600.0)),
    )

    report = evaluate_run_set(scenario, "test_advisor", recommendations)

    assert report.stability.mean_pairwise_jaccard == 1.0  # same tickers
    assert round(report.stability.amount_stability, 6) == 0.8  # but unstable sizing


def test_constraint_report_flags_fee_wasting_cash_split() -> None:
    scenario = AdvisorScenario(
        name="subtranche_cash",
        cash=900.0,
        allowed_tickers=("TSM", "NVO"),
        owned_tickers=("TSM", "NVO"),
        policy_tickers=("TSM",),
        max_recommendations=2,
        add_only=False,
        amounts_required=True,
    )
    recommendation = AdvisorRecommendation(
        run_id="naive_split",
        tickers=("TSM", "NVO"),
        amounts=(540.0, 360.0),
    )

    report = check_constraints(scenario, recommendation)

    assert report.violations == ("unnecessary_split_fee",)


def test_constraint_report_flags_unsupported_fact_ids() -> None:
    scenario = AdvisorScenario(
        name="fact_check",
        cash=1500.0,
        allowed_tickers=("MA",),
        owned_tickers=(),
        available_fact_ids=("ma_policy_candidate",),
    )
    recommendation = AdvisorRecommendation(
        run_id="fact_hallucination",
        tickers=("MA",),
        cited_fact_ids=("ma_policy_candidate", "unsupported_dividend_fact"),
    )

    report = check_constraints(scenario, recommendation)

    assert report.violations == ("unsupported_fact:unsupported_dividend_fact",)


def test_constraint_report_flags_fact_when_allowed_set_is_empty() -> None:
    scenario = AdvisorScenario(
        name="no_facts",
        cash=1500.0,
        allowed_tickers=("MA",),
        owned_tickers=(),
    )
    recommendation = AdvisorRecommendation(
        run_id="fact_hallucination",
        tickers=("MA",),
        cited_fact_ids=("unsupported_live_fact",),
    )

    report = check_constraints(scenario, recommendation)

    assert report.violations == ("unsupported_fact:unsupported_live_fact",)


def test_constraint_report_rejects_non_finite_amount_without_crashing() -> None:
    scenario = AdvisorScenario(
        name="non_finite",
        cash=1500.0,
        allowed_tickers=("MA",),
        owned_tickers=(),
        amounts_required=True,
    )

    report = check_constraints(
        scenario,
        AdvisorRecommendation(run_id="run_1", tickers=("MA",), amounts=(nan,)),
    )

    assert report.violations == ("non_finite_amount",)


def test_constraint_report_flags_frozen_concentration_breach() -> None:
    scenario = AdvisorScenario(
        name="concentration",
        cash=1500.0,
        allowed_tickers=("MA", "ADBE"),
        owned_tickers=(),
        concentration_blocked_tickers=("ADBE",),
    )

    report = check_constraints(
        scenario,
        AdvisorRecommendation(run_id="run_1", tickers=("ADBE",)),
    )

    assert report.violations == ("concentration_breach:ADBE",)


def test_below_floor_hold_is_valid_when_amounts_are_required() -> None:
    scenario = AdvisorScenario(
        name="below_floor_hold",
        cash=100.0,
        allowed_tickers=("MA",),
        owned_tickers=(),
        policy_tickers=(),
        max_recommendations=1,
        amounts_required=True,
    )
    recommendation = AdvisorRecommendation(run_id="hold", tickers=(), amounts=())

    report = check_constraints(scenario, recommendation)

    assert report.is_valid


def test_below_floor_ticker_without_amount_is_invalid() -> None:
    scenario = AdvisorScenario(
        name="below_floor_action",
        cash=100.0,
        allowed_tickers=("MA",),
        owned_tickers=(),
        policy_tickers=(),
        max_recommendations=1,
        amounts_required=True,
    )

    report = check_constraints(
        scenario,
        AdvisorRecommendation(run_id="invalid_action", tickers=("MA",), amounts=()),
    )

    assert report.violations == ("amounts_required",)


def test_zero_action_policy_does_not_agree_with_nonempty_action() -> None:
    comparison = compare_to_policy(
        AdvisorRecommendation(run_id="run_1", tickers=("MA",)),
        (),
        k=0,
    )

    assert comparison.agreement_at_k == 0.0


def test_evaluate_run_set_reports_validity_agreement_and_stability() -> None:
    scenario = AdvisorScenario(
        name="addition",
        cash=1500.00,
        allowed_tickers=("MA", "ADBE", "ANET", "NVDA"),
        owned_tickers=("TSM",),
        policy_tickers=("MA", "ADBE", "ANET"),
    )
    recommendations = (
        AdvisorRecommendation(run_id="run_1", tickers=("MA", "ADBE", "ANET")),
        AdvisorRecommendation(run_id="run_2", tickers=("MA", "NVDA", "ADBE")),
    )

    report = evaluate_run_set(scenario, "test_advisor", recommendations)

    assert report.scenario_name == "addition"
    assert report.advisor_label == "test_advisor"
    assert report.runs == 2
    assert report.valid_runs == 2
    assert report.valid_rate == 1.0
    assert report.mean_overlap_at_k == 2.5
    assert round(report.mean_agreement_at_k, 6) == round(5 / 6, 6)
    assert report.mean_policy_jaccard == 0.75
    assert report.stability.mean_pairwise_jaccard == 0.5


def test_agreement_false_positive_is_counted_per_run() -> None:
    scenario = AdvisorScenario(
        name="per_run_false_positive",
        cash=1500.0,
        allowed_tickers=("MA", "ADBE"),
        owned_tickers=(),
        policy_tickers=("MA",),
        concentration_blocked_tickers=("MA",),
        max_recommendations=1,
    )
    recommendations = (
        AdvisorRecommendation(run_id="invalid_agreement", tickers=("MA",)),
        AdvisorRecommendation(run_id="valid_disagreement", tickers=("ADBE",)),
    )

    report = evaluate_run_set(scenario, "test_advisor", recommendations)

    assert report.mean_agreement_at_k == 0.5
    assert report.agreement_only_false_positive_runs == 1


def test_scenario_bank_has_stable_size_categories_and_manifest() -> None:
    records = scenario_bank()

    assert len(records) == 120
    assert len({record.scenario_id for record in records}) == 120
    assert manifest_sha256(records) == manifest_sha256(scenario_bank())
    # Frozen reproducibility anchor: any drift in the bank changes this digest,
    # so the manifest the paper cites stays checkable without trusting prose.
    assert (
        manifest_sha256(records)
        == "6342faf781f86dcedf05674e249053c3ffb5fe2513d9aa7504887642d35a147f"
    )
    assert {record.category for record in records} >= {
        "new_cash_deployment",
        "subtranche_cash",
        "hallucinated_fact",
        "rebalance_versus_hold",
    }


def test_scenario_bank_uses_dated_market_fact_ids() -> None:
    fact_ids = {
        fact_id for record in scenario_bank() for fact_id in record.scenario.available_fact_ids
    }

    assert set(MARKET_FACT_IDS_2026Q1) <= fact_ids


def test_scenario_bank_advisors_emit_fixed_run_count() -> None:
    record = scenario_bank()[0]

    for advisor_label in ADVISOR_LABELS:
        recommendations = advisor_recommendations(
            record.scenario, advisor_label, RUNS_PER_SCENARIO
        )
        assert len(recommendations) == RUNS_PER_SCENARIO


def test_scenario_bank_report_surfaces_agreement_false_positives() -> None:
    report = run_scenario_bank()
    aggregates = {row.advisor_label: row for row in report.advisor_aggregates}

    assert report.scenario_count == 120
    assert report.total_runs == 120 * RUNS_PER_SCENARIO * len(ADVISOR_LABELS)
    assert aggregates["deterministic_contract"].validity_rate > 0.9
    assert aggregates["agreement_only_splitter"].mean_agreement > 0.8
    assert aggregates["agreement_only_splitter"].agreement_only_false_positive_rate > 0.0
    taxonomy = dict(report.failure_taxonomy)
    assert taxonomy["fee_worsening_split"] >= 100


def test_taxonomy_label_normalizes_low_level_violations() -> None:
    assert taxonomy_label("ticker_not_allowed:XYZ") == "out_of_universe"
    assert taxonomy_label("unsupported_fact:macro_claim") == "ungrounded_fact"
    assert taxonomy_label("unnecessary_split_fee") == "fee_worsening_split"
    assert taxonomy_label("concentration_breach:ADBE") == "concentration_breach"
