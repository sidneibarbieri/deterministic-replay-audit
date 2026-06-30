"""Position repository implementation.

Handles all position-related database operations.
"""

from decimal import Decimal

from sqlmodel import Session, select

from arenawealth.models.database import Position


class PositionRepository:
    """Repository for Position entity operations."""

    def __init__(self, session: Session) -> None:
        """Initialize with database session.

        Args:
            session: SQLModel session for database operations.
        """
        self._session = session

    def get_by_id(self, position_id: int) -> Position | None:
        """Retrieve position by ID.

        Args:
            position_id: Position identifier.

        Returns:
            Position instance or None if not found.
        """
        statement = select(Position).where(Position.id == position_id)
        return self._session.exec(statement).first()

    def get_by_portfolio(self, portfolio_id: int) -> list[Position]:
        """Retrieve all positions for a portfolio.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            List of position entities.
        """
        statement = (
            select(Position)
            .where(Position.portfolio_id == portfolio_id)
            .order_by(Position.ticker)
        )
        return list(self._session.exec(statement).all())

    def get_by_ticker(self, portfolio_id: int, ticker: str) -> Position | None:
        """Retrieve position by ticker within a portfolio.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.

        Returns:
            Position instance or None if not found.
        """
        statement = (
            select(Position)
            .where(Position.portfolio_id == portfolio_id)
            .where(Position.ticker == ticker.upper())
        )
        return self._session.exec(statement).first()

    def create(
        self,
        portfolio_id: int,
        ticker: str,
        name: str,
        shares: Decimal,
        average_cost_basis: Decimal,
        current_price: Decimal | None = None,
        isin: str | None = None,
    ) -> Position:
        """Create new position.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.
            name: Security name.
            shares: Number of shares.
            average_cost_basis: Average cost per share.
            current_price: Current market price (defaults to cost basis).
            isin: ISIN code (optional).

        Returns:
            Created position entity.
        """
        position = Position(
            portfolio_id=portfolio_id,
            ticker=ticker.upper(),
            name=name,
            shares=shares,
            average_cost_basis=average_cost_basis,
            current_price=current_price or average_cost_basis,
            isin=isin,
        )
        self._session.add(position)
        self._session.commit()
        self._session.refresh(position)
        return position

    def update_price(self, position_id: int, new_price: Decimal) -> Position | None:
        """Update current price for a position.

        Args:
            position_id: Position identifier.
            new_price: New market price.

        Returns:
            Updated position or None if not found.
        """
        position = self.get_by_id(position_id)
        if position is None:
            return None

        position.current_price = new_price
        self._session.add(position)
        self._session.commit()
        self._session.refresh(position)
        return position

    def add_shares(
        self,
        position_id: int,
        additional_shares: Decimal,
        purchase_price: Decimal,
    ) -> Position | None:
        """Add shares to existing position (averages cost basis).

        Args:
            position_id: Position identifier.
            additional_shares: Number of shares to add.
            purchase_price: Price per share for new purchase.

        Returns:
            Updated position or None if not found.
        """
        position = self.get_by_id(position_id)
        if position is None:
            return None

        current_shares = position.shares
        current_cost = position.average_cost_basis

        total_shares = current_shares + additional_shares
        total_cost = (current_shares * current_cost) + (additional_shares * purchase_price)

        position.shares = total_shares
        position.average_cost_basis = total_cost / total_shares

        self._session.add(position)
        self._session.commit()
        self._session.refresh(position)
        return position

    def remove_shares(
        self,
        position_id: int,
        shares_to_remove: Decimal,
    ) -> Position | None:
        """Remove shares from position (partial sell).

        Args:
            position_id: Position identifier.
            shares_to_remove: Number of shares to remove.

        Returns:
            Updated position or None if not found/insufficient shares.
        """
        position = self.get_by_id(position_id)
        if position is None:
            return None

        if position.shares < shares_to_remove:
            return None

        position.shares -= shares_to_remove

        if position.shares == 0:
            self._session.delete(position)
            self._session.commit()
            return None

        self._session.add(position)
        self._session.commit()
        self._session.refresh(position)
        return position

    def delete(self, position_id: int) -> bool:
        """Delete position.

        Args:
            position_id: Position identifier.

        Returns:
            True if deleted, False if not found.
        """
        position = self.get_by_id(position_id)
        if position is None:
            return False

        self._session.delete(position)
        self._session.commit()
        return True

    def exists(self, portfolio_id: int, ticker: str) -> bool:
        """Check if position exists for ticker in portfolio.

        Args:
            portfolio_id: Portfolio identifier.
            ticker: Security ticker symbol.

        Returns:
            True if exists, False otherwise.
        """
        statement = (
            select(Position.id)
            .where(Position.portfolio_id == portfolio_id)
            .where(Position.ticker == ticker.upper())
        )
        result = self._session.exec(statement).first()
        return result is not None

    def get_total_value(self, portfolio_id: int) -> Decimal:
        """Calculate total market value for portfolio.

        Args:
            portfolio_id: Portfolio identifier.

        Returns:
            Total market value of all positions.
        """
        positions = self.get_by_portfolio(portfolio_id)
        return sum(p.shares * p.current_price for p in positions)
