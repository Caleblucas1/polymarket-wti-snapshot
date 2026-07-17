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

## Test

```bash
python -m unittest discover -s tests -v
```

## Data sources

- [Gamma event-by-slug API](https://docs.polymarket.com/api-reference/events/get-event-by-slug)
- [CLOB price-history API](https://docs.polymarket.com/api-reference/markets/get-prices-history)
