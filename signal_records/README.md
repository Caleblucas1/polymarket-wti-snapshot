# Durable signal records

The daily signal dashboard writes one append-only JSONL observation to
`observations.jsonl` in this directory. Each record contains the exact
five-contract evidence used by the dashboard, the definition version, and a
catalog fingerprint.

The write is duplicate-safe by `observation_id`, which is the Eastern cutoff
timestamp. Re-running a report for the same cutoff does not add a second
observation. User ratings and notes are annotations on the observation and do
not rewrite its raw probabilities or rule definitions.

Independent prediction-market forecasts are stored separately in
`forecast_history.jsonl`. Each append-only forecast preserves:

- the observed market probability;
- the forecaster's best single-number probability;
- the plausible low and high range;
- a standardized confidence level;
- the computed edge versus the market;
- directional catalysts and missing evidence;
- the market identity, timestamp, and resolution deadline.

A changed forecast creates a new record rather than overwriting the old one.
`signal_research/forecasting.py` validates probability bounds, requires the
point estimate to sit inside the plausible range, computes the edge, and makes
writes duplicate-safe by `forecast_id`.

The generated HTML dashboard and its synthetic rendered data are separate
scratch artifacts; they do not belong in this directory.
