# Superforecasting operating standard

## Purpose

This standard converts the practical lessons of Philip E. Tetlock and Dan Gardner's *Superforecasting: The Art and Science of Prediction* into enforceable habits for the Signals project and the Polymarket forecasting workflow.

The book is an input to the process, not an authority that overrides evidence. We will track whether these practices actually improve our forecasts.

## Core principles

1. **Make forecasts precise and resolvable.** Replace vague language with a probability, target, horizon, resolution rule, and information cutoff.
2. **Start with the outside view.** Record a relevant base rate or reference class before applying case-specific evidence.
3. **Decompose hard questions.** Break a forecast into smaller drivers, estimate them separately, and document how they combine.
4. **Think like a fox, not a hedgehog.** Use multiple models and sources; do not force every event into one grand theory.
5. **Update frequently but proportionally.** Record every probability change, the new evidence, and why the size of the update is justified.
6. **Actively seek disconfirming evidence.** Every forecast must name what would make it wrong and where contrary evidence could appear.
7. **Separate confidence from conviction.** Strong narratives do not substitute for calibration, sample size, or track record.
8. **Keep score.** Use Brier scores for binary questions, proper scoring for multi-outcome questions, calibration buckets, and benchmark comparisons.
9. **Conduct postmortems without hindsight rewriting.** Preserve the original forecast and identify whether error came from the base rate, evidence, model, timing, resolution rule, or execution.
10. **Aggregate diverse judgments carefully.** Compare independent forecasts before discussion where practical, then record the combined estimate and the reason for any extremizing.
11. **Match confidence to forecastability.** Shorter-horizon, clearly resolvable questions deserve more precise estimates than distant or poorly defined questions.
12. **Treat forecasting as a skill that compounds.** Track process quality as well as outcomes and revise the process when repeated errors appear.

## Required forecast record

Every forecast that enters either project must contain:

- stable forecast ID and project (`signals` or `polymarket`);
- question stated so that an external reviewer can resolve it;
- target asset or event and forecast horizon;
- initial probability or numerical forecast;
- information cutoff and first-public timestamp;
- resolution source and mechanical resolution rule;
- relevant base rate/reference class;
- decomposed drivers and their current directional effects;
- strongest supporting evidence;
- strongest disconfirming evidence;
- alternative scenarios;
- market regime and asset-class applicability;
- update history with evidence and probability deltas;
- benchmark forecast;
- final outcome and score;
- postmortem classification.

A forecast without these fields may remain a research note, but it must not be counted in performance statistics.

## Signals-project integration

For each signal candidate:

- distinguish the **signal hypothesis** from the **forecast produced by the signal**;
- compare the signal forecast with a base-rate-only benchmark and the current project ensemble;
- store predictions prospectively before outcomes are known;
- score overall and by predeclared regime and asset class;
- test whether the signal improves Brier score, forecast error, timing, drawdown, or another frozen metric;
- do not promote a signal because it explains the past convincingly;
- preserve failed forecasts and contradictory evidence in the evidence ledger;
- update signal confidence only from evidence available at the recorded timestamp.

A signal's forecast contribution should be represented as an explicit probability or expected-return adjustment, not merely `bullish`, `bearish`, or `important`.

## Polymarket-project integration

Polymarket prices are a benchmark and evidence source, not automatically the project's forecast.

For every tracked market:

- save the market-implied probability at the information cutoff;
- record the project's independent probability before viewing later outcomes;
- record the difference between project probability and market probability;
- explain the base rate, decomposition, and evidence behind that difference;
- track subsequent project updates separately from market-price changes;
- score both the project forecast and the market benchmark at resolution;
- decompose whether any edge came from direction, timing, calibration, or interpretation of the resolution criteria.

For conditional markets, separately record:

1. probability of the conditioning event;
2. probability of the outcome conditional on that event;
3. expected market impact if the event occurs;
4. timing assumptions.

This prevents a low-probability, high-magnitude event from being treated as either irrelevant or certain.

## Scoring

### Binary forecasts

Use Brier score:

```text
Brier = (forecast_probability - outcome)^2
```

where the outcome is `1` if YES and `0` if NO. Lower is better.

Report:

- project Brier score;
- market or base-rate benchmark Brier score;
- relative improvement versus the benchmark;
- calibration by probability bucket;
- sharpness, sample size, and regime breakdown.

### Numerical market forecasts

For price or return forecasts, freeze the metric before forecasting. Suitable primary metrics include absolute error, squared error, directional accuracy, or log score for a full distribution. Always compare against a naive benchmark such as no-change, historical mean, or current futures curve.

### Improvement claim

A statement such as `25% improvement` is valid only when it specifies:

- metric;
- benchmark;
- horizon;
- sample;
- regime;
- asset class;
- in-sample versus out-of-sample status.

## Update discipline

Every probability update must record:

- timestamp;
- old probability;
- new probability;
- evidence that arrived since the prior update;
- whether the evidence was expected;
- whether the update changes the regime classification;
- whether the market price moved first.

Large updates require correspondingly strong evidence. Failure to update after meaningful evidence is also a process error.

## Postmortem taxonomy

Classify errors using one or more of:

- wrong or missing base rate;
- poor decomposition;
- evidence-quality failure;
- underreaction;
- overreaction;
- confirmation bias;
- regime misclassification;
- timing/horizon error;
- resolution-rule misunderstanding;
- data leakage or look-ahead bias;
- model or signal failure;
- execution/cost failure;
- irreducible surprise.

Postmortems must not rewrite the original forecast or imply that an outcome was obvious after it occurred.

## Process scorecard

In addition to outcome accuracy, track whether each forecast:

- had a valid resolution rule;
- used an explicit base rate;
- contained a decomposition;
- recorded contrary evidence;
- was updated when material information arrived;
- preserved an immutable history;
- was scored against a benchmark;
- received a postmortem after resolution.

The project should review both forecast accuracy and process compliance monthly.

## Book-principle tracking

Implementation status is stored in:

```text
forecast_records/superforecasting_principles.json
```

Forecast records should follow:

```text
forecast_records/forecast_record_template.json
```

This standard summarizes and operationalizes the book's ideas in original language. It is not a substitute for reading the book and does not reproduce its text.