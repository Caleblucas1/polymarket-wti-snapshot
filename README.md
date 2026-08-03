# Polymarket WTI Snapshot Exporter

Exports the latest available **Yes** price at or before 9:00 AM Eastern for each
price bin in Polymarket's July 2026 WTI event. Prices are written as percentages
for the seven most recent calendar-day snapshots.

The script uses Polymarket's public Gamma and CLOB APIs; no API key is required.

## Narrative-break signal questionnaire

Open `signal_questionnaire.html` in a browser to calibrate market-level signal
scenarios in one batch. The form defaults to the ten highlighted priority
questions and can reveal all 32 scenarios. The scenarios use Gray-code
ordering, so exactly one market contract changes from each row to the next.
Each row has:

- complete, human-readable headers naming one specific contract per column;
- a pre-selected suggested signal level;
- a dropdown for the user's signal level, including `Flat`;
- an optional notes field.

The yellow-highlighted rows are the most important calibration decisions. The
page saves answers in the browser and produces a compact response that can be
copied into ChatGPT all at once.

`signal_market_catalog.json` is the authoritative list of supplied Polymarket
event pages. An event page is only a container: every currently active dated,
threshold, or day-specific contract on that page is represented as its own
exact signal row. The five contracts first used in the questionnaire remain a
highlighted convenience view, but they are not primary signals and no other
active event is treated as reference-only. Exact contracts are never averaged
into broad diplomacy, shipping, or oil baskets.

### Recurring event rollover

Gamma exposes recurring-family metadata in `event.series[]`, including a
stable series ID and `recurrence` value such as `weekly`, `monthly`, or
`daily`. The series endpoint returns sibling event slugs. `recurring_events.py`
uses that metadata to select the next not-yet-ended sibling for configured
recurring families while retaining the logical source ID and prior URLs.

The live dashboard therefore does not keep pointing at an expired July page
when Polymarket has published the August or next-week instance. If Gamma has
not published a successor yet, the resolver keeps the configured page and
records `configured-fallback-no-future-sibling` instead of guessing. Daily
Houthi questions are treated as one container because the event itself holds
the dated contracts. Historical-only catalog slots remain auditable but are not
fetched as duplicate live sources.

## Durable daily signal review records

The active-contract signal dashboard records each generated observation through
`signal_review.persist_observation()`. The default append-only store is
`signal_records/observations.jsonl`. Each line preserves the cutoff timestamp,
the event and exact contract identity, raw probabilities, comparable prior-day
and seven-day changes, level and change read-throughs, the signal
classification, the definition version, and a fingerprint of the source
catalog. A refresh can therefore contain more signal rows than event pages
when an event has multiple active contracts.

Records are duplicate-safe by cutoff timestamp, so rerunning the same daily
update does not create a second evidence row. The dashboard's dropdown ratings
and notes remain annotations: they can be exported for later calibration, but
cannot change the stored evidence or silently change the contract definitions.

The generated HTML dashboard is intentionally an ephemeral scratch artifact;
the JSONL observation store is the durable project record.

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

The WTI tracker also writes `wti_july_2026_9am_ranges.csv`. Each row contains a
price bin, snapshot date, and the observed minimum and maximum probability over
the complete 24-hour period ending at that day's 9:00 AM ET snapshot. These
ranges reuse the same CLOB history response as the snapshot, so they do not add
one request per market. When a resolved or inactive bin has no observation in a
window, its last observed snapshot is carried forward as a zero-width range.
Stored ranges are cumulative and are never revised.

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
scale. Vertical whiskers show each point's trailing-24-hour low and high when
the companion range CSV is available.

Use different input or output paths when needed:

```bash
python plot_wti_timeseries.py \
  --input wti_july_2026_9am_snapshot.csv \
  --range-input wti_july_2026_9am_ranges.csv \
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
python wti_week_july_27_snapshot.py
```

The Houthi-Saudi and crude-oil all-time-high events use deadline comparison
charts. The weekly WTI tracker follows the current Week of July 27 event and
uses the grouped price-bin chart with all fourteen thresholds. The previous
Week of July 13 files remain stored but are no longer part of the daily update
or briefing. Each command writes its own cumulative 9:00 AM ET CSV and
seven-day HTML chart.

## Fast multi-market update

Tracked-event settings live in `tracked_events.json`. Run any configured event
through the single entry point:

```bash
python track_market.py houthi-saudi
```

The older event-specific commands remain available as compatibility wrappers.
For all eight persistent daily CSVs, update events concurrently and skip unused
chart generation with:

