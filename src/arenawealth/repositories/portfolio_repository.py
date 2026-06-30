"""Portfolio repository implementation.

Follows Repository Pattern for data access abstraction.
All methods use explicit error propagation (no try-except masking).
"""

from decimal import Decimal

from sqlmodel import Session, select

from arenawealth.models.database import Portfolio, Position


class PortfolioRepository:
    """Repository for Portfolio entity operations."""

    def __init__(self, session: Session) -> None:
        """Initialize with database session.

        Args:
            session: SQLModel session for database operations.
        """
        self._session = session

    def get_by_id(self, portfolio_id: int) -> Portfolio | None:
        """Retrieve portfolio by ID.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            Portfolio instance or None if not found.
        """
        statement = select(Portfolio).where(Portfolio.id == portfolio_id)
        return self._session.exec(statement).first()

    def get_all(self) -> list[Portfolio]:
        """Retrieve all portfolios.

        Returns:
            List of all portfolio entities.
        """
        statement = select(Portfolio)
        return list(self._session.exec(statement).all())

    def create(
        self, name: str, currency: str = "USD", initial_cash: Decimal = Decimal("0")
    ) -> Portfolio:
        """Create new portfolio.

        Args:
            name: Portfolio name.
            currency: Currency code (default: USD).
            initial_cash: Initial cash balance.

        Returns:
            Created portfolio entity.
        """
        portfolio = Portfolio(
            name=name,
            currency=currency,
            available_cash=initial_cash,
            total_market_value=Decimal("0"),
            total_cost_basis=Decimal("0"),
        )
        self._session.add(portfolio)
        self._session.commit()
        self._session.refresh(portfolio)
        return portfolio

    def update(self, portfolio_id: int, **kwargs) -> Portfolio | None:
        """Update portfolio fields.

        Args:
            portfolio_id: Portfolio identifier.
            **kwargs: Fields to update (name, description, available_cash).

        Returns:
            Updated portfolio or None if not found.
        """
        portfolio = self.get_by_id(portfolio_id)
        if portfolio is None:
            return None

        allowed_fields = {"name", "description", "available_cash"}
        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(portfolio, key, value)

        self._session.add(portfolio)
        self._session.commit()
        self._session.refresh(portfolio)
        return portfolio

    def recalculate_totals(self, portfolio_id: int) -> Portfolio | None:
        """Recalculate portfolio totals from positions.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            Updated portfolio or None if not found.
        """
        portfolio = self.get_by_id(portfolio_id)
        if portfolio is None:
            return None

        statement = select(Position).where(Position.portfolio_id == portfolio_id)
        positions = self._session.exec(statement).all()

        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")

        for position in positions:
            total_market_value += position.shares * position.current_price
            total_cost_basis += position.shares * position.average_cost_basis

        portfolio.total_market_value = total_market_value
        portfolio.total_cost_basis = total_cost_basis

        self._session.add(portfolio)
        self._session.commit()
        self._session.refresh(portfolio)
        return portfolio

    def delete(self, portfolio_id: int) -> bool:
        """Delete portfolio and all related data.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            True if deleted, False if not found.
        """
        portfolio = self.get_by_id(portfolio_id)
        if portfolio is None:
            return False

        self._session.delete(portfolio)
        self._session.commit()
        return True

    def exists(self, portfolio_id: int) -> bool:
        """Check if portfolio exists.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            True if exists, False otherwise.
        """
        statement = select(Portfolio.id).where(Portfolio.id == portfolio_id)
        result = self._session.exec(statement).first()
        return result is not None
