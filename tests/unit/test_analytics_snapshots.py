"""Unit tests for fundamentals snapshots (no network)."""

from arenawealth.analytics.models import Fundamentals
from arenawealth.analytics.scoring import score_fundamentals
from arenawealth.analytics.snapshots import (
    latest_snapshot_path,
    load_snapshot,
    record_snapshot,
)


def make_fundamentals() -> Fundamentals:
    return Fundamentals(
        live_price=401.62, market_cap=520_000_000_000.0, return_on_equity=0.30,
        gross_margin=0.55, operating_margin=0.45, forward_pe=21.0,
        fifty_two_week_high=420.0, analyst_target=460.0, free_cash_flow=900_000_000_000.0,
        financial_currency="TWD", trading_currency="USD",
        revenue_series=(100.0, 118.0, 139.0), ebit_series=(40.0, 47.0, 55.0),
        tax_rate_series=(0.20, 0.20, 0.20), operating_income_series=(45.0, 52.0, 62.0),
        eps_series=(5.0, 6.1, 7.4), fcf_series=(30.0, 36.0, 44.0),
        diluted_shares_series=(100.0, 99.0, 98.0), invested_capital_series=(80.0, 84.0, 88.0),
    )


def fx_rate(base: str, quote: str) -> float:
    return 0.031


def test_snapshot_round_trip_preserves_fundamentals(tmp_path):
    fundamentals = {"TSM": make_fundamentals()}
    path = record_snapshot(fundamentals, fx_rate, directory=tmp_path)

    provider = load_snapshot(path)

    assert provider.get_fundamentals("TSM") == fundamentals["TSM"]
    assert provider.exchange_rate("TWD", "USD") == 0.031


def test_replay_scoring_is_deterministic(tmp_path):
    fundamentals = make_fundamentals()
    path = record_snapshot({"TSM": fundamentals}, fx_rate, directory=tmp_path)
    provider = load_snapshot(path)

    live_score = score_fundamentals(fundamentals, False, fx_rate)
    replay_score = score_fundamentals(
        provider.get_fundamentals("TSM"), False, provider.exchange_rate
    )
    assert live_score == replay_score


def test_latest_snapshot_path(tmp_path):
    assert latest_snapshot_path(tmp_path) is None
    path = record_snapshot({"TSM": make_fundamentals()}, fx_rate, directory=tmp_path)
    assert latest_snapshot_path(tmp_path) == path
