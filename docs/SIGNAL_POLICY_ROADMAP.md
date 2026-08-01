# U.S. legislative policy-alpha roadmap

## Governing question

> **Can this signal earn and keep the right to influence capital allocation?**

## Governing principle

> **Canonical before enhanced.** The system must first interpret completed legislation accurately and without hindsight before it attempts the harder pre-passage problem.

This roadmap is research-only. Passing a roadmap gate does not authorize real-money trading.

## The eight-step sequence

### 1. Freeze the post-passage rule

The canonical just-passed legislation hypothesis is frozen before historical evaluation. It defines the information cutoff, exposure universe, entry and exit rules, benchmark, costs, invalidation conditions, deactivation rule and out-of-sample boundary.

**Current status:** completed.

### 2. Build a diverse historical legislation set

Select and lock the historical case universe before reviewing outcomes. The set must include nationally prominent and niche laws, beneficiaries and harmed exposures, no-trade conclusions, already-priced effects, delayed implementation, intuitive trades that failed and second-order supplier, customer or competitor effects.

The version-1 readiness gate requires at least 24 locked cases, coverage of all eight event categories and all seven case types. These thresholds are frozen before case selection and cannot be changed after outcomes are reviewed without a roadmap version change.

**Current status:** ready to start; the case registry is intentionally empty.

### 3. Reconstruct each case using only point-in-time information

Each case receives a packet containing only information available at its declared cutoff: operative text, official timestamps, official summaries and estimates, contemporaneous company disclosures, contemporaneous reporting, the tradable universe and point-in-time financial data.

Every source retains its publication timestamp. The complete input packet receives a deterministic hash. Post-event prices, later earnings and retrospective explanatory articles are prohibited.

**Current status:** blocked until step 2 is complete.

### 4. Generate and seal blinded impact memos

Before outcomes are visible, each case receives a versioned and hashed policy-impact memo recording:

- beneficiaries, harmed exposures and explicit no-trade conclusions;
- expected direction and economic mechanism;
- materiality basis and realization horizon;
- trade expression, benchmark, entry and exit rules;
- invalidation conditions;
- confidence before outcome;
- known competing explanations.

The original memo cannot be silently rewritten. Corrections create a new version while preserving the original.

**Current status:** blocked until step 3 is complete.

### 5. Reveal outcomes and explanatory reporting

Only after the memo hash exists may the system reveal:

- 1-, 5-, 20- and 60-session returns;
- benchmark and after-cost abnormal returns;
- later operating-performance changes;
- company disclosures after the event;
- mainstream, specialist and niche reporting;
- implementation timing and competing market explanations.

Niche reporting is deliberately included because it can reveal supply-chain or competitive effects that the obvious exposure misses. Unless published before the information cutoff, it belongs only in the reveal packet.

**Current status:** blocked until step 4 is complete.

### 6. Score interpretation separately from investment usefulness

Interpretation accuracy and investment usefulness remain separate 0–100 scores.

Interpretation accuracy evaluates the operative text and legal mechanism, exposure mapping, direction, materiality, implementation timing, invalidation and competing explanations.

Investment usefulness evaluates directional results, benchmark-adjusted and after-cost performance, magnitude and timing alignment, operating-performance alignment and attribution quality.

A law can be interpreted correctly without creating a profitable trade. A profitable stock move does not prove that the law caused it. A single case grants no capital rights.

**Current status:** blocked until step 5 is complete.

### 7. Use the errors to improve the framework

Scored cases feed an append-only revision registry. Every revision must:

- cite the historical cases that exposed the error;
- classify the error using the frozen taxonomy;
- state the problem and the change made;
- preserve the original memos, outcomes and scores;
- create a new framework version;
- apply prospectively rather than rewriting history.

The taxonomy includes text interpretation, exposure mapping, direction, materiality, implementation timing, benchmark selection, already-priced effects, company events, macro confounders, execution costs, data quality and attribution.

**Current status:** blocked until step 6 produces scored cases.

### 8. Begin untouched prospective testing on newly passed legislation

Prospective post-passage testing begins only when the historical readiness gate passes. Version 1 requires:

- at least 24 selected and 24 scored historical cases;
- complete event-category and case-type coverage;
- mean interpretation accuracy of at least 70;
- zero hindsight-audit failures;
- valid packet, memo and outcome hashes.

Investment usefulness is diagnostic rather than a gate for beginning prospective research. The goal of this gate is to establish reliable comprehension before testing live, untouched events. Passing it grants research-only status, never real-money authorization.

An activation timestamp must be frozen before the first eligible prospective law. Each prospective case must then be captured without outcome knowledge.

**Current status:** blocked until the historical readiness gate passes.

## Repository enforcement

The machine-readable roadmap is:

```text
signal_research/policy_roadmap.json
```

The validator and readiness calculation are:

```text
signal_research/policy_roadmap.py
```

Historical cases, framework revisions and prospective cases are stored separately:

```text
signal_records/policy_historical_cases.json
signal_records/policy_framework_revisions.json
signal_records/policy_prospective_cases.json
```

The validator rejects:

- a roadmap with missing, reordered or renumbered steps;
- dependencies that point forward;
- framework revisions that rewrite prior results or apply retrospectively;
- prospective cases before the historical readiness gate passes;
- prospective activation without a frozen timestamp;
- any real-money authorization.

## Commands

```bash
python signal_cli.py policy-roadmap
python signal_cli.py policy-benchmark
python signal_cli.py policy-case <case-id>
python signal_cli.py validate
python -m unittest tests.test_signal_policy_roadmap -v
```

## Relationship to Polymarket

The separate Polymarket module remains an approved but unfrozen input for the future pre-passage variant. It can provide deadline-specific passage probabilities and a probability term structure, but it cannot replace official text, schedules, votes, amendment-risk analysis or exposure mapping.

That design is already stored in:

```text
signal_research/policy_prediction_markets.json
docs/SIGNAL_POLICY_PREDICTION_MARKETS.md
```

The roadmap deliberately places that enhanced work after the system proves it can interpret completed legislation honestly.
