#!/usr/bin/env python3
"""Render related-market comparison panels from stored snapshot and range CSVs."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plot_wti_timeseries import load_ranges, load_snapshot
from track_market import load_registry


DEFAULT_PAIRS = Path(__file__).with_name("related_market_pairs.json")
DEFAULT_OUTPUT = Path("related_houthi_market_comparison.html")
LABEL_COLUMN = "Deadline"


@dataclass(frozen=True)
class RelatedPair:
    """Configuration for one related-market comparison."""

    id: str
    title: str
    relationship: str
    left_event: str
    left_label: str
    right_event: str
    right_label: str
    note: str = ""


@dataclass(frozen=True)
class PairSeries:
    """Aligned observations for a related-market pair."""

    pair: RelatedPair
    dates: list[str]
    left_values: list[float]
    right_values: list[float]
    left_ranges: list[tuple[float | None, float | None]]
    right_ranges: list[tuple[float | None, float | None]]

    @property
    def spreads(self) -> list[float]:
        """Return left-minus-right spreads in percentage points."""
        return [
            left_value - right_value
            for left_value, right_value in zip(self.left_values, self.right_values)
        ]

    @property
    def latest_spread(self) -> float | None:
        """Return the most recent spread, if available."""
        return self.spreads[-1] if self.spreads else None


def load_pair_config(path: Path = DEFAULT_PAIRS) -> list[RelatedPair]:
    """Load related-market pair configuration."""
    with path.open(encoding="utf-8") as input_file:
        payload = json.load(input_file)
    if not isinstance(payload, list) or not payload:
        raise ValueError("Related-market config must be a non-empty list")

    pairs: list[RelatedPair] = []
    required = {
        "id",
        "title",
        "relationship",
        "left_event",
        "left_label",
        "right_event",
        "right_label",
    }
    for index, raw_pair in enumerate(payload, start=1):
        if not isinstance(raw_pair, dict) or not required.issubset(raw_pair):
            raise ValueError(f"Invalid related-market pair at index {index}")
        pairs.append(
            RelatedPair(
                id=str(raw_pair["id"]),
                title=str(raw_pair["title"]),
                relationship=str(raw_pair["relationship"]),
                left_event=str(raw_pair["left_event"]),
                left_label=str(raw_pair["left_label"]),
                right_event=str(raw_pair["right_event"]),
                right_label=str(raw_pair["right_label"]),
                note=str(raw_pair.get("note", "")),
            )
        )
    return pairs


def event_paths(
    event_key: str,
    *,
    registry: dict[str, dict[str, Any]],
    data_dir: Path,
) -> tuple[Path, Path | None]:
    """Return snapshot and range paths for a configured event."""
    if event_key not in registry:
        raise ValueError(f"Unknown related-market event: {event_key}")
    config = registry[event_key]
    snapshot_path = data_dir / str(config["output"])
    range_output = config.get("range_output")
    range_path = data_dir / str(range_output) if range_output else None
    return snapshot_path, range_path


def aligned_pair_series(
    pair: RelatedPair,
    *,
    registry: dict[str, dict[str, Any]],
    data_dir: Path,
    days: int,
) -> PairSeries:
    """Load and align one pair's overlapping snapshot and range observations."""
    left_path, left_range_path = event_paths(pair.left_event, registry=registry, data_dir=data_dir)
    right_path, right_range_path = event_paths(
        pair.right_event,
        registry=registry,
        data_dir=data_dir,
    )

    left_dates, left_series = load_snapshot(left_path, label_column=LABEL_COLUMN)
    right_dates, right_series = load_snapshot(right_path, label_column=LABEL_COLUMN)
    if pair.left_label not in left_series:
        raise ValueError(f"{pair.left_event} is missing row {pair.left_label!r}")
    if pair.right_label not in right_series:
        raise ValueError(f"{pair.right_event} is missing row {pair.right_label!r}")

    common_dates = sorted(set(left_dates).intersection(right_dates))[-days:]
    left_index = {date_string: index for index, date_string in enumerate(left_dates)}
    right_index = {date_string: index for index, date_string in enumerate(right_dates)}

    dates: list[str] = []
    left_values: list[float] = []
    right_values: list[float] = []
    for date_string in common_dates:
        left_value = left_series[pair.left_label][left_index[date_string]]
        right_value = right_series[pair.right_label][right_index[date_string]]
        if left_value is None or right_value is None:
            continue
        dates.append(date_string)
        left_values.append(left_value)
        right_values.append(right_value)

    left_ranges_by_label = (
        load_ranges(left_range_path, label_column=LABEL_COLUMN).get(pair.left_label, {})
        if left_range_path and left_range_path.exists()
        else {}
    )
    right_ranges_by_label = (
        load_ranges(right_range_path, label_column=LABEL_COLUMN).get(pair.right_label, {})
        if right_range_path and right_range_path.exists()
        else {}
    )

    return PairSeries(
        pair=pair,
        dates=dates,
        left_values=left_values,
        right_values=right_values,
        left_ranges=[left_ranges_by_label.get(date_string, (None, None)) for date_string in dates],
        right_ranges=[
            right_ranges_by_label.get(date_string, (None, None)) for date_string in dates
        ],
    )


