"""Chart rendering (matplotlib, headless) returning PNG bytes."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless; no GUI backends

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from .analyze import Analysis  # noqa: E402

_COLOR = "#2a6f97"
_ACCENT = "#d1495b"
_MAX_GROUP_CHARTS = 3


def _png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150, metadata={"Software": "excel-reporting"})
    plt.close(fig)
    return buf.getvalue()


def _style(ax: Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def build_charts(a: Analysis) -> dict[str, bytes]:
    """Return {chart_title: png_bytes}. Titles double as captions."""
    charts: dict[str, bytes] = {}
    metric = a.metrics[0] if a.metrics else None

    for key, table in list(a.group_tables.items())[:_MAX_GROUP_CHARTS]:
        if table.empty:
            continue
        col = f"{metric}_sum" if metric else "count"
        label = f"{metric} (total)" if metric else "Records"
        fig, ax = plt.subplots(figsize=(8, 4.2))
        ax.barh(table[key].astype(str)[::-1], table[col][::-1], color=_COLOR)
        _style(ax, f"{label} by {key}", xlabel=label)
        ax.grid(axis="x", alpha=0.25)
        ax.grid(axis="y", visible=False)
        charts[f"{label} by {key}"] = _png(fig)

    if a.trend is not None and not a.trend.empty:
        fig, ax = plt.subplots(figsize=(8, 4.2))
        series_cols = [c for c in a.trend.columns if c != "period"][:3]
        palette = [_COLOR, _ACCENT, "#6a994e"]
        for i, c in enumerate(series_cols):
            ax.plot(a.trend["period"], a.trend[c], marker="o", markersize=3,
                    color=palette[i], label=c)
        if len(series_cols) > 1:
            ax.legend(frameon=False)
        _style(ax, "Monthly trend", ylabel="Total")
        fig.autofmt_xdate()
        charts["Monthly trend"] = _png(fig)

    return charts


def build_histogram(df: pd.DataFrame, metric: str) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.hist(df[metric].dropna(), bins=30, color=_COLOR, edgecolor="white")
    _style(ax, f"Distribution of {metric}", xlabel=metric, ylabel="Frequency")
    return _png(fig)
