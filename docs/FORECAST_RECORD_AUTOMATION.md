# Forecast record automation

This layer turns the forecasting operating standard into executable controls.

## What is enforced

For every `open`, `resolved`, or `void` record, the validator requires:

- a precise question, target, horizon, information cutoff, and UTC timestamps;
- an external resolution source and mechanical resolution rule;
- a probability or numerical estimate with a frozen benchmark;
- an outside-view reference class and base rate;
- at least one decomposed driver;
- supporting evidence, disconfirming evidence, and an alternative scenario;
- declared regimes, asset classes, and invalidating conditions;
- chronological append-only updates whose old value matches the prior estimate;
- a valid scoring metric;
- preservation of the original forecast history;
- continued prohibition on real-money authorization.

Draft records may be incomplete, but they are excluded from performance statistics.
Polymarket records additionally require the market slug, the market probability at
the information cutoff, and the exact project-minus-market divergence.

## Automatic scoring

When a valid record is marked `resolved`, the scoring engine uses the latest
prospectively timestamped estimate before resolution.

Binary forecasts use Brier score:

```text
(project_probability - outcome)^2
```

Numerical forecasts currently support absolute error and squared error. Every score
is compared with the benchmark frozen in the original record. If a comparable
Polymarket probability is present, the report also computes project-versus-market
Brier performance.

Relative improvement is:

```text
(benchmark_score - project_score) / benchmark_score
```

It is left undefined when the benchmark score is zero rather than manufacturing an
infinite improvement claim.

## Reports

The report command produces JSON and Markdown containing:

- validation errors and warnings;
- status and project counts;
- project and benchmark scores;
- relative improvement;
- calibration buckets for project probabilities;
- separate calibration buckets for Polymarket probabilities;
- project-versus-Polymarket Brier comparison;
- breakdowns by project, declared market regime, and asset class;
- process-compliance rates for base rates, decomposition, contrary evidence,
  immutable history, benchmarks, and postmortems.

A report with no records is valid and explicitly states that no forecasts have yet
been scored. This avoids filling the system with invented retrospective forecasts.

## Commands

```bash
python forecast_records/forecasting.py validate \
  --records forecast_records/records

python forecast_records/forecasting.py score \
  --records forecast_records/records \
  --output artifacts/forecast_scores.json

python forecast_records/forecasting.py report \
  --records forecast_records/records \
  --json-output artifacts/forecast_accuracy_report.json \
  --markdown-output artifacts/forecast_accuracy_report.md
```

## Continuous integration

`.github/workflows/forecast-records.yml` compiles the tool, runs unit tests,
validates all prospective records, generates both reports, and uploads the outputs
as a 90-day workflow artifact. Invalid open or resolved records fail the pull
request check.

## Prospective-record rule

The automation deliberately does not create a live forecast from an old narrative.
A live record begins only after its probability or value, benchmark, cutoff,
horizon, and resolution rule have been supplied before the outcome is known. This
keeps the score honest and protects the project from hindsight reconstruction.
