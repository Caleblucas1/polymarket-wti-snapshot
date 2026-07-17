# Polymarket WTI Snapshot Exporter

Exports the latest available **Yes** price at or before 9:00 AM Eastern for each
price bin in Polymarket's July 2026 WTI event. Prices are written as percentages
for the seven most recent calendar-day snapshots.

The script uses Polymarket's public Gamma and CLOB APIs; no API key is required.

## Setup

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```bash
python polymarket_wti_snapshot.py
```

The default output is `wti_july_2026_9am_snapshot.csv`. Each row is a price bin,
and each ISO-formatted date column contains an implied probability percentage.
When the file already exists, the script preserves its history and appends only
date columns that are not already present. Existing snapshots are never revised.

Options can change the event, output, snapshot count, or snapshot hour:

```bash
python polymarket_wti_snapshot.py \
  --slug what-price-will-wti-hit-in-july-2026 \
  --output snapshots.csv \
  --days 7 \
  --hour 9
```

The value for a date is the latest five-minute observation returned by
Polymarket at or before that day's target time. It may predate the target when
no exact 9:00 AM observation exists.

## Create the seven-day chart

After generating the CSV, create an interactive time-series chart:

```bash
python plot_wti_timeseries.py
```

The chart is saved as `wti_7_day_time_series.html`. It uses the latest seven
dates in the cumulative CSV. Open it in a browser and use the controls to select
a WTI price bin or switch between an automatic and fixed 0–100% probability
scale.

Use different input or output paths when needed:

```bash
python plot_wti_timeseries.py \
  --input wti_july_2026_9am_snapshot.csv \
  --output charts/wti_7_day_time_series.html
```

## Simple seven-day bar chart

The `agent/simple-chart-option` branch also includes a simpler chart for one
price bin. Each bar shows that day's total odds. When the odds increased from
the previous day, only the incremental portion is stacked in a darker color.

```bash
python plot_wti_simple_bar.py
```

The default price bin is `↑ $90`. Select another exact CSV row label with:

```bash
python plot_wti_simple_bar.py --price-bin '↑ $85'
```

The output is `wti_simple_7_day_bar.html`.

## Compare five chart formats

Generate one interactive gallery containing all five display options:

```bash
python plot_wti_chart_options.py
```

The output is `wti_chart_options.html`, with buttons for:

1. Increase bars for one focus bin (default: `↑ $90`).
2. Five upside price bands on a shared line-chart scale.
3. A seven-day heatmap containing every available price bin.
4. A latest-day horizontal odds ladder containing every available price bin.
5. Six small-multiple trend charts with independent scales.

Change the focus bin or output path when needed:

```bash
python plot_wti_chart_options.py \
  --focus-bin '↑ $85' \
  --output charts/wti_chart_options.html
```

## Test

```bash
python -m unittest discover -s tests -v
```

## Data sources

- [Gamma event-by-slug API](https://docs.polymarket.com/api-reference/events/get-event-by-slug)
- [CLOB price-history API](https://docs.polymarket.com/api-reference/markets/get-prices-history)
