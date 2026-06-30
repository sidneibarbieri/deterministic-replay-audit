"""Shared visual identity for manuscript figures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLUMN_WIDTH_IN = 3.34

INK = "#344054"
MUTED = "#667085"
GRID = "#D0D5DD"
LIGHT = "#F5F7FA"
BLUE = "#466A8D"
GREEN = "#3D7157"
RED = "#A14C5D"

PDF_METADATA = {
        "Creator": "ActionAudit deterministic figure pipeline",
    "CreationDate": datetime(2026, 1, 1, tzinfo=UTC),
    "ModDate": datetime(2026, 1, 1, tzinfo=UTC),
}


def apply_paper_style() -> None:
    """Set a compact vector style that matches the LaTeX paper."""
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "DejaVu Sans",
            "font.size": 7,
            "axes.titlesize": 7,
            "axes.labelsize": 7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "axes.linewidth": 0.6,
        }
    )


def new_figure(height: float = 1.72) -> tuple[plt.Figure, plt.Axes]:
    apply_paper_style()
    return plt.subplots(figsize=(COLUMN_WIDTH_IN, height), constrained_layout=True)


def clean_axes(ax: plt.Axes, *, grid_axis: str = "y") -> None:
    """Remove chart junk while retaining scale cues."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=2.5, width=0.6, color=GRID)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.45, alpha=0.65)
        ax.set_axisbelow(True)


def save_pdf(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.04,
        metadata=PDF_METADATA,
    )
    plt.close(fig)