def _range_errors(
    values: list[float],
    ranges: list[tuple[float | None, float | None]],
) -> tuple[list[float | None], list[float | None], list[list[str]]]:
    """Return Plotly lower/upper error arrays and hover-ready range text."""
    lower_errors: list[float | None] = []
    upper_errors: list[float | None] = []
    customdata: list[list[str]] = []
    for value, (low, high) in zip(values, ranges):
        valid = low is not None and high is not None and low <= value <= high
        lower_errors.append(value - low if valid else None)
        upper_errors.append(high - value if valid else None)
        customdata.append(
            [
                "n/a" if not valid else f"{low:.1f}%",
                "n/a" if not valid else f"{high:.1f}%",
            ]
        )
    return lower_errors, upper_errors, customdata


def build_chart(pair_series: list[PairSeries]) -> Any:
    """Build the related-market comparison dashboard."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if not pair_series:
        raise ValueError("No related-market pairs are available to chart")

    figure = make_subplots(
        rows=len(pair_series),
        cols=1,
        specs=[[{"secondary_y": True}] for _ in pair_series],
        subplot_titles=[
            f"{series.pair.title} · {series.pair.relationship}"
            for series in pair_series
        ],
        vertical_spacing=0.18 if len(pair_series) > 1 else 0.12,
    )
    colors = {
        "left": "#2563EB",
        "right": "#D97706",
        "spread": "#64748B",
    }

    annotations: list[str] = []
    for row, series in enumerate(pair_series, start=1):
        left_lower, left_upper, left_customdata = _range_errors(
            series.left_values,
            series.left_ranges,
        )
        right_lower, right_upper, right_customdata = _range_errors(
            series.right_values,
            series.right_ranges,
        )
        figure.add_trace(
            go.Scatter(
                x=series.dates,
                y=series.left_values,
                mode="lines+markers",
                name=f"{series.pair.left_event}: {series.pair.left_label}",
                legendgroup=series.pair.id,
                line={"color": colors["left"], "width": 3},
                marker={"color": colors["left"], "size": 8},
                customdata=left_customdata,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": left_upper,
                    "arrayminus": left_lower,
                    "color": colors["left"],
                    "thickness": 2,
                    "width": 8,
                    "visible": any(value is not None for value in left_upper),
                },
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>%{x} at 9:00 AM ET"
                    "<br>Snapshot: %{y:.1f}%"
                    "<br>Prior 24h low: %{customdata[0]}"
                    "<br>Prior 24h high: %{customdata[1]}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=series.dates,
                y=series.right_values,
                mode="lines+markers",
                name=f"{series.pair.right_event}: {series.pair.right_label}",
                legendgroup=series.pair.id,
                line={"color": colors["right"], "width": 3},
                marker={"color": colors["right"], "size": 8},
                customdata=right_customdata,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": right_upper,
                    "arrayminus": right_lower,
                    "color": colors["right"],
                    "thickness": 2,
                    "width": 8,
                    "visible": any(value is not None for value in right_upper),
                },
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>%{x} at 9:00 AM ET"
                    "<br>Snapshot: %{y:.1f}%"
                    "<br>Prior 24h low: %{customdata[0]}"
                    "<br>Prior 24h high: %{customdata[1]}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
            secondary_y=False,
        )
        figure.add_trace(
            go.Bar(
                x=series.dates,
                y=series.spreads,
                name=f"Spread: {series.pair.left_label} minus {series.pair.right_label}",
                legendgroup=series.pair.id,
                marker={"color": colors["spread"], "opacity": 0.35},
                hovertemplate="Spread: %{y:.1f} percentage points<extra></extra>",
            ),
            row=row,
            col=1,
            secondary_y=True,
        )
        figure.update_yaxes(
            title_text="Probability",
            ticksuffix="%",
            range=[0, 100],
            row=row,
            col=1,
            secondary_y=False,
        )
        figure.update_yaxes(
            title_text="Spread",
            ticksuffix=" pp",
            zeroline=True,
            row=row,
            col=1,
            secondary_y=True,
        )
        if series.pair.note:
            annotations.append(f"{series.pair.title}: {series.pair.note}")

    figure.update_layout(
        title={
            "text": "Related Houthi escalation market comparison",
            "x": 0.5,
        },
        template="plotly_white",
        hovermode="x unified",
        barmode="overlay",
        height=max(620, 390 * len(pair_series)),
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.06},
        margin={"l": 75, "r": 75, "t": 130, "b": 120},
    )
    figure.update_xaxes(title_text="Daily 9:00 AM ET snapshot")
    figure.add_annotation(
        text=(
            "Use this as a research and anomaly-detection panel, not as an "
            "arbitrage label. Similar prices can reflect shared risk while the "
            "contracts still resolve under different rules."
        ),
        xref="paper",
        yref="paper",
        x=0,
        y=-0.11,
        showarrow=False,
        xanchor="left",
        font={"size": 11, "color": "#334155"},
    )
    if annotations:
        figure.add_annotation(
            text="<br>".join(annotations),
            xref="paper",
            yref="paper",
            x=0,
            y=-0.18,
            showarrow=False,
            xanchor="left",
            align="left",
            font={"size": 10, "color": "#64748B"},
        )
    return figure


def write_related_market_chart(
    *,
    data_dir: Path = Path("."),
    output: Path = DEFAULT_OUTPUT,
    pairs_path: Path = DEFAULT_PAIRS,
    days: int = 7,
) -> int:
    """Write the related-market dashboard and return the number of pairs plotted."""
    registry = load_registry()
    pairs = load_pair_config(pairs_path)
    series = [
        aligned_pair_series(pair, registry=registry, data_dir=data_dir, days=days)
        for pair in pairs
    ]
    figure = build_chart(series)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        output,
        include_plotlyjs="cdn",
        full_html=True,
        config={"displaylogo": False, "responsive": True},
    )
    return len(series)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Create a related-market comparison chart from stored CSVs."
    )
    parser.add_argument("--data-dir", type=Path, default=Path("."), help="CSV directory")
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS, help="Pair config JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="HTML output path")
    parser.add_argument("--days", type=int, default=7, help="Most recent dates to chart")
    return parser


def main() -> int:
    """Run the chart command."""
    args = build_parser().parse_args()
    try:
        count = write_related_market_chart(
            data_dir=args.data_dir,
            output=args.output,
            pairs_path=args.pairs,
            days=args.days,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 2
    print(f"Wrote {args.output} with {count} related-market comparison(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
