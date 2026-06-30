"""Position API endpoints.

Routes for position management within portfolios.
"""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from arenawealth.api.dependencies import PortfolioRepoDep, PositionRepoDep
from arenawealth.api.dtos import (
    PositionCreateRequest,
    PositionResponse,
    PositionSummary,
    PositionUpdateRequest,
)

router = APIRouter(
    prefix="/api/v1/portfolios/{portfolio_id}/positions",
    tags=["positions"],
)

def _to_position_response(position, total_portfolio_value: Decimal) -> PositionResponse:
    """Convert model to response DTO."""
    market_value = position.shares * position.current_price
    cost_basis = position.shares * position.average_cost_basis
    gain_loss = market_value - cost_basis
    gain_pct = (gain_loss / cost_basis * 100) if cost_basis else Decimal("0")

    return PositionResponse(
        id=position.id,
        portfolio_id=position.portfolio_id,
        ticker=position.ticker,
        name=position.name,
        isin=position.isin,
        shares=position.shares,
        average_cost_basis=position.average_cost_basis,
        current_price=position.current_price,
        market_value=market_value,
        cost_basis_total=cost_basis,
        gain_loss=gain_loss,
        gain_loss_percent=gain_pct,
        opened_at=position.opened_at,
        updated_at=position.updated_at,
    )

def _to_position_summary(position, total_value: Decimal) -> PositionSummary:
    """Convert to summary view."""
    market_value = position.shares * position.current_price
    cost_basis = position.shares * position.average_cost_basis
    gain_pct = ((market_value - cost_basis) / cost_basis * 100) if cost_basis else Decimal("0")
    weight = (market_value / total_value * 100) if total_value else Decimal("0")

    return PositionSummary(
        ticker=position.ticker,
        name=position.name,
        shares=position.shares,
        current_price=position.current_price,
        market_value=market_value,
        gain_loss_percent=gain_pct,
        weight_percent=weight,
    )

@router.get("", response_model=list[PositionSummary])
def list_positions(
    portfolio_id: int,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> list[PositionSummary]:
    """List all positions in portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Returns:
        List of position summaries.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    positions = position_repo.get_by_portfolio(portfolio_id)
    total_value = sum(p.shares * p.current_price for p in positions)

    return [_to_position_summary(p, total_value) for p in positions]

@router.post("", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def create_position(
    portfolio_id: int,
    request: PositionCreateRequest,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> PositionResponse:
    """Create new position in portfolio.

    Args:
        portfolio_id: Portfolio identifier.
        request: Position creation data.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Created position data.

    Raises:
        HTTPException: 404 if portfolio not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    if position_repo.exists(portfolio_id, request.ticker):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Position for {request.ticker} already exists",
        )

    position = position_repo.create(
        portfolio_id=portfolio_id,
        ticker=request.ticker,
        name=request.name,
        shares=request.shares,
        average_cost_basis=request.average_cost_basis,
        current_price=request.current_price,
        isin=request.isin,
    )

    portfolio_repo.recalculate_totals(portfolio_id)

    total_value = position_repo.get_total_value(portfolio_id)
    return _to_position_response(position, total_value)

@router.get("/{position_id}", response_model=PositionResponse)
def get_position(
    portfolio_id: int,
    position_id: int,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> PositionResponse:
    """Get position by ID.

    Args:
        portfolio_id: Portfolio identifier.
        position_id: Position identifier.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Position data.

    Raises:
        HTTPException: 404 if not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    position = position_repo.get_by_id(position_id)
    if position is None or position.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    total_value = position_repo.get_total_value(portfolio_id)
    return _to_position_response(position, total_value)

@router.patch("/{position_id}", response_model=PositionResponse)
def update_position(
    portfolio_id: int,
    position_id: int,
    request: PositionUpdateRequest,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> PositionResponse:
    """Update position price or shares.

    Args:
        portfolio_id: Portfolio identifier.
        position_id: Position identifier.
        request: Update data.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Updated position data.

    Raises:
        HTTPException: 404 if not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    position = position_repo.get_by_id(position_id)
    if position is None or position.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    if request.current_price is not None:
        position = position_repo.update_price(position_id, request.current_price)

    portfolio_repo.recalculate_totals(portfolio_id)

    total_value = position_repo.get_total_value(portfolio_id)
    return _to_position_response(position, total_value)

@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(
    portfolio_id: int,
    position_id: int,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> None:
    """Delete position.

    Args:
        portfolio_id: Portfolio identifier.
        position_id: Position identifier.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Raises:
        HTTPException: 404 if not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    position = position_repo.get_by_id(position_id)
    if position is None or position.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found",
        )

    position_repo.delete(position_id)
    portfolio_repo.recalculate_totals(portfolio_id)

@router.get("/by-ticker/{ticker}", response_model=PositionResponse)
def get_position_by_ticker(
    portfolio_id: int,
    ticker: str,
    position_repo: PositionRepoDep,
    portfolio_repo: PortfolioRepoDep,
) -> PositionResponse:
    """Get position by ticker symbol.

    Args:
        portfolio_id: Portfolio identifier.
        ticker: Security ticker.
        position_repo: Position repository.
        portfolio_repo: Portfolio repository.

    Returns:
        Position data.

    Raises:
        HTTPException: 404 if not found.
    """
    portfolio = portfolio_repo.get_by_id(portfolio_id)
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio {portfolio_id} not found",
        )

    position = position_repo.get_by_ticker(portfolio_id, ticker)
    if position is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position for {ticker} not found",
        )

    total_value = position_repo.get_total_value(portfolio_id)
    return _to_position_response(position, total_value)
