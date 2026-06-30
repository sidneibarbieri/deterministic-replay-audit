"""Automated API user scenarios."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_scenario_operator_health(api_client: TestClient) -> None:
    """GET /api/v1/health returns an ok status."""
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_scenario_dashboard_portfolio_snapshot(api_client: TestClient) -> None:
    """The dashboard can read the aggregate portfolio snapshot."""
    response = api_client.get("/api/v1/portfolio/user?live=false")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["position_count"] >= 1
    assert isinstance(body["positions"], list)


def test_scenario_dashboard_portfolio_summary_only(api_client: TestClient) -> None:
    """The dashboard can read summary totals only."""
    response = api_client.get("/api/v1/portfolio/user/summary?live=false")
    assert response.status_code == 200
    assert "total_market_value" in response.json()


def test_scenario_dashboard_user_health_sub(api_client: TestClient) -> None:
    """The user portfolio snapshot service exposes health status."""
    response = api_client.get("/api/v1/portfolio/user/health")
    assert response.status_code == 200
    assert response.json().get("status") == "healthy"


def test_scenario_create_list_get_portfolio(api_client: TestClient) -> None:
    """Create a portfolio, list portfolios, and fetch it by id."""
    created = api_client.post(
        "/api/v1/portfolios",
        json={"name": "Test Portfolio", "currency": "USD", "initial_cash": "10000.00"},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    listed = api_client.get("/api/v1/portfolios")
    assert listed.status_code == 200
    assert any(portfolio["id"] == portfolio_id for portfolio in listed.json())

    fetched = api_client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Test Portfolio"


def test_scenario_add_position_and_list(api_client: TestClient) -> None:
    """Add a position and list the portfolio positions."""
    response = api_client.post(
        "/api/v1/portfolios",
        json={"name": "With Positions", "currency": "USD", "initial_cash": "50000.00"},
    )
    assert response.status_code == 201
    portfolio_id = response.json()["id"]

    position_response = api_client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "ticker": "AAPL",
            "name": "Apple Inc",
            "shares": "10",
            "average_cost_basis": "150.0000",
            "current_price": "175.0000",
        },
    )
    assert position_response.status_code == 201
    assert position_response.json()["ticker"] == "AAPL"

    rows = api_client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert rows.status_code == 200
    assert len(rows.json()) == 1
    assert rows.json()[0]["ticker"] == "AAPL"


def test_scenario_portfolio_analysis_empty_positions(api_client: TestClient) -> None:
    """Portfolio analysis works without network access for an empty portfolio."""
    response = api_client.post(
        "/api/v1/portfolios",
        json={"name": "Analyze Me", "currency": "USD", "initial_cash": "0"},
    )
    assert response.status_code == 201
    portfolio_id = response.json()["id"]

    analysis_response = api_client.get(f"/api/v1/portfolios/{portfolio_id}/analysis")
    assert analysis_response.status_code == 200
    body = analysis_response.json()
    assert "metrics" in body
    assert body["metrics"]["total_value"] is not None

def test_scenario_unknown_portfolio_404(api_client: TestClient) -> None:
    """Unknown portfolio ids return 404."""
    response = api_client.get("/api/v1/portfolios/999999")
    assert response.status_code == 404


def test_scenario_duplicate_ticker_conflict(api_client: TestClient) -> None:
    """A duplicate ticker in the same portfolio returns a conflict."""
    response = api_client.post(
        "/api/v1/portfolios",
        json={"name": "Dup", "currency": "USD", "initial_cash": "100000"},
    )
    portfolio_id = response.json()["id"]
    payload = {
        "ticker": "MSFT",
        "name": "Microsoft",
        "shares": "1",
        "average_cost_basis": "300.0000",
        "current_price": "310.0000",
    }
    create_response = api_client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions", json=payload
    )
    assert create_response.status_code == 201
    conflict_response = api_client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions", json=payload
    )
    assert conflict_response.status_code == 409


def test_scenario_invalid_body_validation(api_client: TestClient) -> None:
    """Invalid request bodies return validation errors."""
    response = api_client.post("/api/v1/portfolios", json={"name": ""})
    assert response.status_code == 422
