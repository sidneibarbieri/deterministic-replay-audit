"""Fundamental analysis data models.

Models for Moat and Compounding analysis with long-term historical data.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Company(SQLModel, table=True):
    """Company master data.

    Core information for companies being analyzed.
    """

    __tablename__ = "companies"

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True, unique=True)
    name: str
    sector: str | None = None
    industry: str | None = None
    cik: str | None = None  # SEC Central Index Key
    isin: str | None = None
    currency: str = Field(default="USD")
    country: str = Field(default="US")
    market_cap: Decimal | None = None
    shares_outstanding: Decimal | None = None
    created_at: date = Field(default_factory=date.today)
    updated_at: date = Field(default_factory=date.today)

class FinancialStatement(SQLModel, table=True):
    """Quarterly and annual financial statements.

    Raw data from 10-K and 10-Q filings.
    """

    __tablename__ = "financial_statements"

    __table_args__ = (UniqueConstraint("ticker", "filing_type", "fiscal_year", "fiscal_quarter"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    filing_type: str  # "10-K" or "10-Q"
    fiscal_year: int
    fiscal_quarter: int | None = None  # 1-4 for quarterly, null for annual
    filing_date: date
    period_end_date: date

    # Income Statement
    revenue: Decimal = Field(default=Decimal("0"))
    gross_profit: Decimal = Field(default=Decimal("0"))
    operating_income: Decimal = Field(default=Decimal("0"))
    net_income: Decimal = Field(default=Decimal("0"))
    eps: Decimal | None = None
    eps_diluted: Decimal | None = None

    # Balance Sheet
    total_assets: Decimal = Field(default=Decimal("0"))
    total_liabilities: Decimal = Field(default=Decimal("0"))
    shareholders_equity: Decimal = Field(default=Decimal("0"))
    total_debt: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    property_plant_equipment: Decimal | None = None
    goodwill: Decimal | None = None
    intangible_assets: Decimal | None = None

    # Cash Flow
    operating_cash_flow: Decimal = Field(default=Decimal("0"))
    free_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = None
    share_buybacks: Decimal | None = None  # Negative = buybacks
    dividends_paid: Decimal | None = None  # Negative = dividends paid

    # Additional
    research_and_development: Decimal | None = None
    selling_general_administrative: Decimal | None = None

    created_at: date = Field(default_factory=date.today)

class MoatMetric(SQLModel, table=True):
    """Moat (competitive advantage) metrics.

    Calculated metrics for economic moat analysis.
    All percentages stored as decimals (e.g., 0.15 for 15%).
    """

    __tablename__ = "moat_metrics"

    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    fiscal_year: int
    fiscal_quarter: int | None = None

    # Capital Efficiency (Moat indicators)
    roic: Decimal | None = None  # Return on Invested Capital
    roce: Decimal | None = None  # Return on Capital Employed
    roe: Decimal | None = None  # Return on Equity
    roa: Decimal | None = None  # Return on Assets

    # Margin Stability (Pricing Power)
    gross_margin: Decimal | None = None
    operating_margin: Decimal | None = None
    net_margin: Decimal | None = None
    fcf_margin: Decimal | None = None  # FCF / Revenue

    # Capital Structure
    debt_to_equity: Decimal | None = None
    debt_to_assets: Decimal | None = None
    equity_to_assets: Decimal | None = None

    # Efficiency
    asset_turnover: Decimal | None = None  # Revenue / Total Assets
    inventory_turnover: Decimal | None = None
    receivables_turnover: Decimal | None = None

    # Intangibles
    rd_to_revenue: Decimal | None = None  # R&D intensity
    intangible_to_assets: Decimal | None = None

    created_at: date = Field(default_factory=date.today)

class CompoundingMetric(SQLModel, table=True):
    """Compounding growth metrics.

    Long-term growth and shareholder return metrics.
    All CAGR values stored as decimals.
    """

    __tablename__ = "compounding_metrics"

    __table_args__ = (UniqueConstraint("ticker", "period_years", "end_year"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    period_years: int  # 5, 10, 15, 20 years
    end_year: int

    # Revenue Growth
    revenue_cagr: Decimal | None = None
    gross_profit_cagr: Decimal | None = None
    operating_income_cagr: Decimal | None = None
    net_income_cagr: Decimal | None = None

    # Cash Flow Growth
    operating_cash_flow_cagr: Decimal | None = None
    free_cash_flow_cagr: Decimal | None = None

    # Per-Share Metrics
    eps_cagr: Decimal | None = None
    book_value_per_share_cagr: Decimal | None = None

    # Shareholder Returns
    shares_outstanding_change: Decimal | None = None  # % change
    dividend_cagr: Decimal | None = None
    total_shareholder_return: Decimal | None = None

    # Consistency Score (0-1)
    # Measures how many years growth was positive
    revenue_consistency: Decimal | None = None
    fcf_consistency: Decimal | None = None

    created_at: date = Field(default_factory=date.today)

class StockPrice(SQLModel, table=True):
    """Historical stock prices for total return calculations.

    End-of-day prices for CAGR calculations.
    """

    __tablename__ = "stock_prices"

    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    date: date = Field(index=True)
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    close_price: Decimal
    adjusted_close: Decimal | None = None
    volume: int | None = None

class Dividend(SQLModel, table=True):
    """Dividend history.

    For dividend CAGR and yield calculations.
    """

    __tablename__ = "dividends"

    __table_args__ = (UniqueConstraint("ticker", "ex_date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    ex_date: date
    payment_date: date | None = None
    amount: Decimal
    dividend_type: str = Field(default="regular")  # regular, special, stock

class SECFiling(SQLModel, table=True):
    """SEC EDGAR filings metadata.

    References to 10-K, 10-Q, 8-K filings.
    """

    __tablename__ = "sec_filings"

    __table_args__ = (UniqueConstraint("cik", "accession_number"),)

    id: int | None = Field(default=None, primary_key=True)
    cik: str = Field(index=True)
    ticker: str = Field(index=True)
    filing_type: str  # 10-K, 10-Q, 8-K, etc.
    filing_date: date
    period_end_date: date | None = None
    accession_number: str  # SEC unique identifier
    form_url: str | None = None
    xbrl_url: str | None = None
    text_url: str | None = None
    size_bytes: int | None = None

    # For XBRL parsing
    processed: bool = Field(default=False)
    processed_at: date | None = None
