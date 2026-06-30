"""Unit tests for the adversarial advisor scenario generator (no network)."""

from arenawealth.experiments.adversarial_scenarios import (
    adversarial_scenarios,
)

REQUIRED_KEYS = {
    "name",
    "category",
    "cash",
    "allowed_tickers",
    "owned_tickers",
    "policy_tickers",
    "available_fact_ids",
    "max_recommendations",
    "add_only",
    "amounts_required",
}


def test_generator_is_deterministic():
    assert adversarial_scenarios() == adversarial_scenarios()


def test_scenarios_cover_the_target_categories():
    categories = {scenario.category for scenario in adversarial_scenarios()}
    assert categories == {
        "unnecessary_split_fee",
        "below_min_order",
        "cash_exceeded",
        "already_owned",
        "too_many_recommendations",
        "unsupported_fact",
    }


def test_payload_has_the_collector_keys():
    for scenario in adversarial_scenarios():
        assert set(scenario.to_payload()) >= REQUIRED_KEYS


def test_no_fact_leaks_the_fee_arithmetic():
    leak_terms = ("fee", "split", "tranche", "floor", "below", "cash")
    for scenario in adversarial_scenarios():
        for fact_id in scenario.available_fact_ids:
            assert not any(term in fact_id.lower() for term in leak_terms)


def test_names_are_unique():
    names = [scenario.name for scenario in adversarial_scenarios()]
    assert len(names) == len(set(names))
