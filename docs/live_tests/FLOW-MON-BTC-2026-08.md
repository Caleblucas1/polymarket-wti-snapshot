# FLOW-MON-BTC August 2026 live shadow

## Why this test exists

The frozen canonical `FLOW-MON-BTC-001` hypothesis says to enter a long Binance BTCUSDT perpetual shadow position at 00:05 UTC on the first calendar day of a month and exit at 00:05 UTC on the eighth day.

August 1, 2026 is the canonical out-of-sample boundary. This test therefore starts at the first possible untouched monthly boundary rather than reconstructing an older month after seeing its return.

## Frozen test

- **Live test ID:** `FLOW-MON-BTC-2026-08`
- **Instrument:** Binance USD-M BTCUSDT perpetual
- **Direction:** long
- **Entry:** 2026-08-01 00:05 UTC
- **Exit:** 2026-08-08 00:05 UTC
- **Daily mark:** 00:05 UTC
- **Quantity:** one BTC, normalized shadow accounting
- **Leverage:** 1x
- **Real-money trading:** prohibited

The test succeeds by collecting the observation honestly. Positive performance is not required.

## Execution proxy

No real order is submitted. The shadow execution price is the earliest public Binance aggregate trade at or after the frozen timestamp within a 60-second search window. When the REST API is available but returns no eligible aggregate trade, the collector uses the open of the one-minute kline beginning at the frozen timestamp.

The U.S.-hosted GitHub Actions runner received HTTP 451 from Binance's futures REST API. The project did not switch exchanges, alter the entry time or substitute an approximate market price. It added a disclosed data-access fallback to Binance's official public-data archive. The archive collector selects the earliest aggregate trade at or after the identical frozen timestamp and stores both the archive ZIP hash and the selected row hash.

Because the finalized daily archive is published after the relevant UTC day, the repository may remain in `awaiting_official_archive` or `open_archive_lagged` status. That is a publication delay, not a change to the economic observation.

This is a reproducible research proxy. It is not a claim that a real market order would have filled at exactly that price.

## Operational amendment

The archive fallback was recorded after the API-access failure and before an entry price was observed. The durable configuration states that:

- no outcome information was used;
- the entry price was still unknown;
- the signal rule did not change;
- the cost model did not change;
- the venue, instrument and frozen timestamps did not change.

This distinction matters. Operational resilience is allowed; retrospective strategy revision is not.

## Costs

The cost schedule was frozen before the result was observed:

- assumed taker fee: 5 basis points per side;
- assumed slippage: 2 basis points per side;
- assumed round-trip execution cost: 14 basis points;
- funding: each public Binance funding-rate observation and its mark price during the holding interval.

When the funding record is not yet available from an official source, the collector marks funding incomplete and withholds the final after-cost estimate. It does not silently assume zero funding.

The fee and slippage assumptions are intentionally conservative and standardized. They do not represent a particular user's account tier.

## Automation

The GitHub workflow runs:

- when the implementation is merged into `main`;
- daily at 06:30 UTC, after the prior UTC day's archive is more likely to be available;
- manually through `workflow_dispatch`;
- during pull-request review as a non-committing integration test.

Every run:

1. attempts the Binance futures REST API first;
2. records any restricted-location response explicitly;
3. falls back only to Binance's official archive for the same venue and timestamps;
4. backfills the frozen entry when the finalized file becomes available;
5. appends missing 00:05 UTC daily marks with archive and row hashes;
6. leaves funding and final after-cost performance pending until official funding observations are available;
7. closes the price record at the frozen August 8 timestamp after its archive is published;
8. uploads the complete record as a workflow artifact;
9. commits changed scheduled observations to `main`.

## Current state

The first successful live workflow recorded:

```text
status: awaiting_official_archive
pending timestamp: 2026-08-01T00:05:00Z
live API status: restricted_location_http_451
entry price: not yet observed
```

This is the honest state on the same UTC day as entry. The system has armed and preserved the test, but it cannot report the entry price until Binance publishes the official daily archive.

## Durable files

```text
signal_research/live_tests/FLOW-MON-BTC-2026-08.json
signal_research/live_flow_mon_btc.py
signal_research/live_flow_mon_btc_resilient.py
signal_records/live/FLOW-MON-BTC-2026-08.json
.github/workflows/live-flow-mon-btc-aug-2026.yml
tests/test_signal_live_flow_mon_btc.py
tests/test_signal_live_flow_mon_btc_resilient.py
```

## Interpretation rules

The final result must keep these questions separate:

1. Did Bitcoin rise or fall over the seven-day interval?
2. Did the observation remain positive after funding and frozen execution costs?
3. Is one month meaningful evidence of a repeatable calendar effect?

A profitable August observation would not validate the signal by itself. A losing observation would not invalidate it by itself. It becomes one untouched observation in the future sample and earns no real-money capital rights.
