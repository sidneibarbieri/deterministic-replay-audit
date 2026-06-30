"""Integration: dashboard portfolio route mounted on main app."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from arenawealth.api.routers.user_portfolio import (
    LiveQuote,
    build_snapshot,
    read_cached_quotes,
    write_cached_quotes,
)
from arenawealth.models.database import QuoteHistory, get_session


def test_portfolio_user_returns_payload(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/portfolio/user?live=false")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "positions" in body
    assert "analysis" in body
    assert body["price_source"] == "stored"
    assert body["summary"]["position_count"] >= 1


def test_build_snapshot_overlays_live_prices() -> None:
    snapshot = build_snapshot(
        live=True,
        quote_lookup=lambda tickers: {ticker: LiveQuote(1234.0, 1.5) for ticker in tickers},
    )

    assert snapshot.price_source == "live"
    assert snapshot.positions
    assert all(position.current_price == 1234.0 for position in snapshot.positions)
    assert all(position.change_pct == 1.5 for position in snapshot.positions)


def test_quote_cache_round_trip(api_client: TestClient) -> None:
    write_cached_quotes({"AAPL": LiveQuote(price=123.45, change_pct=1.2)})

    quotes = read_cached_quotes(["AAPL"], max_age=timedelta(minutes=15))

    assert quotes["AAPL"] == LiveQuote(price=123.45, change_pct=1.2)


def test_quote_cache_respects_ttl(api_client: TestClient) -> None:
    with get_session() as session:
        session.add(
            QuoteHistory(
                ticker="MSFT",
                price=Decimal("300.00"),
                change_percent=Decimal("0.5"),
                recorded_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )
        )
        session.commit()

    quotes = read_cached_quotes(["MSFT"], max_age=timedelta(minutes=15))

    assert quotes == {}


def test_health_aggregate_exists(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json().get("status") == "healthy"


def test_provider_status_never_returns_secret_values(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/status")

    assert response.status_code == 200
    body = response.json()
    assert body
    assert {provider["provider_id"] for provider in body} >= {"yahoo", "sec_edgar"}
    assert all("api_key" not in provider for provider in body)
    assert all("configured" in provider for provider in body)


def test_data_sources_health_config_mode_hides_secret_values(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/data-sources/health")

    assert response.status_code == 200
    body = response.json()
    assert body["live"] is False
    assert body["sources"]
    assert all("api_key" not in source for source in body["sources"])
    assert all(source["status"] in {"configured", "not_configured"} for source in body["sources"])


def test_portfolio_recommendation_offline_demo(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/portfolio/user/recommendation?offline_demo=true")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_mode"] == "offline-demo"
    assert body["minimum_order_amount"] == 250.0
    assert body["ranked_positions"]


def test_large_cash_recommendation_diversifies_fee_neutrally(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/api/v1/portfolio/user/recommendation?cash=100000&offline_demo=true"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["orders"]) > 2
    assert sum(order["amount"] for order in body["orders"]) == 100000.0
    assert sum(order["fee"] for order in body["orders"]) == 250.0


def test_recommendation_is_replayable_from_same_inputs(api_client: TestClient) -> None:
    """The decision is a pure function of (holdings, cash, policy, provider mode).

    Replaying the same input tuple must regenerate an identical recommendation.
    Only the wall-clock timestamp may differ; orders, exclusions, and the ranked
    candidate list must be byte-identical. This is the auditability guarantee the
    paper relies on.
    """
    url = "/api/v1/portfolio/user/recommendation?cash=1500.00&offline_demo=true"
    first = api_client.get(url).json()
    second = api_client.get(url).json()

    replayable = {key: value for key, value in first.items() if key != "generated_at"}
    replayed = {key: value for key, value in second.items() if key != "generated_at"}
    assert replayable == replayed
    assert first["orders"] == second["orders"]
    assert first["ranked_positions"] == second["ranked_positions"]


def test_portfolio_recommendation_rejects_uneconomic_cash(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/portfolio/user/recommendation?cash=0.10&offline_demo=true")

    assert response.status_code == 200
    body = response.json()
    assert body["minimum_order_amount"] == 250.0
    assert body["provider_mode"] == "not-run"
    assert body["orders"] == []


def test_recommendation_run_is_recorded_in_decision_log(
    api_client: TestClient,
) -> None:
    initial_response = api_client.get("/api/v1/portfolio/user/decisions")
    assert initial_response.status_code == 200
    assert initial_response.json() == []

    response = api_client.get("/api/v1/portfolio/user/recommendation?cash=0.10&offline_demo=true")
    assert response.status_code == 200

    log_response = api_client.get("/api/v1/portfolio/user/decisions")
    assert log_response.status_code == 200
    logs = log_response.json()
    assert len(logs) == 1
    assert logs[0]["policy_version"] == "cash-deployment-v1"
    assert logs[0]["provider_mode"] == "not-run"
    assert logs[0]["cash"] == 0.1
    assert logs[0]["order_count"] == 0
    assert logs[0]["total_order_amount"] == 0.0


def test_manual_trade_writes_local_inbox_portfolio(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    seed = inbox / "portfolio.csv"
    seed.write_text("ticker,name,shares,cost_basis_per_share,current_price\nAAPL,Apple,1,100,110\n")
    manual = inbox / "manual-portfolio.csv"
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", manual)

    response = api_client.post(
        "/api/v1/portfolio/user/trades",
        json={
            "action": "buy",
            "ticker": "AAPL",
            "name": "Apple",
            "shares": 1,
            "price": 120,
            "fees": 2,
        },
    )

    assert response.status_code == 200
    assert manual.exists()
    assert "AAPL,Apple,2.0,111.0,120.0" in manual.read_text()


def test_manual_sell_rejects_fee_above_gross_proceeds(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    seed = inbox / "portfolio.csv"
    seed.write_text("ticker,name,shares,cost_basis_per_share,current_price\nAAPL,Apple,1,100,110\n")
    manual = inbox / "manual-portfolio.csv"
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", manual)

    response = api_client.post(
        "/api/v1/portfolio/user/trades",
        json={
            "action": "sell",
            "ticker": "AAPL",
            "shares": 1,
            "price": 100,
            "fees": 101,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Fees cannot exceed gross sale proceeds"


def test_portfolio_source_reports_manual_override(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    manual = inbox / "manual-portfolio.csv"
    manual.write_text("ticker,name,shares,cost_basis_per_share,current_price\nAAPL,Apple,1,100,110\n")
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", manual)

    response = api_client.get("/api/v1/portfolio/user/source")

    assert response.status_code == 200
    body = response.json()
    assert body["active_type"] == "manual"
    assert body["manual_override"] is True
    assert body["position_count"] == 1


def test_clear_manual_portfolio_restores_broker_export(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    broker = inbox / "portfolio.csv"
    broker.write_text("ticker,name,shares,cost_basis_per_share,current_price\nMSFT,Microsoft,1,200,210\n")
    manual = inbox / "manual-portfolio.csv"
    manual.write_text("ticker,name,shares,cost_basis_per_share,current_price\nAAPL,Apple,1,100,110\n")
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", manual)

    response = api_client.delete("/api/v1/portfolio/user/source/manual")

    assert response.status_code == 200
    assert not manual.exists()
    body = response.json()
    assert body["positions"][0]["ticker"] == "MSFT"


def test_upload_broker_csv_becomes_active_source(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", inbox / "manual-portfolio.csv")

    broker_csv = (
        "Symbol,Description,Total Quantity,Average Price,Current Price\n"
        "NVDA,NVIDIA Corp,10,100.00,150.00\n"
    )
    response = api_client.post(
        "/api/v1/portfolio/user/source/upload",
        files={"file": ("broker-export-fixture.csv", broker_csv, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    tickers = [position["ticker"] for position in body["positions"]]
    assert "NVDA" in tickers
    stored = list(inbox.glob("upload-*.csv"))
    assert len(stored) == 1


def test_upload_rejects_csv_without_ticker_column(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", inbox / "manual-portfolio.csv")

    response = api_client.post(
        "/api/v1/portfolio/user/source/upload",
        files={"file": ("bad.csv", "foo,bar\n1,2\n", "text/csv")},
    )

    assert response.status_code == 400
    assert "ticker" in response.json()["detail"].lower()
    assert not list(inbox.glob("upload-*.csv"))


def test_upload_rejects_empty_file(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import arenawealth.api.routers.user_portfolio as user_portfolio

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setenv("ACTIONAUDIT_PORTFOLIO_INBOX", str(inbox))
    monkeypatch.setattr(user_portfolio, "MANUAL_PORTFOLIO", inbox / "manual-portfolio.csv")

    response = api_client.post(
        "/api/v1/portfolio/user/source/upload",
        files={"file": ("empty.csv", "", "text/csv")},
    )

    assert response.status_code == 400


def test_portfolio_candidates_offline_demo(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/portfolio/user/candidates?offline_demo=true&limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["provider_mode"] == "offline-demo"
    assert body["review"]["current_positions"] >= 1
    assert body["review"]["target_min_positions"] == 18
    assert 1 <= len(body["candidates"]) <= 5
    scores = [candidate["composite_score"] for candidate in body["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_portfolio_audit_results_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/portfolio/audit-results")
    assert response.status_code == 200
    body = response.json()
    assert "version" in body
    assert "overall" in body
    assert "by_advisor" in body
    assert "reports" in body
