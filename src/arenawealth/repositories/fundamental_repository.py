"""Repository for fundamental analysis data.

Handles persistence of Moat and Compounding metrics.
"""

from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from arenawealth.models.fundamentals import (
    Company,
    CompoundingMetric,
    FinancialStatement,
    MoatMetric,
)


class FundamentalRepository:
    """Data access for fundamental analysis.

    Encapsulates queries for Moat/Compounding metrics.
    """

    def __init__(self, session: Session) -> None:
        """Initialize with database session.

        Args:
            session: SQLModel session.
        """
        self._session = session

    def save_company(self, company: Company) -> Company:
        """Persist company data.

        Args:
            company: Company instance to save.

        Returns:
            Saved company with ID.
        """
        self._session.add(company)
        self._session.commit()
        self._session.refresh(company)
        return company

    def get_company(self, ticker: str) -> Company | None:
        """Fetch company by ticker.

        Args:
            ticker: Stock symbol.

        Returns:
            Company or None if not found.
        """
        statement = select(Company).where(Company.ticker == ticker.upper())
        return self._session.exec(statement).first()

    def save_financial_statement(self, statement: FinancialStatement) -> FinancialStatement:
        """Persist financial statement.

        Args:
            statement: Financial statement to save.

        Returns:
            Saved statement.
        """
        self._session.add(statement)
        self._session.commit()
        self._session.refresh(statement)
        return statement

    def get_financial_statements(
        self, ticker: str, filing_type: str | None = None, limit: int = 20
    ) -> list[FinancialStatement]:
        """Fetch financial statements.

        Args:
            ticker: Stock symbol.
            filing_type: Filter by "10-K" or "10-Q".
            limit: Maximum records.

        Returns:
            List of statements ordered by date desc.
        """
        statement = select(FinancialStatement).where(
            FinancialStatement.ticker == ticker.upper()
        )

        if filing_type:
            statement = statement.where(FinancialStatement.filing_type == filing_type)

        statement = statement.order_by(
            FinancialStatement.fiscal_year.desc(),
            FinancialStatement.fiscal_quarter.desc().nulls_last(),
        ).limit(limit)

        return list(self._session.exec(statement))

    def save_moat_metric(self, metric: MoatMetric) -> MoatMetric:
        """Persist Moat metric.

        Args:
            metric: MoatMetric to save.

        Returns:
            Saved metric.
        """
        self._session.add(metric)
        self._session.commit()
        self._session.refresh(metric)
        return metric

    def get_moat_metrics(
        self, ticker: str, years: int = 10
    ) -> list[MoatMetric]:
        """Fetch Moat metrics for analysis.

        Args:
            ticker: Stock symbol.
            years: Number of years to fetch.

        Returns:
            List of Moat metrics ordered by year desc.
        """
        statement = (
            select(MoatMetric)
            .where(MoatMetric.ticker == ticker.upper())
            .where(MoatMetric.fiscal_quarter.is_(None))  # Annual only
            .order_by(MoatMetric.fiscal_year.desc())
            .limit(years)
        )

        return list(self._session.exec(statement))

    def calculate_average_roic(self, ticker: str, years: int = 10) -> Decimal:
        """Calculate average ROIC from stored metrics.

        Args:
            ticker: Stock symbol.
            years: Analysis period.

        Returns:
            Average ROIC or 0 if no data.
        """
        metrics = self.get_moat_metrics(ticker, years)
        roic_values = [m.roic for m in metrics if m.roic]

        if not roic_values:
            return Decimal("0")

        return sum(roic_values) / len(roic_values)

    def save_compounding_metric(self, metric: CompoundingMetric) -> CompoundingMetric:
        """Persist Compounding metric.

        Args:
            metric: CompoundingMetric to save.

        Returns:
            Saved metric.
        """
        self._session.add(metric)
        self._session.commit()
        self._session.refresh(metric)
        return metric

    def get_compounding_metrics(
        self, ticker: str, period_years: int = 10
    ) -> list[CompoundingMetric]:
        """Fetch Compounding metrics.

        Args:
            ticker: Stock symbol.
            period_years: CAGR period (5, 10, 15, 20).

        Returns:
            List of compounding metrics.
        """
        statement = (
            select(CompoundingMetric)
            .where(CompoundingMetric.ticker == ticker.upper())
            .where(CompoundingMetric.period_years == period_years)
            .order_by(CompoundingMetric.end_year.desc())
        )

        return list(self._session.exec(statement))

    def get_latest_compounding_score(
        self, ticker: str, period_years: int = 10
    ) -> dict[str, Any] | None:
        """Get latest compounding summary.

        Args:
            ticker: Stock symbol.
            period_years: Analysis period.

        Returns:
            Dict with CAGR values or None.
        """
        metrics = self.get_compounding_metrics(ticker, period_years)
        if not metrics:
            return None

        latest = metrics[0]
        return {
            "ticker": ticker,
            "period_years": period_years,
            "revenue_cagr": latest.revenue_cagr,
            "fcf_cagr": latest.fcf_cagr,
            "eps_cagr": latest.eps_cagr,
            "shares_change": latest.shares_outstanding_change,
        }
