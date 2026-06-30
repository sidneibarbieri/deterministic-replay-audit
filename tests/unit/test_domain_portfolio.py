"""Tests for Position and Portfolio using a brokerage-style seed fixture."""

from decimal import Decimal

from arenawealth.domain.portfolio import Portfolio
from arenawealth.domain.position import Position

# -- Fixtures: brokerage-style seed data ---------------------------------------


def _lin_position() -> Position:
    return Position(
        ticker="LIN",
        name="Linde plc",
        shares=Decimal("50.00000"),
        cost_basis_per_share=Decimal("113.64"),
        current_price=Decimal("100.00"),
    )


def _nvo_position() -> Position:
    return Position(
        ticker="NVO",
        name="Novo Nordisk - ADR",
        shares=Decimal("50.72464"),
        cost_basis_per_share=Decimal("123.21"),
        current_price=Decimal("138.00"),
    )


def _full_seed_portfolio() -> Portfolio:
    """All 17 positions from the seed fixture."""
    rows = [
        ("LIN", "Linde plc", "50.00000", "113.64", "100.00"),
        ("RELX", "RELX Plc - ADR", "59.82906", "108.33", "117.00"),
        ("SPGI", "S&P Global Inc", "33.58209", "141.05", "134.00"),
        ("EQIX", "Equinix Inc", "47.68212", "132.46", "151.00"),
        ("ASML", "ASML Holding NV - New York Shares", "23.80952", "204.88", "168.00"),
        ("ROP", "Roper Technologies Inc", "69.60784", "96.23", "102.00"),
        ("MSFT", "Microsoft Corporation", "36.97479", "127.96", "119.00"),
        ("GOOGL", "Alphabet Inc - Class A", "36.76471", "124.77", "136.00"),
        ("TSM", "Taiwan Semiconductor Manufacturing - ADR", "33.98693", "137.84", "153.00"),
        ("AVGO", "Broadcom Inc", "27.05882", "177.08", "170.00"),
        ("PLD", "Prologis Inc", "73.07692", "100.97", "104.00"),
        ("TDG", "TransDigm Group Inc", "38.84298", "134.44", "121.00"),
        ("NVO", "Novo Nordisk - ADR", "50.72464", "123.21", "138.00"),
        ("ISRG", "Intuitive Surgical Inc", "33.54839", "164.89", "155.00"),
        ("UNH", "UnitedHealth Group Inc", "38.95349", "163.81", "172.00"),
        ("JPM", "JPMorgan Chase & Co", "69.81132", "99.07", "106.00"),
        ("LLY", "Eli Lilly & Co", "35.77236", "135.16", "123.00"),
    ]
    positions = tuple(
        Position(
            ticker=r[0],
            name=r[1],
            shares=Decimal(r[2]),
            cost_basis_per_share=Decimal(r[3]),
            current_price=Decimal(r[4]),
        )
        for r in rows
    )
    return Portfolio(positions=positions, cash_balance_amount=Decimal("1500.00"))


# -- Position tests ------------------------------------------------------------


class TestPositionGainLoss:
    def test_lin_negative_gain(self) -> None:
        position = _lin_position()
        assert position.market_value.amount == Decimal("50.00000") * Decimal("100.00")
        assert position.gain_loss.amount < 0

    def test_lin_gain_pct_matches_seed_reference(self) -> None:
        position = _lin_position()
        assert abs(position.gain_loss_pct - Decimal("-12.00")) < Decimal("0.1")

    def test_nvo_positive_gain(self) -> None:
        position = _nvo_position()
        assert position.gain_loss.amount > 0

    def test_nvo_loss_pct_matches_seed_reference(self) -> None:
        position = _nvo_position()
        assert abs(position.gain_loss_pct - Decimal("12.00")) < Decimal("0.1")


# -- Portfolio tests -----------------------------------------------------------


class TestPortfolioAggregates:
    def test_total_value_matches_seed_reference(self) -> None:
        """Tolerance covers display rounding before summing."""
        portfolio = _full_seed_portfolio()
        expected = Decimal("97000.00")
        assert abs(portfolio.total_value.amount - expected) < Decimal("5.00")

    def test_total_assets_matches_seed_reference(self) -> None:
        portfolio = _full_seed_portfolio()
        expected = Decimal("98500.00")
        assert abs(portfolio.total_assets.amount - expected) < Decimal("5.00")

    def test_total_gain_loss_matches_seed_reference(self) -> None:
        portfolio = _full_seed_portfolio()
        expected = Decimal("898.40")
        assert abs(portfolio.total_gain_loss.amount - expected) < Decimal("5.00")

    def test_total_gain_loss_pct_matches_seed_reference(self) -> None:
        portfolio = _full_seed_portfolio()
        expected = Decimal("0.93")
        assert abs(portfolio.total_gain_loss_pct - expected) < Decimal("0.1")

    def test_position_count(self) -> None:
        portfolio = _full_seed_portfolio()
        assert len(portfolio) == 17

    def test_tickers(self) -> None:
        portfolio = _full_seed_portfolio()
        assert "LIN" in portfolio.tickers
        assert "ASML" in portfolio.tickers
        assert len(portfolio.tickers) == 17


class TestPortfolioWeights:
    def test_pld_is_largest_position(self) -> None:
        portfolio = _full_seed_portfolio()
        pld_weight = portfolio.weight_pct("PLD")
        assert pld_weight > Decimal("7")
        assert pld_weight < Decimal("8")

    def test_weights_sum_to_100(self) -> None:
        portfolio = _full_seed_portfolio()
        total = sum(portfolio.weight_pct(ticker) for ticker in portfolio.tickers)
        assert abs(total - Decimal("100")) < Decimal("0.01")

    def test_unknown_ticker_returns_zero(self) -> None:
        portfolio = _full_seed_portfolio()
        assert portfolio.weight_pct("INVALID") == Decimal("0")


class TestPortfolioDisplay:
    def test_total_value_display(self) -> None:
        portfolio = _full_seed_portfolio()
        display = portfolio.total_value.display()
        assert "$" in display
        assert "97" in display
