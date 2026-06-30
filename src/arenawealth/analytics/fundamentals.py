"""Fundamentals providers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

import httpx
import yfinance

from arenawealth.analytics.models import Fundamentals, Holding
from arenawealth.config.settings import ProviderKeys, load_provider_keys


class FundamentalsProvider(Protocol):
    """Contract for any source of company fundamentals and FX rates."""

    def get_fundamentals(self, ticker: str) -> Fundamentals: ...

    def exchange_rate(self, base: str, quote: str) -> float: ...


class YahooFundamentalsProvider:
    """Fundamentals from Yahoo Finance. Network errors propagate to the caller."""

    def __init__(self) -> None:
        self._exchange_rates: dict[str, float] = {}

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        handle = yfinance.Ticker(ticker)
        info = handle.info
        income = handle.income_stmt
        cash_flow = handle.cashflow
        balance = handle.balance_sheet
        return Fundamentals(
            live_price=float(handle.fast_info.last_price),
            market_cap=info.get("marketCap"),
            return_on_equity=info.get("returnOnEquity"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            forward_pe=info.get("forwardPE"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            analyst_target=info.get("targetMeanPrice"),
            free_cash_flow=info.get("freeCashflow"),
            financial_currency=info.get("financialCurrency"),
            trading_currency=info.get("currency"),
            revenue_series=statement_row(income, "Total Revenue", "Operating Revenue"),
            ebit_series=statement_row(income, "EBIT", "Operating Income"),
            tax_rate_series=statement_row(income, "Tax Rate For Calcs"),
            operating_income_series=statement_row(
                income, "Operating Income", "Total Operating Income As Reported"
            ),
            eps_series=statement_row(income, "Diluted EPS", "Basic EPS"),
            fcf_series=statement_row(cash_flow, "Free Cash Flow"),
            diluted_shares_series=statement_row(
                income, "Diluted Average Shares", "Basic Average Shares"
            ),
            invested_capital_series=statement_row(balance, "Invested Capital"),
        )

    def exchange_rate(self, base: str, quote: str) -> float:
        pair = f"{base}{quote}=X"
        if pair not in self._exchange_rates:
            self._exchange_rates[pair] = float(yfinance.Ticker(pair).fast_info.last_price)
        return self._exchange_rates[pair]


class DemoFundamentalsProvider:
    """Deterministic fundamentals for reviewer runs without network access."""

    def __init__(self, holdings: Sequence[Holding]) -> None:
        self._holdings = {holding.ticker: holding for holding in holdings}

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        holding = self._holdings[ticker]
        ordinal = sum(ord(character) for character in ticker)
        growth = 0.01 * (ordinal % 7)
        live_price = holding.broker_price * (1.0 + (ordinal % 5 - 2) / 100)
        return Fundamentals(
            live_price=live_price,
            market_cap=250_000_000_000.0 + ordinal * 1_000_000.0,
            return_on_equity=0.14 + (ordinal % 8) / 100,
            gross_margin=0.45 + (ordinal % 12) / 100,
            operating_margin=0.20 + (ordinal % 7) / 100,
            forward_pe=18.0 + (ordinal % 18),
            fifty_two_week_high=live_price * 1.2,
            analyst_target=live_price * 1.1,
            free_cash_flow=12_000_000_000.0 + ordinal * 10_000_000.0,
            financial_currency="USD",
            trading_currency="USD",
            revenue_series=normalized_series(growth, latest=100.0),
            ebit_series=normalized_series(growth, latest=22.0),
            tax_rate_series=(0.21, 0.21, 0.21, 0.21, 0.21, 0.21),
            operating_income_series=normalized_series(growth, latest=20.0),
            eps_series=normalized_series(growth, latest=5.0),
            fcf_series=normalized_series(growth, latest=8.0),
            diluted_shares_series=(100.0, 99.6, 99.2, 98.8, 98.4, 98.0),
            invested_capital_series=normalized_series(0.01, latest=94.0),
        )

    def exchange_rate(self, base: str, quote: str) -> float:
        return 1.0


class FinnhubFundamentalsProvider:
    """Fundamentals from Finnhub metrics and quote endpoints."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is required for FinnhubFundamentalsProvider")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30.0, base_url=self.BASE_URL)
        self._exchange_rates: dict[str, float] = {}

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        quote = self._get("/quote", symbol=ticker)
        metric = self._get("/stock/metric", symbol=ticker, metric="all").get("metric", {})
        if not isinstance(metric, dict):
            raise ValueError(f"Finnhub returned invalid metric payload for {ticker}")

        pfcf = optional_float(metric.get("pfcfShareTTM") or metric.get("pfcfShareAnnual"))
        free_cash_flow = (1 / pfcf) if pfcf and pfcf > 0 else None
        market_cap = 1.0 if free_cash_flow is not None else optional_float(
            metric.get("marketCapitalization")
        )
        revenue_growth = percent_metric(metric, "revenueShareGrowth5Y", "revenueGrowth5Y")
        eps_growth = percent_metric(metric, "epsGrowth5Y", "epsGrowth3Y")
        cash_growth = percent_metric(metric, "cashFlowPerShareGrowth5Y", "revenueShareGrowth5Y")

        return Fundamentals(
            live_price=require_float(quote.get("c"), f"{ticker} quote price"),
            market_cap=market_cap,
            return_on_equity=percent_metric(metric, "roeTTM", "roe5Y"),
            gross_margin=percent_metric(metric, "grossMarginTTM", "grossMargin5Y"),
            operating_margin=percent_metric(metric, "operatingMarginTTM", "operatingMargin5Y"),
            forward_pe=optional_float(metric.get("forwardPE") or metric.get("peTTM")),
            fifty_two_week_high=None,
            analyst_target=None,
            free_cash_flow=free_cash_flow,
            financial_currency="USD",
            trading_currency="USD",
            revenue_series=normalized_series(
                revenue_growth, optional_float(metric.get("revenuePerShareTTM")) or 100.0
            ),
            ebit_series=normalized_series(
                revenue_growth, optional_float(metric.get("ebitdPerShareTTM")) or 20.0
            ),
            tax_rate_series=(0.21, 0.21, 0.21, 0.21, 0.21, 0.21),
            operating_income_series=normalized_series(
                revenue_growth, optional_float(metric.get("ebitdPerShareTTM")) or 20.0
            ),
            eps_series=normalized_series(
                eps_growth, optional_float(metric.get("epsNormalizedAnnual")) or 5.0
            ),
            fcf_series=normalized_series(
                cash_growth, optional_float(metric.get("cashFlowPerShareTTM")) or 5.0
            ),
            diluted_shares_series=stable_share_series(),
            invested_capital_series=normalized_series(
                0.03, optional_float(metric.get("bookValuePerShareQuarterly")) or 100.0
            ),
        )

    def exchange_rate(self, base: str, quote: str) -> float:
        pair = f"{base}{quote}=X"
        if pair not in self._exchange_rates:
            self._exchange_rates[pair] = float(yfinance.Ticker(pair).fast_info.last_price)
        return self._exchange_rates[pair]

    def close(self) -> None:
        self._client.close()

    def _get(self, endpoint: str, **params: str) -> dict[str, object]:
        response = self._client.get(endpoint, params={**params, "token": self._api_key})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Finnhub returned non-dict payload for {endpoint}")
        return payload


