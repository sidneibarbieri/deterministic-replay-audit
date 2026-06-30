"""Unit tests for the candidate universe screener (no network)."""

from arenawealth.analytics.models import Fundamentals
from arenawealth.analytics.screening import CandidateAnalysis, screen_candidates
from arenawealth.analytics.universe import CANDIDATE_UNIVERSE


def fundamentals(quality: str, price: float) -> Fundamentals:
    if quality == "strong":
        return Fundamentals(
            live_price=price, market_cap=200.0, return_on_equity=0.35,
            gross_margin=0.65, operating_margin=0.40, forward_pe=22.0,
            fifty_two_week_high=price * 1.2, analyst_target=price * 1.1, free_cash_flow=20.0,
            financial_currency="USD", trading_currency="USD",
            revenue_series=(100.0, 115.0, 132.0), ebit_series=(25.0, 30.0, 36.0),
            tax_rate_series=(0.20, 0.20, 0.20), operating_income_series=(40.0, 46.0, 53.0),
            eps_series=(2.0, 2.6, 3.4), fcf_series=(15.0, 18.0, 22.0),
            diluted_shares_series=(100.0, 98.0, 96.0), invested_capital_series=(80.0, 82.0, 84.0),
        )
    return Fundamentals(
        live_price=price, market_cap=200.0, return_on_equity=0.06,
        gross_margin=0.25, operating_margin=0.08, forward_pe=40.0,
        fifty_two_week_high=price * 1.2, analyst_target=price, free_cash_flow=1.0,
        financial_currency="USD", trading_currency="USD",
        revenue_series=(100.0, 99.0, 98.0), ebit_series=(8.0, 7.0, 6.0),
        tax_rate_series=(0.20, 0.20, 0.20), operating_income_series=(8.0, 7.0, 6.0),
        eps_series=(2.0, 1.9, 1.8), fcf_series=(5.0, 3.0, 1.0),
        diluted_shares_series=(100.0, 101.0, 102.0), invested_capital_series=(80.0, 90.0, 100.0),
    )


class FakeProvider:
    def __init__(self, data: dict[str, Fundamentals]) -> None:
        self._data = data

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        return self._data[ticker]

    def exchange_rate(self, base: str, quote: str) -> float:
        return 1.0


def test_screen_ranks_by_composite_and_excludes_owned():
    provider = FakeProvider(
        {
            "V": fundamentals("strong", 280.0),
            "NVDA": fundamentals("weak", 120.0),
            "MA": fundamentals("strong", 480.0),
        }
    )

    results = screen_candidates(provider, tickers=["V", "NVDA", "MA"], owned=["MA"])

    tickers = [candidate.ticker for candidate in results]
    assert "MA" not in tickers
    assert tickers == ["V", "NVDA"]
    assert isinstance(results[0], CandidateAnalysis)
    assert results[0].score.composite_score > results[1].score.composite_score
    assert results[0].theme == "Payments"


def test_screen_empty_when_all_owned():
    provider = FakeProvider({"V": fundamentals("strong", 280.0)})
    assert screen_candidates(provider, tickers=["V"], owned=["V"]) == []


def test_candidate_universe_includes_requested_adr_reit_and_energy_names():
    assert {"AAPL", "NVDA", "V", "LVMUY", "VICI", "EQNR", "ENB"}.issubset(
        CANDIDATE_UNIVERSE
    )


def test_candidate_universe_includes_legacy_quality_salvage_names():
    assert {"CME", "WM", "WCN", "TXN", "SHW", "ITW", "APD", "EW"}.issubset(
        CANDIDATE_UNIVERSE
    )
