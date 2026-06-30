"""Tests for the controlled portfolio-fit experiment."""

from arenawealth.experiments.portfolio_fit import controlled_portfolio_fit_experiment


def test_controlled_portfolio_fit_changes_the_top_candidate():
    experiment = controlled_portfolio_fit_experiment()

    assert experiment.ranking_changed
    assert experiment.isolated_top == "PLAT"
    assert experiment.portfolio_fit_top == "INDU"


def test_controlled_portfolio_fit_penalizes_crowded_theme():
    experiment = controlled_portfolio_fit_experiment()
    rows = {row.ticker: row for row in experiment.rows}

    assert rows["PLAT"].composite_score > rows["INDU"].composite_score
    assert rows["PLAT"].portfolio_fit_score < rows["INDU"].portfolio_fit_score
    assert rows["PLAT"].structural_role == "Concentration watch"
    assert rows["PLAT"].projected_theme_weight_pct > 20.0
    assert rows["INDU"].structural_role == "Diversifier"