class FMPFundamentalsProvider:
    """Fundamentals from Financial Modeling Prep.

    FMP is preferred when an API key is available because the statement history
    is structured and more reproducible than scraped market pages.
    """

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ValueError("FMP_API_KEY is required for FMPFundamentalsProvider")
        self._client = client or httpx.Client(timeout=60.0, base_url=self.BASE_URL)
        self._api_key = api_key
        self._exchange_rates: dict[str, float] = {}

    def get_fundamentals(self, ticker: str) -> Fundamentals:
        quote = first_item(self._get(f"/quote/{ticker}"))
        profile = first_item(self._get(f"/profile/{ticker}"))
        income = self._get(f"/income-statement/{ticker}", limit=10)
        cash_flow = self._get(f"/cash-flow-statement/{ticker}", limit=10)
        balance = self._get(f"/balance-sheet-statement/{ticker}", limit=10)
        metrics = self._get(f"/key-metrics/{ticker}", limit=10)
        latest_metrics = first_item(metrics)
        market_cap = optional_float(quote.get("marketCap") or profile.get("mktCap"))

        return Fundamentals(
            live_price=require_float(quote.get("price"), f"{ticker} quote price"),
            market_cap=market_cap,
            return_on_equity=optional_float(latest_metrics.get("roe")),
            gross_margin=optional_float(latest_metrics.get("grossProfitMargin")),
            operating_margin=optional_float(latest_metrics.get("operatingProfitMargin")),
            forward_pe=optional_float(quote.get("pe")),
            fifty_two_week_high=optional_float(quote.get("yearHigh")),
            analyst_target=None,
            free_cash_flow=latest_field(cash_flow, "freeCashFlow"),
            financial_currency=profile.get("currency") or profile.get("reportedCurrency"),
            trading_currency=profile.get("currency"),
            revenue_series=field_series(income, "revenue"),
            ebit_series=field_series(income, "ebitda", "operatingIncome"),
            tax_rate_series=tax_rate_series(income),
            operating_income_series=field_series(income, "operatingIncome"),
            eps_series=field_series(income, "epsdiluted", "eps"),
            fcf_series=field_series(cash_flow, "freeCashFlow"),
            diluted_shares_series=field_series(
                income, "weightedAverageShsOutDil", "weightedAverageShsOut"
            ),
            invested_capital_series=invested_capital_series(balance),
        )

    def exchange_rate(self, base: str, quote: str) -> float:
        pair = f"{base}{quote}=X"
        if pair not in self._exchange_rates:
            self._exchange_rates[pair] = float(yfinance.Ticker(pair).fast_info.last_price)
        return self._exchange_rates[pair]

    def close(self) -> None:
        self._client.close()

    def _get(self, endpoint: str, **params: int | str) -> list[dict[str, object]]:
        response = self._client.get(endpoint, params={**params, "apikey": self._api_key})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"FMP returned non-list payload for {endpoint}")
        return payload


