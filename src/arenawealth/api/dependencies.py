"""API dependencies - dependency injection for FastAPI.

Provides database sessions and repositories to endpoints.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from arenawealth.models.database import get_session
from arenawealth.repositories.portfolio_repository import PortfolioRepository
from arenawealth.repositories.position_repository import PositionRepository
from arenawealth.repositories.transaction_repository import TransactionRepository
from arenawealth.services.portfolio_service import PortfolioService


def get_db_session() -> Generator[Session, None, None]:
    """Yield database session for request lifecycle.

    Yields:
        Database session, closed after request completes.
    """
    with get_session() as session:
        yield session

SessionDep = Annotated[Session, Depends(get_db_session)]

def get_portfolio_repository(session: SessionDep) -> PortfolioRepository:
    """Provide portfolio repository.

    Args:
        session: Database session dependency.

    Returns:
        PortfolioRepository instance.
    """
    return PortfolioRepository(session)

PortfolioRepoDep = Annotated[PortfolioRepository, Depends(get_portfolio_repository)]

def get_position_repository(session: SessionDep) -> PositionRepository:
    """Provide position repository.

    Args:
        session: Database session dependency.

    Returns:
        PositionRepository instance.
    """
    return PositionRepository(session)

PositionRepoDep = Annotated[PositionRepository, Depends(get_position_repository)]

def get_transaction_repository(session: SessionDep) -> TransactionRepository:
    """Provide transaction repository.

    Args:
        session: Database session dependency.

    Returns:
        TransactionRepository instance.
    """
    return TransactionRepository(session)

TransactionRepoDep = Annotated[TransactionRepository, Depends(get_transaction_repository)]

def get_portfolio_service(session: SessionDep) -> PortfolioService:
    """Provide portfolio service with all dependencies.

    Args:
        session: Database session dependency.

    Returns:
        PortfolioService instance.
    """
    return PortfolioService(session)

PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