```bash
python update_all_markets.py --data-dir .
```

Use `--with-charts` to regenerate the displayed event charts from the stored CSVs,
including on a day when no date needs to be appended. CSV-only remains the
faster default, and the chart pass uses Plotly's smaller basic browser bundle.
The command reports each event as `appended`, `already current`,
`fully closed`, or `failed`. Every event also maintains a companion
`*_9am_ranges.csv` file with the observed five-minute low and high during the
24 hours ending at each 9:00 AM ET snapshot. Small deadline charts show these
as whiskers; dense heatmaps show the low–high range in each populated cell and
in its hover details.

When charts are enabled, the updater also publishes freshness-verified,
content-addressed copies under `published_charts/` and writes
`published_charts/latest.json`. A chart is rejected if the newest snapshot date
is absent from its HTML. The published filename contains both that date and the
chart's SHA-256 prefix, so changed content never reuses a previously surfaced
filename. User-facing links should always come from the manifest rather than
the mutable compatibility filename at the repository root.

The same command refreshes `market_resolution_status.csv` from Gamma metadata.
It records each contract's current UMA status, whether it is currently
disputed, whether it has ever been disputed, the dispute count and status
history, whether it is closed or automatically resolved, and the terminal Yes
probability when available. Past disputes are sticky: a later resolved status
does not erase the historical dispute flag.

The status inventory also stores each physical condition's creation time,
resolution time, and current Yes probability. The WTI chart uses those fields
with the readable single-condition dropdown, marks every observed Yes
resolution with a red vertical line, and shows the newest active replacement as
a live diamond. A resolved condition's terminal 100% value is never carried
into later dates: the logical line remains blank until a replacement condition
exists, then restarts from that replacement's own price.

Every resolved conditional's chart tooltip reports the resolved outcome, the
actual resolution date/time, and whether Gamma identified it as automatic or
manual/UMA. It intentionally does not show terminal probability as a separate
tooltip field because that value is no longer decision-relevant after
resolution. The fully resolved older Houthi shipping and Houthi-Saudi markets
remain in the authoritative CSV and status histories but are excluded from the
daily chart manifest. The July 22 Houthi-shipping event is a separate
day-specific question and remains eligible for daily chart publication. It is
not a continuation of the resolved cumulative-by-deadline event.

When `--with-charts` is run for the full active registry, the command also
writes `related_houthi_market_comparison.html`. That panel compares
hand-selected related markets such as Houthi shipping July 31 versus
Houthi-Saudi July 31 and Bab el-Mandeb August 31 versus Houthi-Saudi July 24.
It shows both probabilities, intraday low-high whiskers, and the point-in-time
spread. The panel is for research and anomaly detection only; similar prices
are not treated as arbitrage because each contract resolves under its own
rules.

`market_resolution_events.csv` is an append-only transition log. It timestamps
newly observed disputes, cleared disputes, and final resolutions. Dense
deadline heatmaps outline disputed cells in red and resolved cells in green.
Because Polymarket does not expose timestamps for status changes that predate
this tracker, historical disputes discovered at initial setup retain their
sticky flag but are not assigned an invented chart date.

## Unified hourly market data and lifecycle

Market identity, lifecycle, hourly price, order-book liquidity, and reports live
under `market_data/`. The existing root-level daily snapshot, intraday-range,
and resolution-status CSVs retain their paths and schemas for compatibility;
`market_data/datasets.json` declares their grain and authority so the two
frequencies cannot be confused. Collect a current observation for every
configured event with:

```bash
python update_orderbooks.py --data-dir market_data
```

The collector batches public CLOB book requests and stores Yes-token depth in
shares and price-weighted notional at 1¢, 2¢, 5¢, and 10¢ from the best quote.
Its report opens with clearly labeled blue bid-side support and red ask-side
resistance, with controls for effective dollars, raw five-point dollars, and
raw five-point shares. Effective depth applies exponential distance decay with
a one-probability-point half-life, preventing distant penny orders from
dominating the default view. It then ranks markets by weaker-side effective
depth, compares
spread with executable two-sided depth, and summarizes liquidity by Asia,
Europe, U.S., and evening hours as intraday observations accumulate. It also
maintains a physical market-instance inventory.

Logical identity includes the configured event and the full normalized market
label. When Polymarket publishes a new condition/token for the same logical
contract, the new instance links to the prior condition and cumulative volume
continues across the replacement. Appearances, disappearances, closure, order
acceptance, and order-book state changes are recorded once in the lifecycle
event file. Each update retains that complete audit history but returns only
newly detected lifecycle events in its command output.

