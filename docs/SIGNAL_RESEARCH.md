# Signal research engine

This layer turns social-media observations into falsifiable, cost-aware trading
research. The governing standard is
[`docs/SIGNAL_GOVERNANCE.md`](SIGNAL_GOVERNANCE.md).

The project asks:

> Can this signal earn and keep the right to influence capital allocation?

An idea does not advance because it is intuitive, correlated in one chart, or
profitable after retrospective optimization.

## Lifecycle and linked records

Every signal moves through Candidate, Hypothesis, Backtest, Production and
Retired. Definition, evidence, performance and live status are stored
separately and linked by the thematic `registry_id`.

`signal_candidates.json` is the definition registry.
`signal_records/evidence_ledger.jsonl` and
`signal_records/confidence_history.jsonl` are append-only audit records.
`signal_records/performance_history.json` starts empty until a frozen rule
produces reproducible outcomes. `signal_records/live_status.json` states whether
a signal may influence research, paper trades or live capital.

## Canonical before enhanced

Each signal starts with the simplest defensible specification. Enhancements such
as adaptive thresholds, optimized basket weights, Bayesian ensembles or machine
learning remain isolated until the canonical rule demonstrates out-of-sample
value.

For `CROSS-ASSET-REBOUND-001` (legacy `S-009`), volatility adjustment and all
four rebound tests are canonical. A volatility-weighted aggregate is deferred.

For `FLOW-MON-BTC-001` (legacy `S-010`), symmetric short-then-long and long-only
month-boundary rules must be frozen before conditional leverage filters are
evaluated.

## Required backtest record

A complete backtest preserves source time, observable predictor, executable
entry, exit, benchmark, costs, regimes, mechanism, decay, in-sample and
out-of-sample boundaries, every trade, exclusions and data versions.

Correlation is descriptive. A tradable signal must add predictive value after
the information time, benchmark return, spread, fees, slippage, financing and
borrow.

## S-009 canonical rebound definition

For each asset, using only prices available at the decision timestamp:

1. Local-low reversal.
2. Reference reclaim.
3. Trend confirmation.
4. Sustained recovery.

The realized-volatility lookback is constrained to 2–30 bars. Compare first
stage timestamps for BTC, ETH, SOL and HYPE against ES/SPY, NQ/QQQ, a MAG-7
basket and a semiconductor basket. Use equity-index futures for overnight
comparisons.

## Confidence

`signal_research.confidence.confidence_score` calculates an empirical score from
completed research evidence. The registry's transparent component score is an
early-stage prioritization and governance score. Neither is the probability of
the next trade succeeding.

## Commands

```bash
python signal_cli.py list
python signal_cli.py show FLOW-MON-BTC-001
python signal_cli.py gate FLOW-MON-BTC-001
python signal_cli.py families
python signal_cli.py validate
python signal_cli.py rebound --prices 100,99,98,98.3,98.8,99.4,100.2,101 --reference 100 --lookback 5 --sustain-bars 3
python signal_cli.py backtest --input trade_results.json
```

The framework does not claim that any current candidate is profitable. No
current signal has passed the Production gate.
