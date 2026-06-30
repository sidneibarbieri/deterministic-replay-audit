"""Point-in-time helpers for SEC company facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PointInTimeFact:
    tag: str
    unit: str
    value: float
    period_end: date
    filed: date
    form: str
    fiscal_year: int | None
    fiscal_period: str | None
    accession: str | None


def parse_sec_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("SEC date value must be a string")
    return date.fromisoformat(value)


def fact_entries(
    company_facts: Mapping[str, object],
    tag: str,
    unit: str = "USD",
    taxonomy: str = "us-gaap",
) -> tuple[PointInTimeFact, ...]:
    facts = company_facts.get("facts")
    if not isinstance(facts, Mapping):
        raise ValueError("company facts payload is missing facts")
    taxonomy_facts = facts.get(taxonomy)
    if not isinstance(taxonomy_facts, Mapping):
        return ()
    tag_payload = taxonomy_facts.get(tag)
    if not isinstance(tag_payload, Mapping):
        return ()
    units = tag_payload.get("units")
    if not isinstance(units, Mapping):
        return ()
    raw_entries = units.get(unit)
    if not isinstance(raw_entries, list):
        return ()

    entries = []
    for raw_entry in raw_entries:
        if isinstance(raw_entry, Mapping) and raw_entry.get("val") is not None:
            entries.append(to_point_in_time_fact(tag, unit, raw_entry))
    return tuple(sorted(entries, key=lambda entry: (entry.filed, entry.period_end)))


def facts_available_as_of(
    entries: Sequence[PointInTimeFact],
    as_of: date,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> tuple[PointInTimeFact, ...]:
    accepted_forms = {form.upper() for form in forms}
    return tuple(
        entry
        for entry in entries
        if entry.filed <= as_of and entry.form.upper() in accepted_forms
    )


def latest_fact_as_of(
    entries: Sequence[PointInTimeFact],
    as_of: date,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> PointInTimeFact | None:
    available = facts_available_as_of(entries, as_of, forms)
    if not available:
        return None
    return max(available, key=lambda entry: (entry.period_end, entry.filed))


def annual_series_as_of(
    entries: Sequence[PointInTimeFact],
    as_of: date,
    max_years: int = 10,
) -> tuple[PointInTimeFact, ...]:
    if max_years <= 0:
        raise ValueError("max_years must be positive")
    available = facts_available_as_of(entries, as_of, forms=("10-K", "20-F", "40-F"))
    by_year: dict[int, PointInTimeFact] = {}
    for entry in available:
        if entry.fiscal_year is None:
            continue
        current = by_year.get(entry.fiscal_year)
        if current is None or (entry.period_end, entry.filed) > (
            current.period_end,
            current.filed,
        ):
            by_year[entry.fiscal_year] = entry
    return tuple(
        by_year[fiscal_year]
        for fiscal_year in sorted(by_year, reverse=True)[:max_years]
    )


def to_point_in_time_fact(
    tag: str,
    unit: str,
    raw_entry: Mapping[str, object],
) -> PointInTimeFact:
    return PointInTimeFact(
        tag=tag,
        unit=unit,
        value=float(raw_entry["val"]),
        period_end=parse_sec_date(raw_entry["end"]),
        filed=parse_sec_date(raw_entry["filed"]),
        form=str(raw_entry.get("form", "")),
        fiscal_year=optional_int(raw_entry.get("fy")),
        fiscal_period=optional_string(raw_entry.get("fp")),
        accession=optional_string(raw_entry.get("accn")),
    )


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
