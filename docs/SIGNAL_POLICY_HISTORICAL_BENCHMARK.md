# Historical policy interpretation benchmark

## Purpose

The canonical `POLICY-US-LEGISLATION-001` signal asks whether the system can interpret newly enacted U.S. federal legislation accurately enough to identify economically meaningful public-market exposures.

Before the project attempts the harder pre-passage problem, it must demonstrate that it can understand completed legislation without hindsight.

The benchmark asks two different questions:

1. **Interpretation accuracy:** Did the system correctly understand what the law changed, which exposures were affected, in what direction, at what magnitude, and on what timeline?
2. **Investment usefulness:** Did the sealed interpretation identify an executable exposure that produced abnormal after-cost value against a predeclared benchmark?

These scores remain separate. Correct statutory interpretation is not automatically trading alpha, and a profitable stock move is not automatically evidence that the law caused it.

## Governing standards

> **Can this signal earn and keep the right to influence capital allocation?**

> **Canonical before enhanced.** The simple, auditable post-passage interpretation task must work before pre-passage probability models, prediction-market weighting or more complex policy forecasts can influence the research process.

This benchmark is research-only. It does not authorize real-money trading.

## Six-stage workflow

### 1. Lock case selection

The benchmark case list is selected before reviewing post-event returns or retrospective explanatory reporting.

The set must include winners, losers, no-trade conclusions, anticipated effects, delayed implementation, failed intuitive trades, and second-order supplier, customer or competitor effects. Cases may be nationally prominent or niche, but they cannot be chosen because a famous trade is already known to have worked.

### 2. Lock the point-in-time packet

The input packet contains only information available by the declared cutoff:

- operative legislative text and version;
- official passage and signing timestamps;
- official summaries, fiscal estimates and agency material;
- contemporaneous company disclosures;
- contemporaneous news published before the cutoff;
- the tradable universe and point-in-time financial data available then.

Every source is stored as a structured evidence record with:

- one or more human or institutional authors;
- a publisher;
- URL, title, publication and access timestamps;
- source type and reliability;
- evidence stance and affected claims;
- archive reference and notes.

When no individual byline exists, the responsible institution is recorded as the author. The author and publisher remain separate fields.

Every source retains its publication timestamp. The complete packet receives a deterministic hash.

NotebookLM, Gemini or another research assistant may help organize and compare the registered pre-cutoff source set. Any such use must be disclosed in `research_assistance_records`. AI output is not evidence, and every accepted claim must be verified against the original registered source before the packet can lock.

### 3. Seal the policy-impact memo

Before any outcome is revealed, the system records and hashes:

- predicted beneficiaries and harmed exposures;
- explicit no-trade conclusions;
- expected direction;
- economic mechanism;
- materiality basis;
- realization horizon;
- primary trade expression;
- benchmark, entry and exit rules;
- invalidation conditions;
- confidence before outcome;
- known competing explanations.

The sealed memo cannot be silently rewritten. Corrections require a new version while preserving the original.

No unresolved or unverified AI-generated claim may enter the sealed memo.

### 4. Reveal the outcome packet

Only after the memo hash is stored may the project reveal:

- 1-, 5-, 20- and 60-session returns;
- benchmark and after-cost abnormal returns;
- later operating-performance changes;
- later company disclosures;
- mainstream reporting;
- specialist trade-publication and niche reporting;
- implementation timing and competing market explanations.

Niche reporting is especially valuable for identifying unexpected supply-chain or competitive transmission. It belongs in the reveal packet unless it was genuinely published before the information cutoff.

NotebookLM, Gemini or another disclosed assistant may help compare the sealed memo with the registered outcome evidence. The original articles, filings, official documents and datasets remain the evidence sources.

### 5. Score the case

Interpretation accuracy is scored from 0 to 100 across:

- operative text and legal mechanism: 25;
- beneficiary and loser mapping: 25;
- directional effect: 15;
- materiality estimate: 15;
- implementation timing: 10;
- invalidation and competing explanations: 10.

Investment usefulness is scored separately from 0 to 100 across:

- directional market result: 20;
- benchmark-adjusted result: 20;
- after-cost result: 15;
- magnitude and timing alignment: 15;
- operating-performance alignment: 15;
- attribution quality: 15.

A single successful case grants no capital rights.

### 6. Record lessons

Each case must explain:

- what the system understood correctly;
- what it misunderstood;
- whether the obvious exposure or a second-order exposure mattered more;
- whether the effect was already priced;
- whether implementation differed from the text;
- whether an unrelated company or macro event dominated;
- how the next frozen version should improve without rewriting the original result.

## Temporal firewall

The repository validator enforces the following ordering:

```text
case selection
  -> point-in-time packet and hash
  -> sealed memo and hash
  -> outcome reveal and hash
  -> separate scores
  -> lessons
```

Before `outcome_revealed`, a case may not contain an outcome packet or scores. A revealed or scored case must have valid input, memo and outcome hashes. This prevents retrospective articles, later earnings, stock performance or other outcome information from leaking into the original interpretation.

Pre-cutoff AI assistance may reference only registered pre-cutoff evidence. Post-outcome AI assistance may use registered input and outcome evidence, but it cannot alter the sealed memo.

## Case registry

The durable case registry is:

```text
signal_records/policy_historical_cases.json
```

It is intentionally empty until the case universe is selected and locked. Narrative examples are not entered as scored wins without a point-in-time packet and a sealed memo.

The machine-readable benchmark protocol is:

```text
signal_research/policy_historical_benchmark.json
```

The validator and scoring implementation is:

```text
signal_research/policy_benchmark.py
```

Source identity and contradiction rules are documented in:

```text
docs/SIGNAL_POLICY_EVIDENCE_STANCE.md
```

NotebookLM, Gemini and other AI-assistance rules are documented in:

```text
docs/SIGNAL_POLICY_AI_RESEARCH_ASSISTANCE.md
```

## Commands

```bash
python signal_cli.py policy-benchmark
python signal_cli.py policy-case <case-id>
python signal_cli.py validate
python -m unittest tests.test_signal_policy_historical_benchmark -v
```

## Relationship to the Polymarket design

The historical benchmark tests whether the project can understand enacted legislation. The separate Polymarket design supports the future enhanced pre-passage variant by preserving deadline-specific market probabilities as one prospective input.

The prediction-market design is stored in:

```text
signal_research/policy_prediction_markets.json
docs/SIGNAL_POLICY_PREDICTION_MARKETS.md
```

It remains blocked from becoming a trading trigger until contract matching, liquidity, spread, probability thresholds, stale-price controls, amendment risk, exact timing and out-of-sample rules are frozen.
