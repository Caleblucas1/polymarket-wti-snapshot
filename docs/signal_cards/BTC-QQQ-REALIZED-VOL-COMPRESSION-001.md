# S-012 — Bitcoin realized-volatility compression below QQQ

## Decision

**Lifecycle:** Backtest complete  
**Operational status:** Prospective shadow watchlist  
**Confidence:** 47/100 — promising but unconfirmed  
**Capital right:** None  
**Real-money authorization:** False

The canonical signal earned the right to be monitored prospectively, but it did **not** earn production status or capital influence. Historical performance is encouraging; the independent sample and untouched evidence are not yet sufficient.

## Source and fidelity boundary

The candidate comes from the Venture Coinist X post and the supplied TradingView chart comparing Bitcoin and QQQ 30-day realized volatility. The chart marks several historical BTC buying areas near periods when BTC realized volatility fell to or below QQQ realized volatility.

The chart is evidence for candidacy, not proof. It does not expose machine-readable marker timestamps or indicator source code, so the repository independently tests the frozen rule and does not claim exact reproduction of every source marker.

## Frozen canonical rule

- Compute close-to-close log-return realized volatility over the preceding 30 calendar days.
- Annualize BTC with `sqrt(365)` and QQQ with `sqrt(252)`.
- Compare the series only after the regular QQQ close.
- Use only QQQ adjusted closes and completed BTC UTC daily closes available by the decision timestamp.
- Trigger on a fresh crossover from BTC realized volatility greater than or equal to QQQ realized volatility to strictly below it.
- Re-arm only after BTC realized volatility returns to greater than or equal to QQQ realized volatility.
- Enter the research return calculation at the first completed BTC UTC close after the decision.
- Subtract 20 basis points round trip.
- Direction: long BTC spot proxy; no leverage.

Frozen exits are 30, 90, 180 and 365 calendar days. A recross exit is scored separately and cannot replace the primary horizon after the result is known.

## Sample integrity

- Comparable observations: **2,968**
- Canonical fresh crossovers: **11**
- Development segment: through **2021-12-31**
- Source-exposed historical validation: **2022-01-01 through 2026-08-03**
- Untouched prospective boundary: **2026-08-04**

The chart already displayed historical examples, so no pre-boundary observation is represented as truly untouched. In addition, several crossover events occur close together and their holding periods overlap. The repository preserves all 11 events descriptively but uses greedily selected nonoverlapping episodes for the primary inference.

## Primary 90-day result

### All fresh crossovers — descriptive

- Events: **11**
- Mean after-cost return: **50.86%**
- Median after-cost return: **33.64%**
- Hit rate: **90.9%**
- Calendar-year and source-exposure-matched null mean: **23.22%**
- Relative improvement versus the absolute matched mean: **119.0%**

This is not the primary independent-sample estimate because some holding windows overlap.

### Nonoverlapping episodes — primary inference

- Events: **6**
- Mean after-cost return: **34.22%**
- Median after-cost return: **32.69%**
- Hit rate: **83.3%**
- Matched-null expected mean: **19.24%**
- Absolute edge: **14.98 percentage points**
- Relative improvement versus the absolute matched mean: **77.9%**
- One-sided matched-null probability of an equal-or-better mean: **21.7%**
- Worst maximum adverse excursion: **−50.0%**
- Worst path drawdown: **−50.4%**

The rule clears the project's predeclared 25% conditional-improvement target historically. It does not clear a conventional evidentiary bar for production: six independent episodes are too few, and the downside path can be extreme.

### Source-exposed validation episodes

After overlap control, only two episodes remain: **2022-10-21** and **2025-04-09**.

- Mean after-cost return: **20.76%**
- Hit rate: **100%**
- Matched-null expected mean: **−6.42%**
- Relative improvement versus the absolute matched mean: **423.3%**
- One-sided matched-null probability: **8.1%**

This is supportive but fragile. Two source-exposed episodes are not independent proof and are not untouched out-of-sample evidence.

## Other frozen horizons

Using nonoverlapping events:

| Horizon | Events | Mean after-cost return | Hit rate | Matched-null mean | Relative improvement |
|---|---:|---:|---:|---:|---:|
| 30 days | 7 | 14.63% | 71.4% | 5.40% | 171.0% |
| 90 days | 6 | 34.22% | 83.3% | 19.24% | 77.9% |
| 180 days | 6 | 119.82% | 83.3% | 56.05% | 113.8% |
| 365 days | 5 | 256.51% | 80.0% | 97.67% | 162.6% |

These horizons are correlated and cannot be treated as four independent confirmations.

## Recross exit

The volatility recross exit was not useful enough to promote:

- Mean after-cost return: **0.32%**
- Median after-cost return: **−0.66%**
- Hit rate: **45.5%**
- Bootstrap 95% mean interval: approximately **−3.46% to 4.04%**

The fixed 90-day horizon remains the predeclared primary test. No exit is reselected after the result.

## Current prospective state

As of the first post-boundary record:

- Latest comparable decision date: **2026-08-03**
- BTC realized volatility: **29.46%**
- QQQ realized volatility: **24.11%**
- BTC/QQQ volatility ratio: **1.222**
- BTC below QQQ: **No**
- Regime proxy: **bear contraction**
- Status: **armed and waiting for a fresh crossover**
- Untouched prospective events: **0**

The weekday workflow updates the shadow ledger automatically. It observes and scores the frozen rule; it cannot place orders.

## Confidence update

Confidence moves from **42/100 to 47/100**.

It rises because the rule is causal, reproducible, cost-aware, historically positive and directionally stable across several episodes. It remains below production quality because:

- there are only six nonoverlapping 90-day historical episodes;
- only two are in the source-exposed validation segment;
- there are no untouched prospective outcomes;
- the worst historical adverse excursion is about 50%;
- the mechanism is plausible but not uniquely identified;
- the source image cannot be exactly reconstructed marker-for-marker.

## Production gate

A production review cannot begin until all frozen requirements pass, including:

- at least **10 untouched prospective nonoverlapping trigger outcomes**;
- positive 90-day after-cost edge of at least 25% versus the frozen matched benchmark;
- evidence in more than one predeclared regime;
- stable data and execution behavior;
- an explicit review of adverse excursion, decay risk and implementation costs.

Passing that gate would permit a review, not automatic live authorization.

## Enhancements held back

Optimized lookbacks, volatility-ratio weighting, z-scores, macro filters, ETF-flow filters, ETH/SOL generalization and ensembles remain separate future candidates. They cannot rewrite the canonical S-012 record.

## Durable records

- Frozen hypothesis: `signal_research/hypothesis_extensions/S-012-BTC-QQQ-RV.json`
- Registry record: `signal_research/registry_extensions/S-012-BTC-QQQ-RV.json`
- Backtest program: `signal_research/backtest_s012_btc_qqq_rv.py`
- Conservative overlap audit: `signal_research/audit_s012_btc_qqq_rv.py`
- Durable result: `signal_research/results/S-012-BTC-QQQ-RV-RESULT.json`
- Prospective ledger: `signal_records/live/S-012-BTC-QQQ-RV-SHADOW.json`
- Workflow artifact run: `30868542744`

**Governing rule:** Canonical before enhanced.
