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

No real order is submitted. The shadow execution price is the earliest public Binance aggregate trade at or after the frozen timestamp within a 60-second search window. When no aggregate trade is returned, the collector uses the open of the one-minute kline beginning at the frozen timestamp.

This is a reproducible research proxy. It is not a claim that a real market order would have filled at exactly that price.

## Costs

The cost schedule was frozen before the result was observed:

- assumed taker fee: 5 basis points per side;
- assumed slippage: 2 basis points per side;
- assumed round-trip execution cost: 14 basis points;
- funding: every public Binance funding-rate observation and its mark price during the holding interval.

The fee and slippage assumptions are intentionally conservative and standardized. They do not represent a particular user's account tier.

## Automation

The GitHub workflow runs:

- when the implementation is merged into `main`;
- daily at 00:10 UTC;
- manually through `workflow_dispatch`;
- during pull-request review as a non-committing live integration test.

Every run:

1. verifies the BTCUSDT contract is a trading perpetual;
2. backfills the frozen entry if needed;
3. appends any missing 00:05 UTC daily marks;
4. refreshes funding observations;
5. calculates gross, funding and assumed after-cost performance;
6. closes the record at the exact August 8 timestamp;
7. uploads the complete record as a workflow artifact;
8. commits changed scheduled observations to `main`.

## Durable files

```text
signal_research/live_tests/FLOW-MON-BTC-2026-08.json
signal_research/live_flow_mon_btc.py
signal_records/live/FLOW-MON-BTC-2026-08.json
.github/workflows/live-flow-mon-btc-aug-2026.yml
tests/test_signal_live_flow_mon_btc.py
```

## Interpretation rules

The final result must keep these questions separate:

1. Did Bitcoin rise or fall over the seven-day interval?
2. Did the observation remain positive after funding and frozen execution costs?
3. Is one month meaningful evidence of a repeatable calendar effect?

A profitable August observation would not validate the signal by itself. A losing observation would not invalidate it by itself. It becomes one untouched observation in the future sample and earns no real-money capital rights.
