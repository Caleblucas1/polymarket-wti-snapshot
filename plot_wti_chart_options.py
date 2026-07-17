#!/usr/bin/env python3
"""Generate a five-format gallery from the latest WTI snapshot CSV."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Any

from plot_wti_simple_bar import create_chart as create_increase_bar_chart
from plot_wti_timeseries import DEFAULT_INPUT, latest_window, load_snapshot


DEFAULT_OUTPUT = Path("wti_chart_options.html")
PREFERRED_UPSIDE_LABELS = ["↑ $80", "↑ $85", "↑ $90", "↑ $95", "↑ $100"]
PREFERRED_SMALL_MULTIPLES = [
    "↑ $80",
    "↑ $85",
    "↑ $90",
    "↑ $100",
    "↑ $110",
    "↓ $65",
]


def price_level(label: str) -> float:
    """Return the numeric price level embedded in a price-bin label."""
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", label)
    return float(match.group(1)) if match else float("-inf")


def ordered_labels(series: dict[str, list[float | None]]) -> list[str]:
    """Order upside bins first, then downside bins, highest price first."""
    return sorted(
        series,
        key=lambda label: (
            0 if label.startswith("↑") else 1,
            -price_level(label),
            label,
        ),
    )


def available_labels(
    preferred: list[str], series: dict[str, list[float | None]], limit: int
) -> list[str]:
    """Choose preferred labels that exist, then fill from the remaining bins."""
    selected = [label for label in preferred if label in series]
    selected.extend(label for label in ordered_labels(series) if label not in selected)
    return selected[:limit]


def create_price_bands_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Compare five important upside price bins on a shared probability scale."""
    import plotly.graph_objects as go

    labels = available_labels(PREFERRED_UPSIDE_LABELS, series, 5)
    colors = ["#2563EB", "#0891B2", "#059669", "#D97706", "#DC2626"]
    figure = go.Figure()
    for label, color in zip(labels, colors):
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=series[label],
                mode="lines+markers",
                name=label,
                line={"color": color, "width": 3},
                marker={"color": color, "size": 8},
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>%{y:.1f}% implied probability<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title={"text": "WTI upside price bands — seven-day comparison", "x": 0.5},
        template="plotly_white",
        hovermode="x unified",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={"title": "Implied probability (%)", "range": [0, 100], "ticksuffix": "%"},
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.1},
        margin={"l": 70, "r": 35, "t": 120, "b": 75},
    )
    return figure


def create_heatmap_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Show every price bin in a compact probability heatmap."""
    import plotly.graph_objects as go

    labels = ordered_labels(series)
    values = [series[label] for label in labels]
    text = [
        ["—" if value is None else f"{value:.1f}%" for value in row]
        for row in values
    ]
    figure = go.Figure(
        go.Heatmap(
            x=dates,
            y=labels,
            z=values,
            zmin=0,
            zmax=100,
            colorscale=[
                [0.0, "#EFF6FF"],
                [0.15, "#BFDBFE"],
                [0.4, "#60A5FA"],
                [0.7, "#2563EB"],
                [1.0, "#1E3A8A"],
            ],
            text=text,
            texttemplate="%{text}",
            hovertemplate=(
                "<b>%{y}</b><br>%{x} at 9:00 AM ET"
                "<br>%{z:.1f}% implied probability<extra></extra>"
            ),
            colorbar={"title": {"text": "Odds"}, "ticksuffix": "%"},
            xgap=2,
            ygap=2,
        )
    )
    figure.update_layout(
        title={"text": "All WTI price bins — seven-day heatmap", "x": 0.5},
        template="plotly_white",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={"title": "Price bin", "autorange": "reversed"},
        height=max(620, 33 * len(labels) + 155),
        margin={"l": 90, "r": 65, "t": 80, "b": 75},
    )
    return figure


def create_odds_ladder_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Show the latest snapshot for all bins as a horizontal odds ladder."""
    import plotly.graph_objects as go

    labels = ordered_labels(series)
    latest_values = [series[label][-1] for label in labels]
    colors = ["#2563EB" if label.startswith("↑") else "#D97706" for label in labels]
    text = ["—" if value is None else f"{value:.1f}%" for value in latest_values]
    figure = go.Figure(
        go.Bar(
            x=latest_values,
            y=labels,
            orientation="h",
            marker={"color": colors},
            text=text,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.1f}% implied probability<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title={"text": f"WTI odds ladder — latest snapshot ({dates[-1]})", "x": 0.5},
        template="plotly_white",
        xaxis={"title": "Implied probability (%)", "range": [0, 105], "ticksuffix": "%"},
        yaxis={"title": "Price bin", "autorange": "reversed"},
        height=max(620, 30 * len(labels) + 145),
        margin={"l": 90, "r": 55, "t": 80, "b": 70},
        showlegend=False,
    )
    return figure


