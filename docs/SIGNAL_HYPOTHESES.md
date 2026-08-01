# Canonical hypothesis freeze standard

## Purpose

Step 1 of the Signals implementation freezes the simplest defensible research
version of each candidate before dataset construction begins.

The governing question remains:

> **Can this signal earn and keep the right to influence capital allocation?**

The governing principle is:

> **Canonical before enhanced.** A simple, predeclared version must demonstrate
> out-of-sample value before thresholds, weighting, filters, ensembles, machine
> learning or other complexity are allowed.

`signal_hypotheses.json` is the durable source of truth for the exact research
rules. Chat explanations and source posts do not override it.

## Frozen versus blocked

A `frozen` canonical hypothesis specifies all of the following:

- information available at the decision time;
- tradable instrument;
- exact entry, exit, direction and trigger rules;
- benchmark;
- applicable and invalid regimes;
- transaction-cost treatment;
- mechanical deactivation rule;
- untouched out-of-sample boundary;
- timezone and observation grain;
- definition version.

A `blocked` hypothesis preserves the supported parts of the source claim while
listing every unresolved field in `blocking_fields`. A blocked record is not
eligible for dataset construction or backtesting. This is intentional: missing
information is recorded rather than replaced by persuasive-sounding precision.

## Current version 1 status

Six canonical definitions are frozen for research dataset construction:

- `ANALYST-AAPL-001`
- `TECH-HMA-001`
- `TECH-MVWAP-BTC-001`
- `MACRO-XLY-BTC-001`
- `MICRO-ASIA-SNDK-001`
- `FLOW-MON-BTC-001`

Two remain blocked:

- `POLICY-SEMIS-001` — the source does not yet fix the eligible announcement
  universe, expected direction, executable entry or held-out boundary.
- `CROSS-ASSET-REBOUND-001` — the four rebound components are implemented, but a
  mechanical common-shock detector, event reference, maximum horizon and
  aggregation rule must be frozen before event collection can be unbiased.

Frozen means the research rule is fixed. It does **not** mean the signal is
validated, profitable, production-ready or authorized for real-money trading.

## Source claim versus research definition

Some source posts describe an observation without a complete trading rule. In
those cases, version 1 records both:

- `source_claim` — what the supplied evidence actually asserts;
- the canonical research rule — the deliberately simple, executable translation
  selected for testing.

`source_fidelity_notes` explains every material difference. For example, the
SNDK source chart used a late-night reference that is not assumed to be an
executable SNDK entry; the canonical test waits for the next regular-session open.

## Definition fingerprints

Each hypothesis receives a deterministic SHA-256 fingerprint computed from its
complete definition. A change to entry, exit, direction, benchmark, costs,
regimes, timing or any other field changes the fingerprint.

A material change must create a new `definition_version`; it must not silently
rewrite historical results produced under an earlier fingerprint.

## Dataset eligibility

A signal is eligible for step 2 only when:

1. its variant is `canonical`;
2. its freeze status is `frozen`;
3. `blocking_fields` is empty;
4. the repository validator passes.

Enhanced variants cannot freeze before their canonical version. No hypothesis
file may authorize real-money trading.

## Commands

```bash
python signal_cli.py hypotheses
python signal_cli.py hypothesis FLOW-MON-BTC-001
python signal_cli.py hypothesis S-010
python signal_cli.py validate
python -m unittest tests.test_signal_hypotheses -v
```

`signal_cli.py hypotheses` reports frozen, blocked and dataset-eligible counts
plus each definition fingerprint.

## Next step

Step 2 will build reproducible, versioned datasets only for the six currently
eligible canonical definitions. Dataset manifests must bind raw sources,
transformations and hashes to the exact hypothesis fingerprint that requested the
data.
