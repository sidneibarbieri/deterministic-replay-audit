"""Tests for CSV importer using a brokerage-style seed fixture."""

from decimal import Decimal
from pathlib import Path

import pytest

from arenawealth.importers.csv_importer import import_csv

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
BROKER_CSV = FIXTURES_DIR / "seed_portfolio_broker.csv"


class TestCsvImporter:
    def test_reads_broker_fixture(self) -> None:
        positions = import_csv(BROKER_CSV)
        assert len(positions) == 17

    def test_first_position_is_lin(self) -> None:
        positions = import_csv(BROKER_CSV)
        assert positions[0].ticker == "LIN"
        assert positions[0].name == "Linde plc"

    def test_shares_precision_preserved(self) -> None:
        positions = import_csv(BROKER_CSV)
        lin = positions[0]
        assert lin.shares == Decimal("50.00000")

    def test_cost_basis_correct(self) -> None:
        positions = import_csv(BROKER_CSV)
        lin = positions[0]
        assert lin.cost_basis_per_share == Decimal("113.64")

    def test_all_tickers_present(self) -> None:
        positions = import_csv(BROKER_CSV)
        tickers = {pos.ticker for pos in positions}
        expected = {
            "LIN",
            "RELX",
            "SPGI",
            "EQIX",
            "ASML",
            "ROP",
            "MSFT",
            "GOOGL",
            "TSM",
            "AVGO",
            "PLD",
            "TDG",
            "NVO",
            "ISRG",
            "UNH",
            "JPM",
            "LLY",
        }
        assert tickers == expected

    def test_missing_ticker_column_raises(self, tmp_path: Path) -> None:
        csv = tmp_path / "bad.csv"
        csv.write_text("wrong_col,shares\nAAPL,10\n")
        with pytest.raises(ValueError, match="No ticker column found"):
            import_csv(csv)

    def test_current_price_optional_falls_back_to_cost_basis(self, tmp_path: Path) -> None:
        csv = tmp_path / "holdings.csv"
        csv.write_text("ticker,shares,cost_basis_per_share\nAAPL,10,150\n")
        positions = import_csv(csv)
        assert positions[0].current_price == Decimal("150")

    def test_reads_broker_download_columns(self, tmp_path: Path) -> None:
        csv = tmp_path / "portfolio.csv"
        csv.write_text(
            "Symbol,Name,Asset Class,Category,Total Quantity,Available Quantity,"
            "Average Price,Current Price,Total Invested,Current Value\n"
            "AVGO,Broadcom Inc,Stocks Global,Stock,24.221260,24.221260,"
            "241.16,414.14,5841.20,10030.99\n"
        )

        positions = import_csv(csv)

        assert positions[0].ticker == "AVGO"
        assert positions[0].shares == Decimal("24.221260")
        assert positions[0].cost_basis_per_share == Decimal("241.16")
        assert positions[0].current_price == Decimal("414.14")
