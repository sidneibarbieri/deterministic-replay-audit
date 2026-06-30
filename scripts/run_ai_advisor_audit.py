#!/usr/bin/env python3
"""Run the offline AI-advisor audit benchmark.

The benchmark does not call an LLM. It evaluates frozen advisor outputs and
synthetic failure-mode baselines against deterministic constraints so future
model outputs can be compared without changing the measurement surface.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
from paper_plot_style import BLUE, INK, LIGHT, RED, new_figure, save_pdf

from arenawealth.experiments.ai_advisor import (
    AdvisorRecommendation,
    AdvisorRunSetReport,
    AdvisorScenario,
    evaluate_run_set,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS = ROOT / "paper" / "data" / "ai_advisor_scenarios.json"
REFERENCE_OUTPUT = ROOT / "paper" / "data" / "ai_advisor_audit_reference.json"
FIGURE_OUTPUT = ROOT / "paper" / "figures" / "ai_advisor_audit.pdf"
EXPORT_DIR = ROOT / "exports"


def load_suite(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_from_payload(payload: dict[str, Any]) -> AdvisorScenario:
    return AdvisorScenario(
        name=payload["name"],
        cash=float(payload["cash"]),
        allowed_tickers=tuple(payload["allowed_tickers"]),
        owned_tickers=tuple(payload["owned_tickers"]),
        policy_tickers=tuple(payload.get("policy_tickers", ())),
        concentration_blocked_tickers=tuple(
            payload.get("concentration_blocked_tickers", ())
        ),
        available_fact_ids=tuple(payload.get("available_fact_ids", ())),
        max_recommendations=int(payload.get("max_recommendations", 3)),
        add_only=bool(payload.get("add_only", True)),
        amounts_required=bool(payload.get("amounts_required", False)),
    )


def recommendation_from_payload(payload: dict[str, Any]) -> AdvisorRecommendation:
    return AdvisorRecommendation(
        run_id=payload["run_id"],
        tickers=tuple(payload["tickers"]),
        amounts=tuple(float(amount) for amount in payload.get("amounts", ())),
        cited_fact_ids=tuple(payload.get("cited_fact_ids", ())),
    )


def evaluate_suite(suite: dict[str, Any]) -> tuple[AdvisorRunSetReport, ...]:
    reports: list[AdvisorRunSetReport] = []
    for scenario_payload in suite["scenarios"]:
        scenario = scenario_from_payload(scenario_payload)
        for advisor_label, recommendation_payloads in scenario_payload["recommendations"].items():
            recommendations = tuple(
                recommendation_from_payload(payload) for payload in recommendation_payloads
            )
            reports.append(evaluate_run_set(scenario, advisor_label, recommendations))
    return tuple(reports)


def summarize_reports(
    suite: dict[str, Any], reports: tuple[AdvisorRunSetReport, ...]
) -> dict[str, Any]:
    return {
        "version": suite["version"],
        "description": suite["description"],
        "scenario_count": len(suite["scenarios"]),
        "advisor_count": len({report.advisor_label for report in reports}),
        "overall": overall_summary(reports),
        "by_advisor": summarize_by_advisor(reports),
        "reports": [report_payload(report) for report in reports],
    }


def overall_summary(reports: tuple[AdvisorRunSetReport, ...]) -> dict[str, Any]:
    return {
        "run_sets": len(reports),
        "mean_valid_rate": mean(report.valid_rate for report in reports),
        "mean_policy_agreement": mean(
            report.mean_agreement_at_k for report in reports
        ),
        "mean_stability": mean(report.stability.mean_pairwise_jaccard for report in reports),
        "mean_amount_stability": mean_amount_stability(reports),
        "violation_counts": flatten_violation_counts(reports),
    }


def mean_amount_stability(reports: tuple[AdvisorRunSetReport, ...]) -> float | None:
    """Average sizing stability over the run sets that actually carry amounts."""
    values = [
        report.stability.amount_stability
        for report in reports
        if report.stability.amount_stability is not None
    ]
    return mean(values) if values else None


def summarize_by_advisor(reports: tuple[AdvisorRunSetReport, ...]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[AdvisorRunSetReport]] = defaultdict(list)
    for report in reports:
        grouped[report.advisor_label].append(report)
    return {
        advisor_label: {
            "scenarios": len(items),
            "mean_valid_rate": mean(item.valid_rate for item in items),
            "mean_policy_agreement": mean(
                item.mean_agreement_at_k for item in items
            ),
            "mean_stability": mean(item.stability.mean_pairwise_jaccard for item in items),
            "mean_amount_stability": mean_amount_stability(tuple(items)),
            "violation_counts": flatten_violation_counts(tuple(items)),
        }
        for advisor_label, items in sorted(grouped.items())
    }


def flatten_violation_counts(reports: tuple[AdvisorRunSetReport, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for violation, count in report.violation_counts:
            counts[violation] = counts.get(violation, 0) + count
    return dict(sorted(counts.items()))


def report_payload(report: AdvisorRunSetReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["valid_rate"] = report.valid_rate
    return payload


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# AI Advisor Audit Reference",
        "",
        "This file is generated from frozen offline scenarios. It does not contain",
        "live model outputs or investment advice.",
        "",
        "## Overall",
        "",
        f"- Scenarios: {summary['scenario_count']}",
        f"- Advisor labels: {summary['advisor_count']}",
        f"- Mean valid rate: {summary['overall']['mean_valid_rate']:.3f}",
        f"- Mean policy agreement: {summary['overall']['mean_policy_agreement']:.3f}",
        f"- Mean stability: {summary['overall']['mean_stability']:.3f}",
        "",
        "## By Advisor",
        "",
        "| Advisor | Valid rate | Policy agreement | Stability | Violations |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for advisor_label, values in summary["by_advisor"].items():
        violations = ", ".join(
            f"{violation}={count}" for violation, count in values["violation_counts"].items()
        )
        if not violations:
            violations = "none"
        lines.append(
            f"| {advisor_label} | {values['mean_valid_rate']:.3f} | "
            f"{values['mean_policy_agreement']:.3f} | "
            f"{values['mean_stability']:.3f} | {violations} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_advisor_audit_pdf(summary: dict[str, Any], path: Path) -> None:
    labels = sorted(summary["by_advisor"], key=advisor_sort_key)
    rows: list[tuple[str, float, float, float]] = [
        (
            display_label(label),
            summary["by_advisor"][label]["mean_valid_rate"],
            summary["by_advisor"][label]["mean_policy_agreement"],
            summary["by_advisor"][label]["mean_stability"],
        )
        for label in labels
    ]
    matrix = [
        [valid for _, valid, _, _ in rows],
        [agreement for _, _, agreement, _ in rows],
        [stability for _, _, _, stability in rows],
    ]
    cmap = LinearSegmentedColormap.from_list("arena_score", [LIGHT, BLUE])
    fig, ax = new_figure(1.62)
    # Draw cells as vector patches rather than imshow, so the heatmap stays
    # resolution-independent and never pixelates when the PDF is zoomed.
    for row_index, values in enumerate(matrix):
        for col_index, value in enumerate(values):
            ax.add_patch(
                Rectangle(
                    (col_index - 0.5, row_index - 0.5),
                    1,
                    1,
                    facecolor=cmap(value),
                    edgecolor="none",
                )
            )
    ax.set_xticks(range(len(rows)), [label for label, *_ in rows], rotation=0)
    ax.set_yticks(range(3), ["Validity", "Agreement", "Stability"])
    ax.tick_params(length=0, pad=2)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(rows))], minor=True)
    ax.set_yticks([0.5, 1.5], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    for row_index, values in enumerate(matrix):
        for col_index, value in enumerate(values):
            color = "white" if value >= 0.72 else INK
            label = "1" if value == 1 else "0" if value == 0 else f"{value:.2f}"
            ax.text(
                col_index,
                row_index,
                label,
                ha="center",
                va="center",
                color=color,
                fontsize=6.5,
            )
    # The key reviewer objection: high agreement can coexist with invalidity.
    ax.add_patch(Rectangle((2.5, -0.5), 1, 1, fill=False, edgecolor=RED, linewidth=1.0))
    ax.text(3, -0.82, "agreement=1, invalid", ha="center", va="bottom", fontsize=6.5, color=RED)
    ax.set_xlim(-0.5, len(rows) - 0.5)
    ax.set_ylim(2.5, -1.0)
    save_pdf(fig, path)

def advisor_sort_key(label: str) -> tuple[int, str]:
    order = {
        "deterministic_policy": 0,
        "valid_but_low_agreement": 1,
        "drifting_advisor": 2,
        "naive_diversifier": 3,
        "underdeploying_advisor": 4,
        "popularity_chaser": 5,
        "constraint_breaker": 6,
    }
    return order.get(label, 99), label


def display_label(label: str) -> str:
    names = {
        "constraint_breaker": "breaks",
        "deterministic_policy": "policy",
        "drifting_advisor": "drift",
        "naive_diversifier": "naive\nsplit",
        "popularity_chaser": "popular",
        "underdeploying_advisor": "under\ndeploy",
        "valid_but_low_agreement": "valid\nlow-agree",
    }
    return names.get(label, label.replace("_", "\n"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--figure", type=Path, default=FIGURE_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    suite = load_suite(args.scenarios)
    reports = evaluate_suite(suite)
    summary = summarize_reports(suite, reports)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output = args.output or EXPORT_DIR / f"ai_advisor_audit_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.reference:
        REFERENCE_OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown = args.markdown or output.with_suffix(".md")
    write_markdown(summary, markdown)
    args.figure.parent.mkdir(parents=True, exist_ok=True)
    write_advisor_audit_pdf(summary, args.figure)
    print(
        "AI advisor audit: "
        f"valid={summary['overall']['mean_valid_rate']:.3f} "
        f"policy_agreement={summary['overall']['mean_policy_agreement']:.3f} "
        f"stability={summary['overall']['mean_stability']:.3f}"
    )
    print(f"Wrote {output}")
    print(f"Wrote {markdown}")
    print(f"Wrote {args.figure}")


if __name__ == "__main__":
    main()