def create_small_multiples_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Give six selected price bins their own compact seven-day panels."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    labels = available_labels(PREFERRED_SMALL_MULTIPLES, series, 6)
    rows = 2 if len(labels) > 3 else 1
    columns = min(3, len(labels))
    figure = make_subplots(rows=rows, cols=columns, subplot_titles=labels)
    colors = ["#2563EB", "#0891B2", "#059669", "#D97706", "#DC2626", "#7C3AED"]

    for index, (label, color) in enumerate(zip(labels, colors)):
        row = index // columns + 1
        column = index % columns + 1
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=series[label],
                mode="lines+markers",
                name=label,
                showlegend=False,
                line={"color": color, "width": 3},
                marker={"color": color, "size": 7},
                fill="tozeroy",
                fillcolor=color.replace(")", ", 0.12)")
                if color.startswith("rgb(")
                else None,
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>%{y:.1f}% implied probability<extra></extra>"
                ),
            ),
            row=row,
            col=column,
        )

    figure.update_xaxes(type="date", showgrid=False)
    figure.update_yaxes(rangemode="tozero", ticksuffix="%", gridcolor="#E5E7EB")
    figure.update_layout(
        title={"text": "Selected WTI price bins — small multiples", "x": 0.5},
        template="plotly_white",
        height=650 if rows == 2 else 390,
        margin={"l": 55, "r": 35, "t": 95, "b": 55},
    )
    return figure


def create_figures(
    dates: list[str], series: dict[str, list[float | None]], focus_bin: str
) -> list[tuple[str, str, Any]]:
    """Build the five chart-format options."""
    if focus_bin not in series:
        raise ValueError(f"Focus bin {focus_bin!r} is not present in the CSV")
    return [
        (
            "Increase bars",
            f"Focused {focus_bin} view; darker sections show increases from the prior day.",
            create_increase_bar_chart(dates, series[focus_bin], focus_bin),
        ),
        (
            "Price bands",
            "Five upside price bins on a shared scale for direct comparison.",
            create_price_bands_chart(dates, series),
        ),
        (
            "All-market heatmap",
            "Every available price bin in a compact seven-day probability map.",
            create_heatmap_chart(dates, series),
        ),
        (
            "Latest odds ladder",
            "All price bins compared at the most recent 9:00 AM snapshot.",
            create_odds_ladder_chart(dates, series),
        ),
        (
            "Small multiples",
            "Six selected price bins in separate panels so each trend remains readable.",
            create_small_multiples_chart(dates, series),
        ),
    ]


def write_gallery(path: Path, figures: list[tuple[str, str, Any]]) -> None:
    """Write one responsive HTML page with controls for all five formats."""
    from plotly.io import to_html

    buttons: list[str] = []
    panels: list[str] = []
    for index, (name, description, figure) in enumerate(figures, start=1):
        active = index == 1
        buttons.append(
            f'<button type="button" data-panel="option-{index}" '
            f'aria-pressed="{str(active).lower()}">{index}. {html.escape(name)}</button>'
        )
        fragment = to_html(
            figure,
            full_html=False,
            include_plotlyjs="cdn" if active else False,
            config={"displaylogo": False, "responsive": True},
            div_id=f"wti-chart-option-{index}",
        )
        hidden = "" if active else " hidden"
        panels.append(
            f'<section id="option-{index}"{hidden}>'
            f'<p>{html.escape(description)}</p>{fragment}</section>'
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WTI chart format options</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 1100px; padding: 24px; }}
    h1 {{ font-size: 1.45rem; margin: 0 0 16px; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    button {{ border: 1px solid #94a3b8; border-radius: 7px; cursor: pointer; padding: 8px 12px; }}
    button[aria-pressed="true"] {{ background: #1d4ed8; border-color: #1d4ed8; color: white; }}
    section > p {{ color: #64748b; margin: 0 0 6px; }}
    [hidden] {{ display: none; }}
    @media (prefers-color-scheme: dark) {{
      section > p {{ color: #cbd5e1; }}
      button {{ background: #1e293b; border-color: #64748b; color: #f8fafc; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WTI seven-day chart formats</h1>
    <nav aria-label="Chart format">{''.join(buttons)}</nav>
    {''.join(panels)}
  </main>
  <script>
    const buttons = document.querySelectorAll("button[data-panel]");
    const panels = document.querySelectorAll("main section");
    buttons.forEach((button) => {{
      button.addEventListener("click", () => {{
        buttons.forEach((candidate) => candidate.setAttribute(
          "aria-pressed", candidate === button ? "true" : "false"
        ));
        panels.forEach((panel) => {{
          panel.hidden = panel.id !== button.dataset.panel;
        }});
        const chart = document.querySelector(`#${{button.dataset.panel}} .plotly-graph-div`);
        if (chart && window.Plotly) requestAnimationFrame(() => Plotly.Plots.resize(chart));
      }});
    }});
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a five-format gallery from a WTI snapshot CSV."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Snapshot CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument("--days", type=int, default=7, help="Most recent days to chart")
    parser.add_argument("--focus-bin", default="↑ $90", help="Bin used by Increase bars")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dates, series = load_snapshot(args.input)
        dates, series = latest_window(dates, series, args.days)
        figures = create_figures(dates, series, args.focus_bin)
        write_gallery(args.output, figures)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Created {args.output} with {len(figures)} chart formats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
