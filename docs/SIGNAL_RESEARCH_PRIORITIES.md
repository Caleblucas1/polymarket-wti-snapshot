# Signal research priorities

## Decision

The project now distinguishes **research cleanliness** from **economic priority**.

The August 2026 `FLOW-MON-BTC-001` observation remains useful as a one-off test of live collection, immutable timestamps, official-archive recovery, costs and audit behavior. It is not important enough to justify automatic monthly successors or continued high-priority engineering.

`CROSS-ASSET-REBOUND-001` is the highest next research priority because it asks a more useful capital-allocation question:

> After a common risk-off shock, does crypto recover before U.S. equities strongly enough to justify earlier rotation into crypto exposure?

This reprioritization does not make the cross-asset signal live-ready. Priority determines what the project works on next; readiness determines whether an untouched live observation may begin.

## Priority 1: crypto versus equity rebound ordering

### Assets

Crypto:

- BTC
- ETH
- SOL
- HYPE

Equity comparisons:

- ES or SPY
- NQ or QQQ
- an explicitly frozen MAG-7 basket
- an explicitly frozen semiconductor basket

### Canonical rebound components

Every asset and basket must be evaluated with all four existing mechanical definitions:

1. local-low reversal;
2. pre-shock reference reclaim;
3. trend confirmation;
4. sustained recovery.

Recent volatility may use no more than 30 one-hour bars. The canonical comparison remains unweighted. A volatility-weighted aggregate may be developed separately, but it cannot replace, select or rewrite the canonical result.

### Why no live launch exists yet

The frozen canonical hypothesis remains blocked by four unresolved fields:

1. mechanical common-shock detector;
2. pre-shock reference-level rule;
3. maximum event horizon;
4. exact unweighted basket timestamp aggregation rule.

These fields must be fixed before an event occurs. Otherwise, the project could select a convenient dip, reference level, endpoint or basket rule after observing which market recovered first.

### Required implementation order

1. Freeze a common-shock detector that uses no recovery information.
2. Freeze reference levels for each asset and basket.
3. Freeze the event horizon and invalidation rules.
4. Freeze unweighted aggregation and ties.
5. Bind synchronized crypto and equity-futures data sources.
6. Prove with replay tests that every event and rebound timestamp uses only contemporaneously available information.
7. Run the untouched rebound-ordering study.
8. Only after ordering evidence exists, freeze separate 1-, 3- and 5-day trading translations with fees, spreads, slippage, funding and turnover.

The ordering study and a profitable trading strategy are different claims. Crypto recovering first does not automatically establish that buying it at that moment earns an after-cost return.

## Low priority: BTC first week of the month

The existing `FLOW-MON-BTC-2026-08` test will be completed honestly. It remains one untouched research observation and an infrastructure exercise.

After completion:

- `FLOW-MON-BTC-001` becomes dormant;
- no September 2026 or later successor is created automatically;
- no current result grants capital rights;
- no future month may be armed without an explicit priority amendment;
- the project must not describe the signal as directly measuring flows unless actual flow data are collected.

The validator scans the live-test directory and rejects any new `FLOW-MON-BTC-*` configuration other than the approved August 2026 observation.

## Machine-readable record

```text
signal_research/research_priorities.json
```

Validation and summary:

```bash
python -m signal_research.priorities --validate
```

Regression tests:

```bash
python -m unittest tests.test_signal_research_priorities -v
```

## Capital boundary

This decision changes research allocation only. It authorizes no real-money trading and does not grant the cross-asset signal permission to launch before its frozen blockers are resolved.
