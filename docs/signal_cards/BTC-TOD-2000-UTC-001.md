# BTC-TOD-2000-UTC-001 — BTC 20:00 UTC timing effect

## Decision

**Lifecycle:** Backtest complete; frozen for observation  
**Operational status:** Dormant research candidate  
**Capital right:** None  
**Real-money authorization:** False  
**Priority:** Low until reactivation criteria pass

S-010 is complete for the current research cycle. The project will not add more filters, optimize the hour, tune the holding period, or create a live trading rule from the present evidence.

## Canonical hypothesis

A scheduled BTC long entered at **20:00 UTC** has unusually favorable forward returns and is unusually close to a surrounding local low relative to entries at other UTC hours.

The frozen forward horizons are 1, 2, 4, 8, 12, 24, 48, 96 and 168 hours. The neighboring 19:00 and 21:00 UTC tests are robustness checks. The all-hour and weekday matrices are exploratory and cannot rewrite the 20:00 UTC hypothesis.

## Data and test

- Instrument: Binance BTCUSDT spot
- Data: public one-hour Binance archive klines
- Historical sample: January 2024 through June 2026
- Corrected bar count: 21,888 consecutive hourly bars
- Missing-hour gaps: zero
- Round-trip cost assumption: 14 basis points
- Entry: scheduled hourly open
- Local-low proximity: non-causal diagnostic only

## Evidence summary

### Full history

The broad local-bottom claim was not supported. The 20:00 UTC price was near the middle of its surrounding 24-hour range, not persistently near the low.

The hour ranked relatively well at some 2–12-hour horizons, but expected returns generally failed to clear the frozen cost assumption. Multiday positive returns were not unique enough to 20:00 UTC to establish a useful timing edge.

### Recent windows

The latest 7-, 14-, 21- and 30-day windows showed strong relative rankings at 1–12-hour horizons. The effect weakened over 60- and 90-day windows and did not establish that 20:00 UTC was the actual local bottom.

The supported interpretation is narrower than the source claim:

> 20:00 UTC may occasionally become a short-horizon relative-strength entry window during a temporary regime, but it is not a durable unconditional BTC local-bottom rule.

## Applicable regime

Potentially applicable only when recent 20:00 UTC observations show repeated short-horizon outperformance relative to all other hours.

## Invalid regimes and failure modes

- no cross-hour relative outperformance;
- apparent profitability caused only by broad BTC drift;
- the result fails after realistic costs;
- the hour is selected retrospectively from the 24-hour matrix;
- fewer than 20 independent daily observations;
- a crypto-specific event dominates the sample;
- changing the entry hour or exit horizon after viewing outcomes.

## Confidence

**Current confidence: Preliminary / low.**

Reasoning:

- the source observation was testable;
- the recent pattern appeared in adjacent short windows;
- full-history evidence did not support the stronger local-bottom claim;
- cost-adjusted performance was weak;
- the recent sample was small and highly regime-sensitive;
- no untouched prospective confirmation exists.

## Why research stops here

Further historical refinement would have high overfitting risk and low expected project value. The current result is sufficiently understood to classify:

- not a production signal;
- not a high-upside discovery-tier signal;
- potentially useful later as a conditional timing feature;
- lower priority than testing independent candidates with a credible path to a 25% or greater conditional improvement over their baseline.

## Reactivation rule

Reopen S-010 only after at least **90 additional calendar days** of untouched data are available and at least one of the following is true:

1. 20:00 UTC ranks in the top six of 24 entry hours at the 2-, 4-, 8- and 12-hour horizons over both the latest 30-day and 90-day windows;
2. its cost-adjusted mean exceeds the cross-hour mean by at least 25% of the cross-hour return dispersion at three adjacent horizons;
3. an independent mechanism is documented before reviewing the new outcomes;
4. S-010 becomes an input to a broader model and demonstrates material out-of-sample incremental value.

Reactivation does not permit changing the canonical hour or selecting the best historical exit. Any such change creates a new candidate.

## Next project action

Move research capacity to independent, high-upside candidates. The immediate priority is a candidate with a credible path to at least a **25% conditional improvement** in forecast error, risk-adjusted performance, or tail-loss control over a predeclared baseline.
