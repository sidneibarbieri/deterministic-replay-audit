"""Unit tests for the price backtest CLI helpers."""

import json

from scripts.price_backtest import load_target_weights, study_to_payload

from arenawealth.analytics.backtest import compare_backtests, run_backtest
from arenawealth.analytics.price_backtest import PriceBacktestStudy


def test_load_target_weights_from_csv(tmp_path):
    holdings = tmp_path / "holdings.csv"
    holdings.write_text(
        "\n".join(
            [
                "ticker,name,shares,cost_basis_per_share,current_price",
                "AAA,AAA Inc,2,10,50",
                "BBB,BBB Inc,1,10,100",
            ]
        ),
        encoding="utf-8",
    )

    assert load_target_weights(holdings) == {"AAA": 0.5, "BBB": 0.5}


def test_report_payload_is_json_serializable():
    current = run_backtest({"AAA": (0.1, 0.1)}, {"AAA": 1.0}, periods_per_year=1)
    equal_weight = run_backtest({"AAA": (0.1, 0.1)}, {"AAA": 1.0}, periods_per_year=1)
    benchmark = run_backtest({"SPY": (0.05, 0.05)}, {"SPY": 1.0}, periods_per_year=1)
    study = PriceBacktestStudy(
        start_date="2024-01-02",
        end_date="2024-01-03",
        tickers=("AAA",),
        benchmark_ticker="SPY",
        current_weight=current,
        equal_weight=equal_weight,
        benchmark=benchmark,
        current_vs_equal_weight=compare_backtests(current, equal_weight),
        current_vs_benchmark=compare_backtests(current, benchmark),
        sota_method={"method": "walk_forward_rolling_covariance"},
    )
    payload = study_to_payload(study, "20260521_180000")

    assert payload["limitations"]
    assert "baselines" in payload
    assert "comparisons" in payload
    json.dumps(payload)
