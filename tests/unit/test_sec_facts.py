"""Unit tests for point-in-time SEC company facts."""

from datetime import date

import pytest

from arenawealth.analytics.sec_facts import (
    annual_series_as_of,
    fact_entries,
    latest_fact_as_of,
)


def company_facts_payload():
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "end": "2022-12-31",
                                "val": 100.0,
                                "filed": "2023-02-15",
                                "form": "10-K",
                                "fy": 2022,
                                "fp": "FY",
                                "accn": "000-test-2022",
                            },
                            {
                                "end": "2023-03-31",
                                "val": 30.0,
                                "filed": "2023-05-01",
                                "form": "10-Q",
                                "fy": 2023,
                                "fp": "Q1",
                                "accn": "000-test-2023-q1",
                            },
                            {
                                "end": "2023-12-31",
                                "val": 140.0,
                                "filed": "2024-02-20",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "accn": "000-test-2023",
                            },
                        ]
                    }
                }
            }
        }
    }


def test_latest_fact_as_of_uses_filing_date_not_period_end():
    entries = fact_entries(company_facts_payload(), "Revenues")

    latest = latest_fact_as_of(entries, date(2024, 1, 15))

    assert latest is not None
    assert latest.value == 30.0
    assert latest.period_end == date(2023, 3, 31)


def test_latest_fact_as_of_includes_later_filing_after_it_is_available():
    entries = fact_entries(company_facts_payload(), "Revenues")

    latest = latest_fact_as_of(entries, date(2024, 3, 1))

    assert latest is not None
    assert latest.value == 140.0
    assert latest.filed == date(2024, 2, 20)


def test_annual_series_as_of_excludes_quarters_and_unfiled_annuals():
    entries = fact_entries(company_facts_payload(), "Revenues")

    series = annual_series_as_of(entries, date(2024, 1, 15))

    assert [entry.fiscal_year for entry in series] == [2022]


def test_annual_series_requires_positive_max_years():
    entries = fact_entries(company_facts_payload(), "Revenues")

    with pytest.raises(ValueError, match="max_years"):
        annual_series_as_of(entries, date(2024, 1, 15), max_years=0)
