# Signal research engine

This layer turns social-media observations into falsifiable, cost-aware trading
research. It does **not** promote an idea because it is intuitive, correlated in
one chart, or profitable after retrospective optimization.

## Lifecycle

Every idea has one explicit stage:

1. **Candidate** — source captured; claim may still need exact extraction.
2. **Hypothesis** — predictor, target, timing, direction and invalidation are fixed.
3. **Backtest** — rules are frozen and evaluated with costs, benchmarks, regimes
   and a held-out sample.
4. **Production** — live observations are recorded without rewriting history.
5. **Retired** — the edge failed, decayed, became untradeable, or lost data support.

Promotion is evidence-based. A production signal can move backward or be retired.

## Canonical before enhanced

Each signal starts with the simplest defensible specification. Enhancements such
as adaptive thresholds, optimized basket weights, Bayesian ensembles or machine
learning are isolated until the canonical rule demonstrates out-of-sample value.
This prevents complexity from manufacturing an apparent historical edge.

For S-009, volatility adjustment and all four rebound tests are canonical because
they define a fair cross-asset comparison. A volatility-weighted aggregate basket
is explicitly deferred. The first version compares component and basket stage
timestamps without learned or hand-tuned asset weights.

## Required research record

A complete backtest should preserve:

- source URL and first-public timestamp;
- exact observable predictor and executable entry timestamp;
- target asset, direction, horizon and exit;
- benchmark and transaction-cost model;
- applicable and invalid regimes;
- economic or market-microstructure mechanism;
- expected decay mechanism;
- in-sample and untouched out-of-sample boundaries;
- every trade, including ambiguous and losing observations;
- data revisions, exclusions and reasons;
- overall and regime-level metrics.

Correlation is descriptive. A tradable signal must add predictive value after the
information time, benchmark return, spread, fees, slippage, financing and borrow.

## S-009 canonical rebound definition

For each asset, using only prices available at the decision timestamp:

1. **Local-low reversal** — price advances a configured multiple of its own recent
   realized volatility from the post-shock low.
2. **Reference reclaim** — price retakes the predeclared shock reference, such as
   pre-dip price or event VWAP.
3. **Trend confirmation** — current price is above a short moving average and that
   average is rising.
4. **Sustained recovery** — price remains materially above the low for a fixed
   number of bars and continues upward.

The volatility lookback is constrained to 2–30 bars. Research should predeclare
whether a bar is hourly, four-hour, or daily; switching bar size after viewing the
outcome is optimization.

Scores map to stages:

- 0: none
- 1: early
- 2: provisional
- 3: confirmed
- 4: full

Compare first-stage timestamps for BTC, ETH, SOL and HYPE against ES/SPY, NQ/QQQ,
a MAG-7 basket and a semiconductor basket. Use equity-index futures for overnight
comparisons so 24/7 crypto trading is not mistaken for predictive leadership.
Analyze common macro shocks separately from crypto-specific and equity-specific
shocks.

## Confidence

`signal_research.confidence.confidence_score` produces a conservative 0–100 score
from sample size, out-of-sample observations, out-of-sample Sharpe, regime
coverage, data quality, implementation costs versus gross edge, and decay risk.
It is a prioritization tool—not a replacement for the underlying evidence.
Missing data lowers confidence.

## Commands

```bash
python signal_cli.py list
python signal_cli.py show S-009
python signal_cli.py rebound \
  --prices 100,99,98,98.3,98.8,99.4,100.2,101 \
  --reference 100 \
  --lookback 5 \
  --sustain-bars 3
python signal_cli.py confidence \
  --sample-size 200 \
  --oos-trades 80 \
  --oos-sharpe 1.1 \
  --regime-coverage 0.7 \
  --gross-edge-bps 12 \
  --cost-bps 3 \
  --decay-risk 0.25 \
  --data-quality 0.9
python signal_cli.py backtest --input trade_results.json
```

The backtest input is a JSON array whose rows contain the `TradeResult` fields in
`signal_research/backtest.py`. Output includes overall, out-of-sample and
regime-level results.

## Current limitations and next evidence tasks

This PR builds the durable research framework and formalizes the supplied
candidates. It does not claim that any candidate is profitable. External market
history and complete public-post history still need to be collected under
reproducible data-source rules.

Priority order:

1. Collect and classify S-009 common-shock episodes without looking at subsequent
   recovery order.
2. Reconstruct all public AAPL campaigns for S-003, counting campaigns rather
   than scaled entries.
3. Reconstruct S-008 timing precisely and test the claimed regime break and
   post-break decay.
4. Backtest S-005, S-006 and S-007 with frozen rule variants and held-out periods.
5. Complete exact source extraction and event-universe rules for S-001 before
   advancing it from Candidate.

Signal IDs S-002 and S-004 are reserved because the conversation's working labels
were superseded by the fully specified S-006 and S-007 records. They are not
separate hypotheses and must not be double-counted.

No weighted aggregate should be added to S-009 until the canonical signal shows
incremental out-of-sample predictive value.
