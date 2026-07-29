"""Shared output settings for lightweight interactive charts."""

from __future__ import annotations


def plotly_basic_cdn() -> str:
    """Return the version-matched Plotly basic bundle URL.

    The basic bundle keeps the interactive hover/dropdown behavior used here
    while avoiding the much larger full Plotly browser bundle.
    """
    from plotly.offline import get_plotlyjs_version

    return f"https://cdn.plot.ly/plotly-basic-{get_plotlyjs_version()}.min.js"
