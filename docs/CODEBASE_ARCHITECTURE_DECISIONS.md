# Codebase architecture decisions

## Purpose

This document records the target architecture for the combined Signals and Polymarket forecasting platform. It is a governing design standard, not a request to rename or move every existing file immediately.

The migration must preserve working data pipelines, append-only histories, chart compatibility, and research reproducibility. Speed matters: document the boundary once, migrate code only when that area is actively changed, and avoid large reorganizations that do not improve decision quality.

## Governing constraints

1. **Candidate → Hypothesis → Backtest → Production** remains the signal lifecycle.
2. **Canonical before enhanced.** No adaptive weighting, ensemble, optimizer, or machine-learning layer may replace the simplest defensible version before that canonical version demonstrates value.
3. **Prospective forecasts only.** A forecast becomes countable only after its estimate, benchmark, information cutoff, horizon, and resolution rule are recorded before the outcome.
4. **Evidence is append-only.** Annotations, ratings, and later interpretations must not overwrite raw observations or earlier forecasts.
5. **Exact identity is preserved.** A Polymarket contract, physical condition, token, replacement instance, signal definition, and forecast record are separate objects.
6. **Production is not capital authorization.** In this repository, production means production-quality research and monitoring. Real-money authorization requires separate portfolio, execution, reconciliation, loss-limit, and emergency-stop controls.

## Target top-level structure

```text
apps/               User-facing commands and orchestration
core/               Reusable domain, scoring, validation, storage, and governance logic
signals/            One self-contained directory per signal
polymarket/         Exact-contract catalogs, collectors, lifecycle, and charts
forecast_records/   Forecast schemas, open records, resolved records, and reports
data/               Snapshots, ranges, lifecycle logs, hourly files, and artifacts
docs/               Governance, runbooks, architecture, and research documentation
tests/              Tests mirroring the source layout
.github/workflows/  Scheduled jobs and pull-request checks
```

## Architecture decisions

### ADR-001 — Every signal is self-contained

Each signal receives its own directory:

```text
signals/<signal_id>/
├── signal.yaml
├── hypothesis.md
├── backtest.py
├── live_monitor.py        # only when needed
└── results/
```

The directory must answer:

- What is the frozen canonical hypothesis?
- What information is available at decision time?
- What is the tradable asset or instrument?
- What are the entry, exit, and forward horizons?
- What benchmark is used?
- Which regimes and asset classes apply?
- What costs are charged?
- What is the untouched out-of-sample boundary?
- What is the deactivation or reactivation rule?
- What is the current lifecycle stage and confidence?
- Does the signal have capital rights? Default: no.

Signal definitions and results are versioned separately so a changed rule cannot inherit the old backtest silently.

### ADR-002 — Forecast records are separate from signal research

A signal hypothesis is not itself a forecast. Forecasts live under:

```text
forecast_records/
├── schema/
├── open/
├── resolved/
└── reports/
```

This boundary prevents a persuasive narrative, backtest, or research note from being counted as a timestamped prediction.

Every countable forecast must contain:

- stable forecast ID;
- project (`signals` or `polymarket`);
- precise question and target;
- probability, numerical estimate, or distribution;
- benchmark value;
- information cutoff;
- horizon and resolution rule;
- base rate or reference class;
- supporting and disconfirming evidence;
- update history;
- regime and asset-class applicability;
- outcome, score, and postmortem after resolution.

### ADR-003 — Open and resolved forecasts are stored separately

Open forecasts remain mutable only through append-only updates. Resolution moves or materializes a record under `resolved/` while preserving the original and every update.

Automatic reports calculate:

- Brier score for binary forecasts;
- absolute and squared error for numerical forecasts when declared;
- relative improvement versus the frozen benchmark;
- project-versus-Polymarket performance;
- calibration buckets;
- breakdowns by project, regime, asset class, signal family, and horizon;
- process compliance and postmortem completion.

### ADR-004 — Polymarket ingestion is a separate bounded context

Polymarket-specific concerns belong under `polymarket/`:

```text
polymarket/
├── catalog/       Exact event, condition, token, slug, and logical-market identity
├── collectors/    Daily snapshots, ranges, hourly prices, and order books
├── lifecycle/     Replacements, disputes, closures, and resolutions
└── charts/        Seven-day, heatmap, related-market, and liquidity views
```

Generic signal research must consume normalized market observations rather than embed Polymarket API and lifecycle logic directly.