def build_fundamentals_provider(keys: ProviderKeys | None = None) -> FundamentalsProvider:
    loaded_keys = keys or load_provider_keys()
    if loaded_keys.fmp_api_key:
        return FMPFundamentalsProvider(loaded_keys.fmp_api_key)
    # Yahoo serves real multi-year statements. Finnhub's free tier does not, so it
    # would approximate them and distort the moat scores; prefer Yahoo for accuracy.
    return YahooFundamentalsProvider()


def statement_row(statement, *labels: str) -> tuple[float, ...]:
    """Return one statement row ordered oldest to newest, skipping blanks."""
    if statement is None or statement.empty:
        return ()
    for label in labels:
        if label in statement.index:
            newest_first = statement.loc[label].tolist()
            return tuple(float(value) for value in reversed(newest_first) if is_number(value))
    return ()


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def first_item(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {}
    return rows[0]


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def require_float(value: object, label: str) -> float:
    parsed = optional_float(value)
    if parsed is None:
        raise ValueError(f"Missing numeric value: {label}")
    return parsed


def percent_metric(metric: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        value = optional_float(metric.get(key))
        if value is not None:
            return value / 100
    return None


def normalized_series(growth: float | None, latest: float, periods: int = 6) -> tuple[float, ...]:
    if periods < 2 or latest <= 0:
        return ()
    rate = growth or 0.0
    if rate <= -0.95:
        return ()
    return tuple(latest / ((1 + rate) ** index) for index in reversed(range(periods)))


def stable_share_series(periods: int = 6) -> tuple[float, ...]:
    return tuple(100.0 - index * 0.4 for index in range(periods))


def field_series(rows: list[dict[str, object]], *fields: str) -> tuple[float, ...]:
    values = []
    for row in reversed(rows):
        for field in fields:
            value = optional_float(row.get(field))
            if value is not None:
                values.append(value)
                break
    return tuple(values)


def latest_field(rows: list[dict[str, object]], *fields: str) -> float | None:
    for row in rows:
        for field in fields:
            value = optional_float(row.get(field))
            if value is not None:
                return value
    return None


def tax_rate_series(rows: list[dict[str, object]]) -> tuple[float, ...]:
    values = []
    for row in reversed(rows):
        income_before_tax = optional_float(row.get("incomeBeforeTax"))
        tax_expense = optional_float(row.get("incomeTaxExpense"))
        if income_before_tax and tax_expense is not None:
            values.append(tax_expense / income_before_tax)
    return tuple(values)


def invested_capital_series(rows: list[dict[str, object]]) -> tuple[float, ...]:
    values = []
    for row in reversed(rows):
        explicit = optional_float(row.get("investedCapital"))
        if explicit is not None:
            values.append(explicit)
            continue
        debt = optional_float(row.get("totalDebt")) or 0.0
        equity = optional_float(row.get("totalStockholdersEquity")) or 0.0
        cash = optional_float(row.get("cashAndCashEquivalents")) or 0.0
        invested = debt + equity - cash
        if invested > 0:
            values.append(invested)
    return tuple(values)
