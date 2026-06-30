#!/usr/bin/env python3
"""Run the exploratory experiment suite and emit vector figures plus JSON.

This driver is deterministic and offline. It sweeps the production scoring and
deployment engines, reuses the most recent real price-backtest export when one
is present, and writes:

  - paper/figures/*.pdf   empirical figures for the paper
  - exports/experiments_<stamp>.json   the numeric findings

Usage:
    python scripts/run_experiments.py
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from paper_plot_style import BLUE, GREEN, INK, RED, clean_axes, new_figure, save_pdf

from arenawealth.analytics.fundamentals import DemoFundamentalsProvider
from arenawealth.analytics.models import Holding
from arenawealth.analytics.performance import sharpe_ratio
from arenawealth.analytics.universe import FINANCIAL_TICKERS, THEME_BY_TICKER
from arenawealth.analytics.workflow import analyze_holdings
from arenawealth.experiments.ablation import (
    rank_under_weights,
    standard_weight_sets,
    weight_ablation,
    weight_sensitivity,
)
from arenawealth.experiments.fee_landscape import (
    fee_landscape,
    guardrail_report,
    worst_case_premium,
)
from arenawealth.experiments.fee_sensitivity import (
    reference_schedules,
    schedule_floors,
)
from arenawealth.experiments.planner_optimality import (
    reference_report as planner_optimality_report,
)
from arenawealth.experiments.portfolio_fit import controlled_portfolio_fit_experiment
from arenawealth.experiments.robustness import (
    block_bootstrap_sharpe_diff,
    equal_weights,
    fixed_weight_returns,
    rolling_comparison,
)
from arenawealth.experiments.scenario_bank import run_scenario_bank

ROOT = Path(__file__).resolve().parent.parent
SEED_CSV = ROOT / "tests" / "fixtures" / "seed_portfolio_broker.csv"
RETURN_MATRIX_CSV = ROOT / "paper" / "data" / "returns_matrix.csv"
FIG_DIR = ROOT / "paper" / "figures"
EXPORT_DIR = ROOT / "exports"


def load_return_matrix(path: Path) -> dict[str, tuple[float, ...]]:
    """Read the tracked date-indexed return matrix into per-ticker series."""
    with path.open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        tickers = header[1:]
        columns: dict[str, list[float]] = {ticker: [] for ticker in tickers}
        for row in reader:
            for ticker, value in zip(tickers, row[1:], strict=True):
                columns[ticker].append(float(value))
    return {ticker: tuple(values) for ticker, values in columns.items()}


def current_weights_from_seed(path: Path) -> dict[str, float]:
    """Market-value weights from the seed holdings (benchmark excluded)."""
    weights: dict[str, float] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ticker = row["ticker"].strip().upper()
            weights[ticker] = float(row["shares"]) * float(row["current_price"])
    return weights


def load_holdings(path: Path) -> tuple[Holding, ...]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    holdings = []
    for row in rows:
        ticker = row["ticker"].strip().upper()
        holdings.append(
            Holding(
                ticker=ticker,
                name=row["name"].strip(),
                shares=float(row["shares"]),
                average_cost=float(row["cost_basis_per_share"]),
                broker_price=float(row["current_price"]),
                theme=THEME_BY_TICKER.get(ticker, "Other"),
                is_financial=ticker in FINANCIAL_TICKERS,
            )
        )
    return tuple(holdings)


def latest_backtest_export() -> dict | None:
    """Use the tracked reference so local exploratory exports cannot contaminate paper output."""
    reference = ROOT / "paper" / "data" / "price_backtest_reference.json"
    if reference.exists():
        return json.loads(reference.read_text())
    return None


def figure_fee_premium_pdf(landscape, path: Path) -> None:
    # Premium is only defined where the engine actually deploys (cash >= floor).
    deployed = [p for p in landscape if p.cash >= 250]
    cash = [p.cash for p in deployed]
    naive = [p.proportional_premium for p in deployed]
    aware = [p.engine_premium for p in deployed]

    fig, ax = new_figure(1.58)
    clean_axes(ax)
    ax.fill_between(cash, 0, naive, step="post", color=RED, alpha=0.16, linewidth=0)
    ax.step(cash, naive, where="post", color=RED, linewidth=1.25)
    ax.plot(cash, aware, color=GREEN, linewidth=1.45)
    ax.set_xlim(250, 5000)
    ax.set_ylim(-0.08, 2.85)
    ax.set_xticks([1000, 2000, 3000, 4000, 5000])
    ax.set_yticks([0, 2.5])
    ax.set_xlabel("Cash to deploy (USD)")
    ax.set_ylabel("Extra fee (USD)")
    ax.text(1180, 2.58, "naive split: +$2.50 bands", color=RED, fontsize=6.5)
    ax.text(
        4985,
        0.30,
        "fee-aware:\n$0 premium",
        color=GREEN,
        ha="right",
        va="bottom",
        linespacing=1.1,
        fontsize=6.3,
    )
    save_pdf(fig, path)


def rolling_excess_sharpe_points(
    asset_returns: dict[str, tuple[float, ...]],
    weights_equal: dict[str, float],
    weights_current: dict[str, float],
    window: int = 252,
    step: int = 21,
) -> list[tuple[int, float]]:
    returns_equal = fixed_weight_returns(asset_returns, weights_equal)
    returns_current = fixed_weight_returns(asset_returns, weights_current)
    length = len(returns_equal)
    starts = list(range(0, length - window + 1, step))
    return [
        (
            window_number,
            sharpe_ratio(returns_equal[start : start + window], 252.0)
            - sharpe_ratio(returns_current[start : start + window], 252.0),
        )
        for window_number, start in enumerate(starts, start=1)
    ]


def figure_robustness_pdf(
    asset_returns: dict[str, tuple[float, ...]],
    weights_equal: dict[str, float],
    weights_current: dict[str, float],
    path: Path,
) -> None:
    """Rolling 1-year excess Sharpe of equal weighting over current weighting."""
    points = rolling_excess_sharpe_points(asset_returns, weights_equal, weights_current)
    x_values = [index for index, _ in points]
    y_values = [value for _, value in points]
    colors = [BLUE if value > 0 else RED for value in y_values]

    fig, ax = new_figure(1.55)
    clean_axes(ax)
    ax.bar(x_values, y_values, width=0.72, color=colors, edgecolor="none")
    ax.axhline(0, color=INK, linewidth=0.65)
    ax.set_xlim(0, 54)
    ax.set_ylim(-0.16, 0.25)
    ax.set_xticks([1, 10, 20, 30, 40, 50])
    ax.set_yticks([-0.1, 0, 0.1, 0.2])
    ax.set_xlabel("Rolling one-year window")
    ax.set_ylabel("Sharpe difference")
    equal_higher = sum(value > 0 for value in y_values)
    current_higher = sum(value < 0 for value in y_values)
    total = len(y_values)
    ax.text(4, 0.207, f"equal higher: {equal_higher}/{total}", color=BLUE, fontsize=6.5)
    ax.text(
        39.5,
        -0.13,
        f"current higher: {current_higher}/{total}",
        color=RED,
        fontsize=6.5,
    )
    save_pdf(fig, path)


def figure_ablation_pdf(ablation_rows, path: Path) -> None:
    labels = [
        {
            "baseline_40_35_25": "baseline",
            "moat_only": "moat only",
            "compounding_only": "comp.",
            "valuation_only": "value only",
            "equal_thirds": "equal",
        }.get(row.label, row.label.replace("_", " "))
        for row in ablation_rows
    ]
    values = [row.spearman_vs_baseline for row in ablation_rows]
    colors = [BLUE if value >= 0 else RED for value in values]
    y_pos = list(range(len(labels)))

    fig, ax = new_figure(1.58)
    clean_axes(ax, grid_axis="x")
    ax.barh(y_pos, values, height=0.46, color=colors, edgecolor="none")
    ax.axvline(0, color=INK, linewidth=0.65)
    ax.set_yticks(y_pos, labels)
    ax.invert_yaxis()
    ax.set_xlim(-0.62, 1.08)
    ax.set_xticks([-0.5, 0, 0.5, 1.0])
    ax.set_xlabel("Spearman rank correlation vs. baseline")
    for y, value in zip(y_pos, values, strict=True):
        if value < 0:
            ax.text(
                value / 2,
                y,
                f"{value:.2f}",
                va="center",
                ha="center",
                color="white",
                fontsize=6.5,
            )
        else:
            ax.text(
                min(value + 0.025, 1.03),
                y,
                f"{value:.2f}",
                va="center",
                color=INK,
                fontsize=6.5,
            )
    save_pdf(fig, path)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    holdings = load_holdings(SEED_CSV)
    analyses = analyze_holdings(holdings, DemoFundamentalsProvider(holdings))

    # Experiment A/B: fee landscape and guardrail
    grid = [float(x) for x in range(0, 5001, 10)]
    landscape = fee_landscape(grid, first_share=0.6)
    guardrail = guardrail_report()
    worst = worst_case_premium(grid, first_share=0.6)

    # Experiment C: weight ablation and sensitivity (deterministic demo basket)
    ablation_rows = weight_ablation(analyses, standard_weight_sets())
    sensitivity_rows = weight_sensitivity(analyses)
    baseline_order = rank_under_weights(analyses, standard_weight_sets()["baseline_40_35_25"])

    # Experiment D: guardrail sensitivity to the fee parameters
    fee_schedule_floors = schedule_floors(reference_schedules())

    # Experiment E: reuse the most recent real backtest export
    backtest = latest_backtest_export()

    # Experiment F: robustness of the equal-weight-beats-current result
    robustness = None
    if RETURN_MATRIX_CSV.exists():
        asset_returns = load_return_matrix(RETURN_MATRIX_CSV)
        current_raw = current_weights_from_seed(SEED_CSV)
        basket = sorted(ticker for ticker in current_raw if ticker in asset_returns)
        basket_returns = {ticker: asset_returns[ticker] for ticker in basket}
        weights_current = {ticker: current_raw[ticker] for ticker in basket}
        weights_equal = equal_weights(basket)
        robustness = {
            "rolling": rolling_comparison(basket_returns, weights_equal, weights_current),
            "bootstrap": block_bootstrap_sharpe_diff(
                basket_returns, weights_equal, weights_current
            ),
        }

    # Experiment G: isolated asset quality versus portfolio fit
    portfolio_fit = controlled_portfolio_fit_experiment()

    # Experiment H: planner suboptimality against the MIP deployment optimum
    optimality = planner_optimality_report()

    # Experiment I: offline frozen-scenario advisor benchmark
    advisor_benchmark = run_scenario_bank()

    # Figures. The sensitivity sweep and the backtest are reported in prose and
    # the backtest table; their data still feeds the JSON below, but a figure
    # would only restate the closed form and the table, so none is rendered.
    figure_fee_premium_pdf(landscape, FIG_DIR / "fee_premium.pdf")
    figure_ablation_pdf(ablation_rows, FIG_DIR / "ablation.pdf")
    if robustness is not None:
        figure_robustness_pdf(
            basket_returns, weights_equal, weights_current, FIG_DIR / "robustness.pdf"
        )

    findings = {
        "generated_utc": stamp,
        "fee_landscape": {
            "guardrail": asdict(guardrail),
            "worst_naive_premium": asdict(worst),
            "engine_overpay_band": [
                {"cash": point.cash, "engine_premium": point.engine_premium}
                for point in landscape
                if point.engine_premium > 0
            ],
            "max_engine_premium": max(point.engine_premium for point in landscape),
            "max_naive_premium": max(point.proportional_premium for point in landscape),
        },
        "fee_sensitivity": {
            "schedule_floors": [asdict(row) for row in fee_schedule_floors],
            "floor_is_tranche_invariant": True,
        },
        "robustness": (
            {
                "rolling": asdict(robustness["rolling"]),
                "bootstrap": asdict(robustness["bootstrap"]),
            }
            if robustness is not None
            else None
        ),
        "ablation": {
            "baseline_order": baseline_order,
            "rows": [asdict(row) for row in ablation_rows],
            "sensitivity": [asdict(row) for row in sensitivity_rows],
            "top_k_stable": all(not row.top_k_changed for row in sensitivity_rows),
        },
        "portfolio_fit": asdict(portfolio_fit),
        "planner_optimality": {
            "max_deployment_gap": optimality.max_deployment_gap,
            "max_fee_premium": optimality.max_fee_premium,
            "points": [asdict(point) for point in optimality.points],
        },
        "advisor_scenario_bank": asdict(advisor_benchmark),
        "backtest": _summarize_backtest(backtest),
    }
    out = EXPORT_DIR / f"experiments_{stamp}.json"
    out.write_text(json.dumps(findings, indent=2))

    _print_summary(findings, out)


def _summarize_backtest(export: dict | None) -> dict | None:
    if export is None:
        return None

    def metrics(values: dict) -> dict:
        return {
            "cagr": values["cagr"],
            "sharpe_ratio": values["sharpe_ratio"],
            "max_drawdown": values["max_drawdown"],
        }

    summary: dict = {
        "window": [export["start_date"], export["end_date"]],
        "baselines": {name: metrics(values) for name, values in export["baselines"].items()},
        "comparisons": export.get("comparisons"),
        "limitations": export.get("limitations"),
    }
    sota_baselines = export.get("sota_baselines")
    if sota_baselines:
        summary["sota_baselines"] = {
            name: metrics(values) for name, values in sota_baselines.items()
        }
        summary["sota_comparisons"] = export.get("sota_comparisons")
        summary["sota_method"] = export.get("sota_method")
    return summary


def _print_summary(findings: dict, out: Path) -> None:
    fee = findings["fee_landscape"]
    band = fee["engine_overpay_band"]
    print("== Fee landscape ==")
    print(f"  guardrail fixed point: ${fee['guardrail']['one_percent_fixed_point']:.0f}")
    if band:
        low = min(point["cash"] for point in band)
        high = max(point["cash"] for point in band)
        peak = fee["max_engine_premium"]
        print(f"  engine overpay band: ${low:.0f}..${high:.0f} (max ${peak:.2f})")
    else:
        print("  engine overpay band: none (fee-optimal everywhere)")
    print(f"  worst naive premium: ${fee['worst_naive_premium']['proportional_premium']:.2f}")
    print("== Ablation ==")
    for row in findings["ablation"]["rows"]:
        print(
            f"  {row['label']:>20}: top={row['top']} spearman={row['spearman_vs_baseline']:.3f}"
            f" churn={row['top_k_churn']}"
        )
    print(
        f"  top-2 stable under +/-10% weight perturbation: {findings['ablation']['top_k_stable']}"
    )
    portfolio_fit = findings["portfolio_fit"]
    print("== Portfolio fit ==")
    print(
        f"  isolated top={portfolio_fit['isolated_top']} "
        f"portfolio-fit top={portfolio_fit['portfolio_fit_top']} "
        f"changed={portfolio_fit['ranking_changed']}"
    )
    backtest = findings["backtest"]
    if backtest:
        print("== Backtest (real data) ==")
        strategies = {**backtest["baselines"], **backtest.get("sota_baselines", {})}
        for name, stats in strategies.items():
            print(
                f"  {name:>16}: CAGR={stats['cagr'] * 100:5.2f}% "
                f"Sharpe={stats['sharpe_ratio']:.3f} "
                f"MaxDD={stats['max_drawdown'] * 100:6.1f}%"
            )
    advisor_bank = findings["advisor_scenario_bank"]
    print("== Advisor scenario bank ==")
    print(
        f"  scenarios={advisor_bank['scenario_count']} "
        f"advisors={advisor_bank['advisor_count']} "
        f"runs={advisor_bank['total_runs']} "
        f"manifest={advisor_bank['manifest_sha256'][:12]}"
    )
    for row in advisor_bank["advisor_aggregates"]:
        print(
            f"  {row['advisor_label']:>25}: "
            f"valid={row['validity_rate']:.3f} "
            f"agree={row['mean_agreement']:.3f} "
            f"setS={row['mean_set_stability']:.3f} "
            f"agreement-fp={row['agreement_only_false_positive_rate']:.3f}"
        )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