Hourly rows call the physical condition's traded volume **Current Listing
Volume**. **Continuous Market Volume** is the sum across genuine replacement
conditions belonging to the same event and normalized market label. A related
condition ID is either the previous condition for a
true replacement or a comparison condition in the same price-threshold family;
the lifecycle event type distinguishes those cases.

Each hourly row stores both price context and liquidity. `Book Midpoint
Probability` is current two-sided book information; `Gamma Last Trade
Probability` may be older. `Reference Probability` prefers the midpoint and
falls back to the last trade, while `Reference Price Source` makes that choice
explicit. This avoids maintaining a second hourly price source.

Hourly runs write observations into bounded monthly files under
`market_data/hourly/`. The original baseline remains readable, while the daily
9:00 AM snapshot/range/status files are not modified. These high-frequency files
remain in persistent local storage rather than being committed every hour;
source code and compact lifecycle changes remain suitable for GitHub sync.

Price direction remains part of contract identity: `↑ $80` and `↓ $80` share
an `$80` comparison family, but are not stitched because they are opposite
propositions. See `market_data/SCHEMA.md` for the complete schema and definitions.

## GitHub snapshot storage

The cumulative `*_9am_snapshot.csv` files, all seven companion range CSVs, and
the resolution-status inventory are versioned in this repository as a second
copy of the locally maintained data. The 9:00 AM Eastern automation updates
these files in persistent local storage and then syncs the same files to the
configured branch. This makes the complete history available after cloning or
downloading the repository on a device that did not already have the local
CSVs.

The same append-only and fully-closed-event safeguards apply before either copy
is replaced.

## Iran de-escalation narrative-break signal

`narrative_break_signal.py` turns the Iran blockade and peace-talk signal into a
small rules game. Each component can be mixed into a scenario, then classified as
Green, Weaker Yellow, Yellow, Yellow/Orange, Orange, Orange/Red, or Red.

List the component cards and allowed moves:

```bash
python narrative_break_signal.py --list-components
```

Run the interactive questionnaire:

```bash
python narrative_break_signal.py
```

List the pre-classified starter scenarios:

```bash
python narrative_break_signal.py --list-scenarios
python narrative_break_signal.py --list-scenarios --show-scenario-details
```

### Daily signal review and calibration guardrail

Every active exact contract is recorded as an append-only evidence layer by
`signal_review.py`. Each observation stores the event ID, physical contract ID,
exact contract label, current probability, prior-day probability, one-day and
seven-day changes, the catalog fingerprint, and the definition version. A
user's daily rating is an annotation on that record; it cannot overwrite the
odds, contract identity, or rule-based oil read-through.

The daily market dashboard presents a dropdown for each exact contract and an
overall rating. Ratings are intentionally comparative—`Much more bullish`,
`More bullish`, `Unchanged`, `More bearish`, `Much more bearish`,
`Conflicted / mixed`, or `Insufficient evidence`—and are saved separately from
the raw evidence. Export the reviewed record after completing the dashboard so
later backtests can compare the user's judgment with subsequent market moves.
The objective one-day change uses the same Eastern cutoff on the prior day;
the seven-day chart remains anchored to the comparable 9:00 AM observations.

Classify one of the starter scenarios:

```bash
python narrative_break_signal.py --scenario question-2
```

Play the calibration quiz:

```bash
python narrative_break_signal.py --quiz
```

Classify a scenario directly:

```bash
python narrative_break_signal.py \
  --peace-talk-near-term down \
  --peace-talk-long-term stable \
  --blockade-near-term down \
  --blockade-long-term stable \
  --shipping-risk flat \
  --wti-upside-threshold slightly_up
```

The calibrated Question 2 rule is stored as Yellow/Orange:

```text
Near-term peace-talk odds fall
+ near-term blockade odds fall
+ long-dated blockade odds stay stable
+ shipping-risk markets stay flat
+ WTI upside-threshold odds are only slightly higher
= Yellow/Orange timing-risk warning
```

Stable long-dated odds and flat shipping markets keep it below Orange, but the
paired near-term drop in peace-talk and blockade odds may reflect a meaningful
near-term development from outside the included model signals.

## Test

```bash
python -m unittest discover -s tests -v
```

## Data sources

- [Gamma event-by-slug API](https://docs.polymarket.com/api-reference/events/get-event-by-slug)
- [CLOB price-history API](https://docs.polymarket.com/api-reference/markets/get-prices-history)
