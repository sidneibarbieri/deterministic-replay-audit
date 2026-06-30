"""Unit tests for fundamentals provider selection and parsing."""

from arenawealth.analytics.fundamentals import (
    FinnhubFundamentalsProvider,
    FMPFundamentalsProvider,
    YahooFundamentalsProvider,
    build_fundamentals_provider,
)
from arenawealth.config.settings import ProviderKeys


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, endpoint: str, params: dict[str, object]) -> FakeResponse:
        self.calls.append(endpoint)
        payloads = {
            "/quote/MSFT": [{"price": 420.0, "marketCap": 3_000_000_000_000, "pe": 31.0}],
            "/profile/MSFT": [{"currency": "USD", "mktCap": 3_000_000_000_000}],
            "/income-statement/MSFT": [
                {
                    "revenue": 120.0,
                    "ebitda": 40.0,
                    "operatingIncome": 35.0,
                    "incomeBeforeTax": 32.0,
                    "incomeTaxExpense": 6.4,
                    "epsdiluted": 10.0,
                    "weightedAverageShsOutDil": 100.0,
                },
                {
                    "revenue": 100.0,
                    "ebitda": 30.0,
                    "operatingIncome": 25.0,
                    "incomeBeforeTax": 22.0,
                    "incomeTaxExpense": 4.4,
                    "epsdiluted": 8.0,
                    "weightedAverageShsOutDil": 105.0,
                },
            ],
            "/cash-flow-statement/MSFT": [
                {"freeCashFlow": 22.0},
                {"freeCashFlow": 18.0},
            ],
            "/balance-sheet-statement/MSFT": [
                {
                    "totalDebt": 20.0,
                    "totalStockholdersEquity": 80.0,
                    "cashAndCashEquivalents": 10.0,
                },
                {
                    "totalDebt": 18.0,
                    "totalStockholdersEquity": 70.0,
                    "cashAndCashEquivalents": 8.0,
                },
            ],
            "/key-metrics/MSFT": [
                {
                    "roe": 0.30,
                    "grossProfitMargin": 0.65,
                    "operatingProfitMargin": 0.42,
                }
            ],
        }
        return FakeResponse(payloads[endpoint])


class FakeFinnhubClient:
    def get(self, endpoint: str, params: dict[str, object]) -> FakeResponse:
        if endpoint == "/quote":
            return FakeResponse({"c": 421.0})
        if endpoint == "/stock/metric":
            return FakeResponse(
                {
                    "metric": {
                        "roeTTM": 33.0,
                        "grossMarginTTM": 68.0,
                        "operatingMarginTTM": 46.0,
                        "forwardPE": 22.0,
                        "pfcfShareTTM": 42.0,
                        "revenueShareGrowth5Y": 15.0,
                        "epsGrowth5Y": 18.0,
                        "cashFlowPerShareTTM": 12.0,
                        "bookValuePerShareQuarterly": 55.0,
                    }
                }
            )
        raise AssertionError(f"unexpected endpoint {endpoint}")


def test_factory_uses_yahoo_without_fmp_key():
    provider = build_fundamentals_provider(ProviderKeys())

    assert isinstance(provider, YahooFundamentalsProvider)


def test_factory_uses_fmp_when_key_is_available():
    provider = build_fundamentals_provider(ProviderKeys(fmp_api_key="test-key"))

    assert isinstance(provider, FMPFundamentalsProvider)
    provider.close()


def test_factory_prefers_yahoo_over_finnhub_for_statements():
    provider = build_fundamentals_provider(ProviderKeys(finnhub_api_key="test-key"))

    assert isinstance(provider, YahooFundamentalsProvider)


def test_fmp_provider_maps_structured_payloads():
    provider = FMPFundamentalsProvider("test-key", client=FakeClient())

    fundamentals = provider.get_fundamentals("MSFT")

    assert fundamentals.live_price == 420.0
    assert fundamentals.market_cap == 3_000_000_000_000
    assert fundamentals.return_on_equity == 0.30
    assert fundamentals.gross_margin == 0.65
    assert fundamentals.operating_margin == 0.42
    assert fundamentals.forward_pe == 31.0
    assert fundamentals.free_cash_flow == 22.0
    assert fundamentals.revenue_series == (100.0, 120.0)
    assert fundamentals.tax_rate_series == (0.20, 0.20)
    assert fundamentals.invested_capital_series == (80.0, 90.0)


def test_finnhub_provider_maps_metric_payloads():
    provider = FinnhubFundamentalsProvider("test-key", client=FakeFinnhubClient())

    fundamentals = provider.get_fundamentals("MSFT")

    assert fundamentals.live_price == 421.0
    assert fundamentals.return_on_equity == 0.33
    assert fundamentals.gross_margin == 0.68
    assert fundamentals.operating_margin == 0.46
    assert fundamentals.forward_pe == 22.0
    assert fundamentals.free_cash_flow == 1 / 42.0
    assert len(fundamentals.revenue_series) == 6
    assert fundamentals.revenue_series[-1] == 100.0
