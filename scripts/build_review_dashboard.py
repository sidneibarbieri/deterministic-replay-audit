#!/usr/bin/env python3
"""Generate a self-contained HTML audit dashboard for reviewers.

Reads the cached audit summaries and run manifests and renders one offline HTML
file that maps each headline number to its supporting result and the raw JSON
behind it. No server and no build step: open the file in a browser. Reviewers use
it to audit, from the artifact, exactly what they read in the paper.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = ROOT / "paper" / "data" / "adversarial_runs"
OUTPUT_PATH = ROOT / "paper" / "data" / "review_dashboard.html"
ARM_ORDER = ("bare", "policy", "scaffold")


def valid_rate(audits: list[dict]) -> tuple[int, int]:
    runs = sum(audit["runs"] for audit in audits)
    valid = sum(audit["valid_runs"] for audit in audits)
    return valid, runs


def violation_totals(audits: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for audit in audits:
        for name, count in audit["violation_counts"]:
            category = name.split(":")[0]
            totals[category] = totals.get(category, 0) + count
    return totals


def load_cell(summary_path: Path) -> dict:
    """One (model, arm) cell from its audit summary and optional run manifest."""
    audits = json.loads(summary_path.read_text(encoding="utf-8"))
    valid, runs = valid_rate(audits)
    manifest_path = summary_path.with_name("run_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return {
        "model": summary_path.parent.parent.name,
        "arm": summary_path.parent.name,
        "valid": valid,
        "runs": runs,
        "rate": valid / runs if runs else 0.0,
        "violations": violation_totals(audits),
        "manifest": manifest,
        "summary_rel": summary_path.relative_to(RESULTS_ROOT.parent).as_posix(),
    }


def collect_cells(results_root: Path) -> list[dict]:
    cells = [load_cell(path) for path in sorted(results_root.rglob("audit_summary.json"))]
    arm_rank = {arm: index for index, arm in enumerate(ARM_ORDER)}
    return sorted(cells, key=lambda cell: (cell["model"], arm_rank.get(cell["arm"], 9)))


def rate_class(rate: float) -> str:
    if rate >= 0.9:
        return "ok"
    if rate >= 0.7:
        return "warn"
    return "bad"


def render_rows(cells: list[dict]) -> str:
    rows = []
    for cell in cells:
        violations = ", ".join(f"{name} ({count})" for name, count in sorted(cell["violations"].items()))
        rows.append(
            f'<tr data-arm="{html.escape(cell["arm"])}">'
            f'<td>{html.escape(cell["model"])}</td>'
            f'<td><span class="pill {html.escape(cell["arm"])}">{html.escape(cell["arm"])}</span></td>'
            f'<td class="num {rate_class(cell["rate"])}">{cell["rate"]:.2f}</td>'
            f'<td class="num">{cell["valid"]}/{cell["runs"]}</td>'
            f'<td class="muted">{html.escape(violations) or "none"}</td>'
            f'<td><a href="{html.escape(cell["summary_rel"])}">raw JSON</a></td>'
            "</tr>"
        )
    return "\n".join(rows)


def render_provenance(cells: list[dict]) -> str:
    seen: set[str] = set()
    cards = []
    for cell in cells:
        manifest = cell["manifest"]
        key = f"{cell['model']}/{cell['arm']}"
        if not manifest or key in seen:
            continue
        seen.add(key)
        cards.append(
            '<div class="card">'
            f'<h4>{html.escape(cell["model"])} / {html.escape(cell["arm"])}</h4>'
            f'<p>scenarios hash <code>{html.escape(manifest.get("scenarios_sha256", "")[:16])}</code></p>'
            f'<p>temperature {manifest.get("temperature", "?")} '
            f'&middot; {manifest.get("live_calls", "?")} calls '
            f'&middot; {manifest.get("retries", "?")} retries</p>'
            f'<p>wall clock {manifest.get("wall_clock_seconds", "?")} s '
            f'&middot; python {html.escape(str(manifest.get("environment", {}).get("python", "?")))}</p>'
            "</div>"
        )
    return "\n".join(cards) or "<p class='muted'>No run manifests found.</p>"


def render_html(cells: list[dict]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Executable-Action Audit - Reviewer Dashboard</title>
<style>
:root {{
  --ink: #1e293b; --muted: #64748b; --line: #e2e8f0; --paper: #ffffff;
  --navy: #1e3a5f; --ok: #15803d; --warn: #b45309; --bad: #b91c1c;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  color: var(--ink); background: #f8fafc; margin: 0; line-height: 1.5; }}
header {{ background: var(--navy); color: #fff; padding: 28px 32px; }}
header h1 {{ margin: 0 0 6px; font-size: 22px; font-weight: 600; }}
header p {{ margin: 0; color: #cbd5e1; font-size: 14px; }}
main {{ max-width: 960px; margin: 0 auto; padding: 28px 32px 60px; }}
h2 {{ font-size: 16px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); border-bottom: 1px solid var(--line); padding-bottom: 8px; margin-top: 36px; }}
table {{ width: 100%; border-collapse: collapse; background: var(--paper); font-size: 14px;
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); }}
th {{ background: #f1f5f9; font-weight: 600; color: var(--muted); font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
td.muted, .muted {{ color: var(--muted); }}
.ok {{ color: var(--ok); }} .warn {{ color: var(--warn); }} .bad {{ color: var(--bad); }}
.pill {{ font-size: 12px; padding: 2px 8px; border-radius: 999px; background: #e2e8f0; color: #334155; }}
.pill.scaffold {{ background: #dcfce7; color: #166534; }}
.pill.bare {{ background: #fee2e2; color: #991b1b; }}
.filters {{ margin: 12px 0; }}
.filters button {{ font: inherit; border: 1px solid var(--line); background: #fff; color: var(--ink);
  padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-right: 6px; }}
.filters button.active {{ background: var(--navy); color: #fff; border-color: var(--navy); }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
.card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
.card h4 {{ margin: 0 0 8px; font-size: 14px; }}
.card p {{ margin: 2px 0; font-size: 13px; color: var(--muted); }}
code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }}
a {{ color: var(--navy); }}
</style>
</head>
<body>
<header>
  <h1>Executable-Action Audit &mdash; Reviewer Dashboard</h1>
  <p>Each row links to the raw audited model runs. Generated offline from the artifact.</p>
</header>
<main>
  <h2>Validity by model and prompt arm</h2>
  <p class="muted">Valid rate is the fraction of model runs that satisfy every constraint.
  Higher is better; policy states the contract, and scaffold additionally supplies
  the pre-computed fee arithmetic.</p>
  <div class="filters" id="filters">
    <button class="active" data-filter="all">All arms</button>
    <button data-filter="bare">bare</button>
    <button data-filter="policy">policy</button>
    <button data-filter="scaffold">scaffold</button>
  </div>
  <table>
    <thead><tr><th>Model</th><th>Arm</th><th>Valid rate</th><th>Valid/runs</th>
    <th>Violations</th><th>Evidence</th></tr></thead>
    <tbody id="rows">
{render_rows(cells)}
    </tbody>
  </table>

  <h2>Reproducibility and provenance</h2>
  <div class="cards">
{render_provenance(cells)}
  </div>
</main>
<script>
const buttons = document.querySelectorAll('#filters button');
buttons.forEach(button => button.addEventListener('click', () => {{
  buttons.forEach(other => other.classList.remove('active'));
  button.classList.add('active');
  const filter = button.dataset.filter;
  document.querySelectorAll('#rows tr').forEach(row => {{
    row.style.display = (filter === 'all' || row.dataset.arm === filter) ? '' : 'none';
  }});
}}));
</script>
</body>
</html>
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    cells = collect_cells(arguments.results)
    if not cells:
        raise SystemExit(f"no audit summaries found under {arguments.results}")
    arguments.out.write_text(render_html(cells), encoding="utf-8")
    print(f"wrote {arguments.out.relative_to(ROOT)} from {len(cells)} audited cells")


if __name__ == "__main__":
    main()
