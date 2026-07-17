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

Every snapshot command follows the same historical-data safeguards:

- Existing date columns and their values are preserved.
- Only missing date columns are appended.
- Once every market in an event is closed, the command exits successfully
  without adding another date.

History requests are sent through Polymarket's batch endpoint in groups of up
to 20 markets. If every requested date already exists in the CSV, the command
exits before making any API calls.

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

## Bab el-Mandeb effective-closure market

Fetch the four currently open deadline markets for Polymarket's
“Bab el-Mandeb Strait effectively closed by…?” event and create a seven-day
comparison chart:

```bash
python bab_el_mandeb_snapshot.py
```

This creates:

- `bab_el_mandeb_9am_snapshot.csv`, containing cumulative daily 9:00 AM ET
  Yes-probability snapshots.
- `bab_el_mandeb_7_day_chart.html`, comparing the latest seven days for each
  open deadline.

Resolved deadlines are excluded by default. Add `--include-closed` to retain
them when rebuilding the CSV and chart.

## Iran action and Houthi shipping markets

Two more deadline-based events use the same cumulative snapshot engine:

```bash
python iran_gulf_action_snapshot.py
python houthi_shipping_snapshot.py
```

The Iran event currently contains many unresolved daily contracts, so its
seven-day output automatically uses a heatmap. The Houthi shipping event has
only three deadline contracts and uses a line chart. Both scripts exclude
closed contracts by default and create their own cumulative CSV and HTML chart.

## Additional Houthi and crude-oil markets

Three additional event commands use the appropriate shared engine:

```bash
python houthi_saudi_action_snapshot.py
python crude_oil_ath_snapshot.py
python wti_week_july_13_snapshot.py
```

The Houthi-Saudi and crude-oil all-time-high events use deadline comparison
charts. The weekly WTI event uses the price-bin selector chart and includes all
fourteen thresholds by default, including bins that have already resolved.
Each command writes its own cumulative 9:00 AM ET CSV and seven-day HTML chart.

## Fast multi-market update

Tracked-event settings live in `tracked_events.json`. Run any configured event
through the single entry point:

```bash
python track_market.py houthi-saudi
```

The older event-specific commands remain available as compatibility wrappers.
For the four persistent daily CSVs, update events concurrently and skip unused
chart generation with:

```bash
python update_all_markets.py --data-dir .
```

Use `--with-charts` when individual event charts are also needed. CSV-only is
the faster default for the multi-market updater.

## GitHub snapshot storage

The cumulative `*_9am_snapshot.csv` files are versioned in this repository as
a second copy of the locally maintained data. The 9:00 AM Eastern automation
updates the four active cumulative files in persistent local storage and then
syncs those same files to the `agent/faster-market-updates` branch. This makes
the complete history available after cloning or downloading the repository on
a device that did not already have the local CSVs.

The same append-only and fully-closed-event safeguards apply before either copy
is replaced.

## Test

```bash
python -m unittest discover -s tests -v
```

## Data sources

- [Gamma event-by-slug API](https://docs.polymarket.com/api-reference/events/get-event-by-slug)
- [CLOB price-history API](https://docs.polymarket.com/api-reference/markets/get-prices-history)
