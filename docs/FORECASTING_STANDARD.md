# Probability forecast and calibration standard

## Purpose

Every prediction-market review should distinguish the market's price from the
forecaster's own judgment. A forecast is incomplete unless it records both the
number and the uncertainty around the number.

## Required fields

Each forecast record contains:

1. **Market probability** — the observed market price at the forecast timestamp.
2. **Independent probability** — the forecaster's best single-number estimate.
3. **Plausible range** — a low and high bound containing outcomes that remain
   reasonably defensible given current uncertainty.
4. **Confidence level** — low, moderate-low, moderate, moderate-high, or high.
5. **Edge** — independent probability minus market probability, in percentage points.
6. **Catalysts up and down** — observable developments that would change the estimate.
7. **Evidence needed** — missing information most likely to narrow the range or
   materially change the point estimate.
8. **Resolution criteria and source** — the frozen rule and authoritative data
   source that determine the outcome.
9. **Timestamp, contract identity, question, and resolution deadline** — enough
   information to score the forecast later without hindsight.

The point estimate and plausible range are different objects. A 12.5% point
estimate with a 5%-25% plausible range says the best estimate is 12.5%, while
acknowledging that discrete events could justify a much lower or higher number.

Confidence is also separate. It describes confidence in the quality and
stability of the estimate, not the probability that the event occurs.

## Validation rules

- All probabilities must be between 0% and 100%.
- The plausible range must contain the independent point estimate.
- Edge is computed, never entered manually.
- Forecasts are append-only. A changed view creates a new record; it does not
  overwrite the prior forecast.
- Market probabilities and independent estimates must preserve their sources.
- Resolution criteria and the authoritative resolution source are required.
- When a condition ID is unavailable, forecast identity includes the exact
  question and deadline so dated contracts on one event page cannot collide.
- The exact contract identifier should still be captured before the forecast is
  treated as completely linked to the market's raw contract data.
- Catalysts must be observable and directional. Narrative that cannot change the
  estimate is not a catalyst.

## Calibration after resolution

The system should score each resolved forecast with:

- Brier score for the independent point estimate;
- market Brier score at the same timestamp as a benchmark;
- forecast-versus-market improvement;
- plausible-range coverage;
- calibration by confidence level;
- average absolute edge and realized value by market, horizon, and regime.

A wide range is not automatically poor forecasting. The range should be judged
by coverage and usefulness: whether it captured genuine uncertainty without
being so wide that it offered no decision value.

## Initial live record

The first record is the August 31, 2026 Strait of Hormuz traffic-normalization
market:

- market probability: 15.5%, as stated by the user;
- independent point estimate: 12.5%, the midpoint of the agreed 10%-15% initial band;
- plausible range: 5%-25%;
- confidence: moderate-low;
- edge: -3.0 percentage points versus the market;
- resolution rule: YES if IMF PortWatch publishes a seven-day moving average of
  Strait of Hormuz Arrivals of Ships of at least 60 for any date through August 31.

The repository's existing market event ID and exact source URL are linked. The
August 31 condition identifier remains explicitly listed as missing evidence
rather than being guessed.

## Files

- `signal_research/forecasting.py` validates and appends forecasts.
- `signal_records/forecast_history.jsonl` is the append-only ledger.
- `tests/test_forecasting.py` protects the identity, rules, range, edge,
  confidence, and duplicate-safety requirements.
