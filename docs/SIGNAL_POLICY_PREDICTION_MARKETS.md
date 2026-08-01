# Prediction-market inputs for pre-passage policy alpha

## Purpose

The canonical `POLICY-US-LEGISLATION-001` signal begins with just-passed legislation because final congressional passage and public operative text can be timestamped objectively.

The project also preserves a future pre-passage extension. When a suitable Polymarket contract exists, its deadline-specific probability may be used as one prospective input for estimating whether and how soon legislation may pass.

This extension remains blocked and research-only. It does not authorize real-money trading.

## What a Polymarket price means

A contract price represents the market-implied probability of the contract's exact resolution condition by its stated deadline. It is not automatically an expected passage date.

For example, the following events are different and must never be treated as interchangeable:

- passage in the House;
- passage in the Senate;
- final passage of identical text by both chambers;
- presidential signature;
- enactment or implementation by a specified deadline.

The resolution wording, deadline, timezone and source must match the legislative milestone used by the policy-alpha hypothesis.

## Passage-probability term structure

When comparable contracts exist for several deadlines, preserve all of them. The resulting probability-by-deadline curve can provide a passage-probability term structure.

That structure may later support calculations such as:

- incremental probability between deadlines;
- conditional probability of passage in a later interval, given no earlier passage;
- an approximate passage hazard;
- changes in the curve after votes, amendments or leadership announcements.

These calculations are only valid when the underlying contract definitions are comparable. A House-passage contract and a presidential-signature contract do not form one coherent term structure.

## Required market-quality checks

The research system must archive:

- market, condition and event identifiers;
- full question, description and resolution rules;
- resolution milestone and source;
- deadline and snapshot timestamps in UTC;
- Yes bid, ask, midpoint and last-trade price;
- displayed probability;
- spread, liquidity and volume;
- active and accepting-orders status;
- exclusion or quality status.

The displayed probability alone is insufficient. Polymarket explains that displayed prices may use the bid-ask midpoint, or the last trade when the spread is wide; those values can differ from an executable entry. The CLOB bid and ask therefore matter for both signal quality and realistic costs.

## Role in the signal

Prediction-market information supplements, rather than replaces:

- official bill text;
- chamber schedules and vote notices;
- committee and leadership actions;
- amendment and reconciliation risk;
- fiscal or agency estimates;
- the pre-entry mapping from legislation to tradable exposures.

The Polymarket snapshot must exist before the policy-impact memo and entry decision are sealed. The probability may become one component of a future trigger, but it may not be the sole trigger.

## Canonical before enhanced

The current post-passage version remains the canonical test. The pre-passage version cannot freeze until the project defines:

- market discovery and contract matching;
- minimum liquidity and volume;
- maximum spread;
- a probability or probability-change trigger;
- multi-deadline term-structure calculations;
- treatment when no suitable market exists;
- weighting relative to official procedural evidence;
- stale-price and manipulation safeguards;
- exact memo and entry timing;
- an untouched out-of-sample boundary.

The machine-readable source of truth for this future input is `signal_research/policy_prediction_markets.json`.

## Public data interfaces

Polymarket's public Gamma API supports market discovery and metadata. Its public CLOB endpoints expose prices, spreads, order books and price history. The design record stores the official documentation locations used for the future implementation.