The following remain distinct:

- market-implied probability;
- the project's independent probability;
- user rating or annotation;
- signal classification;
- oil or asset-price read-through;
- final market resolution.

### ADR-005 — Shared rules move into `core/`; orchestration moves into `apps/`

Reusable domain objects, validation, scoring, confidence, storage, and lifecycle rules belong in `core/`.

User-facing commands and multi-step workflows belong in `apps/`, including:

- daily market update;
- signal research command;
- forecast entry and update flow;
- scoring and calibration report generation;
- chart publication;
- monthly review.

This prevents large root-level scripts from owning business rules that other workflows need.

### ADR-006 — Data has explicit authority and grain

```text
data/
├── snapshots/    Daily comparable cutoff observations
├── ranges/       Trailing-window minimum and maximum observations
├── lifecycle/    Append-only state transitions
├── hourly/       Bounded monthly high-frequency files
└── artifacts/    Backtests, reports, manifests, and generated outputs
```

Rules:

- historical snapshot values are never revised silently;
- duplicates are rejected by stable identity and cutoff;
- closed markets stop appending normal observations;
- files are replaced atomically;
- daily and hourly datasets declare their grain and authority;
- large high-frequency data remains outside routine Git commits unless explicitly approved;
- generated charts are not authoritative data.

### ADR-007 — Compatibility wrappers remain during migration

Existing root-level scripts, CSV paths, and published chart names may remain as compatibility interfaces while their internals delegate to the new modules.

A compatibility wrapper must:

- preserve existing command arguments and output schema;
- contain minimal logic;
- call the new implementation;
- be removable only after all workflows and users have migrated;
- never create a second source of truth.

### ADR-008 — Tests mirror the architecture

Tests should gradually mirror their source boundary:

```text
tests/
├── core/
├── signals/
├── polymarket/
├── forecast_records/
└── integration/
```

Required checks include:

- no lifecycle-stage skipping;
- no signal-definition/version mismatch;
- no look-ahead timestamps;
- chronological update chains;
- valid probability bounds;
- immutable original forecast preservation;
- correct scoring and benchmark comparison;
- append-only market history;
- closed-market safeguards;
- exact contract and replacement identity;
- content-addressed chart publication.

### ADR-009 — Automation is organized by responsibility

GitHub Actions remain under `.github/workflows/`, grouped by purpose:

- data collection and lifecycle refresh;
- signal governance and backtests;
- forecast validation, scoring, and calibration;
- reliability guardrails;
- chart publication;
- monthly review.

A scheduled workflow must fail visibly rather than silently omit missing data, malformed records, or unavailable sources.

### ADR-010 — Migration is incremental and value-driven

The repository will not be reorganized in one large mechanical pull request.

Move code when one of these is true:

- the file is already being materially changed;
- duplicated logic needs one owner;
- a new signal or forecast requires the boundary;
- tests cannot be made reliable without separation;
- runtime or maintenance cost materially improves.

Do not move code solely for aesthetic consistency.

## End-to-end data flow

```text
External sources
    ↓
Collectors and source-specific validation
    ↓
Immutable raw observations and lifecycle events
    ↓
Normalized domain records
    ↓
Signal evaluation and cost-aware backtests
    ↓
Prospective forecast records
    ↓
Scoring, calibration, benchmark comparison, and postmortems
    ↓
Daily dashboards and decision support
```

## Speed standard

For future repository changes:

1. Prefer the smallest safe change that creates a durable boundary.
2. Reuse existing working collectors and schemas instead of rewriting them.
3. Add a compatibility wrapper before moving a public command or data path.
4. Run only the tests affected by the first pass, then the full reliability suite before merge.
5. Separate architectural cleanup from market-data collection and daily-report delivery so urgent updates are not delayed.
6. Report clearly whether a change is documented, partially implemented, or fully migrated.

## Current adoption status

- Signal lifecycle and canonical-before-enhanced governance: implemented.
- Prospective forecast schema, validation, scoring, and calibration reports: implemented on the PR branch.
- Exact Polymarket market-data and lifecycle boundary: partially implemented in `market_data/` and existing collectors.
- One-directory-per-signal layout: adopted as target; migration will be incremental.
- `apps/` and `core/` separation: adopted as target; migration will be incremental.
- Open/resolved forecast directory split: adopted as target; existing records directory will migrate without fabricating retrospective forecasts.
- Compatibility wrappers: required for every moved public command or persistent data path.
