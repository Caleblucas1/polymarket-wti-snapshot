"""Shared output settings for lightweight, trace-compatible charts."""

from __future__ import annotations


def plotly_basic_cdn() -> str:
    """Return the version-matched Plotly basic bundle URL.

    The basic bundle keeps the interactive hover/dropdown behavior used here
    while avoiding the much larger full Plotly browser bundle.
    """
    from plotly.offline import get_plotlyjs_version

    return f"https://cdn.plot.ly/plotly-basic-{get_plotlyjs_version()}.min.js"


def plotly_cartesian_cdn() -> str:
    """Return the version-matched Plotly cartesian bundle URL.

    Unlike the basic bundle, the cartesian bundle includes heatmap traces while
    remaining substantially smaller than the complete Plotly browser bundle.
    """
    from plotly.offline import get_plotlyjs_version

    return f"https://cdn.plot.ly/plotly-cartesian-{get_plotlyjs_version()}.min.js"


def plotly_cdn_for_figure(figure: object) -> str:
    """Choose the smallest official bundle that supports every figure trace."""
    trace_types = {
        str(getattr(trace, "type", "") or "").lower()
        for trace in getattr(figure, "data", ())
    }
    basic_types = {"bar", "pie", "scatter"}
    cartesian_types = basic_types | {
        "box",
        "contour",
        "heatmap",
        "histogram",
        "histogram2d",
        "histogram2dcontour",
        "image",
        "scatterternary",
        "violin",
    }
    if trace_types <= basic_types:
        return plotly_basic_cdn()
    if trace_types <= cartesian_types:
        return plotly_cartesian_cdn()
    raise ValueError(
        "No configured lightweight Plotly bundle supports trace types: "
        + ", ".join(sorted(trace_types))
    )
